"""
Content deduplication system
Prevents generating duplicate or very similar content
Enforces configurable weekly format limits
Supports Redis for scalability (fallback to JSON)
"""

import hashlib
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from infrastructure.constants import THEME_STOPWORDS
from infrastructure.logging.logger import get_logger
from infrastructure.utils.text_utils import normalize_text

logger = get_logger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class DeduplicationStore:
    """Abstract storage backend for deduplication history"""
    
    def load_history(self) -> dict[str, list[dict[str, Any]]]:
        raise NotImplementedError
    
    def save_history(self, history: dict[str, list[dict[str, Any]]]) -> None:
        raise NotImplementedError


class JSONDeduplicationStore(DeduplicationStore):
    """JSON file-based deduplication storage"""
    
    def __init__(self, account_id: str, history_file: Path) -> None:
        self.account_id = account_id
        self.history_file = history_file
    
    def load_history(self) -> dict[str, list[dict[str, Any]]]:
        """Load content generation history from JSON"""
        if self.history_file.exists():
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load history file: {e}", exc_info=True)
                return {"generated": []}
        return {"generated": []}
    
    def save_history(self, history: dict[str, list[dict[str, Any]]]) -> None:
        """Save content generation history to JSON"""
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)


class RedisDeduplicationStore(DeduplicationStore):
    """Redis-based deduplication storage (async-compatible)"""
    
    def __init__(self, account_id: str) -> None:
        self.account_id = account_id
        self.redis_key = f"dedup:{account_id}:history"
        self._cache = None
        self._fallback_store = None
    
    def _get_cache(self):
        """Get Redis cache instance (lazy init)"""
        if self._cache is None:
            try:
                import asyncio
                from infrastructure.cache.redis_client import get_cache
                
                # Try to get cache synchronously (will use in-memory if Redis unavailable)
                loop = asyncio.get_event_loop()
                self._cache = loop.run_until_complete(get_cache())
            except Exception as e:
                logger.warning(f"Redis cache init failed: {e} - using JSON fallback")
                # Fallback to JSON
                history_file = PROJECT_ROOT / "output" / self.account_id / ".content_history.json"
                self._fallback_store = JSONDeduplicationStore(self.account_id, history_file)
        return self._cache
    
    def load_history(self) -> dict[str, list[dict[str, Any]]]:
        """Load content generation history from Redis"""
        # Use fallback if Redis init failed
        if self._fallback_store:
            return self._fallback_store.load_history()
        
        cache = self._get_cache()
        if not cache or not cache.is_redis_enabled:
            # Redis not available, use JSON fallback
            history_file = PROJECT_ROOT / "output" / self.account_id / ".content_history.json"
            self._fallback_store = JSONDeduplicationStore(self.account_id, history_file)
            return self._fallback_store.load_history()
        
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            history_json = loop.run_until_complete(cache.get(self.redis_key))
            
            if history_json:
                return json.loads(history_json)
            return {"generated": []}
        except Exception as e:
            logger.warning(f"Redis load failed: {e} - using JSON fallback")
            history_file = PROJECT_ROOT / "output" / self.account_id / ".content_history.json"
            self._fallback_store = JSONDeduplicationStore(self.account_id, history_file)
            return self._fallback_store.load_history()
    
    def save_history(self, history: dict[str, list[dict[str, Any]]]) -> None:
        """Save content generation history to Redis"""
        # Use fallback if Redis init failed
        if self._fallback_store:
            return self._fallback_store.save_history(history)
        
        cache = self._get_cache()
        if not cache or not cache.is_redis_enabled:
            # Redis not available, use JSON fallback
            if not self._fallback_store:
                history_file = PROJECT_ROOT / "output" / self.account_id / ".content_history.json"
                self._fallback_store = JSONDeduplicationStore(self.account_id, history_file)
            return self._fallback_store.save_history(history)
        
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            history_json = json.dumps(history)
            # Store in Redis with 90-day TTL
            loop.run_until_complete(cache.set(self.redis_key, history_json, ttl=90*24*3600))
        except Exception as e:
            logger.warning(f"Redis save failed: {e} - using JSON fallback")
            if not self._fallback_store:
                history_file = PROJECT_ROOT / "output" / self.account_id / ".content_history.json"
                self._fallback_store = JSONDeduplicationStore(self.account_id, history_file)
            self._fallback_store.save_history(history)


def get_weekly_limits() -> dict[str, int]:
    """Get weekly limits from config"""
    try:
        from src.infrastructure.config.loader import load_weekly_limits

        return load_weekly_limits()
    except Exception as e:
        # Fallback to defaults
        logger.debug(f"Using default weekly limits (config load failed): {e}")
        return {"Thread": 1, "Single Tweet": 7, "Poll": 2, "Image": 3}


def enforce_redis_for_scale(account_count: int) -> None:
    """
    Enforce Redis requirement for 50+ accounts
    
    Args:
        account_count: Number of accounts being processed
        
    Raises:
        RuntimeError: If Redis not configured for 50+ accounts
    """
    if account_count > 50:
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            raise RuntimeError(
                f"Redis required for {account_count} accounts (50+ threshold). "
                "Set REDIS_URL environment variable."
            )


class ContentDeduplicator:
    """Track and prevent duplicate content generation"""

    def __init__(self, account_id: str, use_redis: bool = False) -> None:
        self.account_id = account_id
        self.use_redis = use_redis
        self.history_file = PROJECT_ROOT / "output" / account_id / ".content_history.json"
        
        # Storage backend
        if use_redis:
            self._store = RedisDeduplicationStore(account_id)
        else:
            self._store = JSONDeduplicationStore(account_id, self.history_file)
        
        # Lazy loading: don't load history upfront
        self._history = None
    
    @property
    def history(self) -> dict[str, list[dict[str, Any]]]:
        """Lazy load history on first access"""
        if self._history is None:
            self._history = self._store.load_history()
        return self._history
    
    @history.setter
    def history(self, value: dict[str, list[dict[str, Any]]]) -> None:
        """Set history value"""
        self._history = value

    def _load_history(self) -> dict[str, list[dict[str, Any]]]:
        """Load content generation history (deprecated - use store)"""
        return self._store.load_history()

    def _save_history(self):
        """Save content generation history (deprecated - use store)"""
        self._store.save_history(self.history)

    def _compute_content_hash(self, content: str) -> str:
        """Compute hash of content (normalized)"""
        # Normalize: lowercase, remove extra whitespace
        normalized = " ".join(content.lower().split())
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def _compute_topic_hash(self, topic: str, angle_title: str) -> str:
        """Compute hash of topic + angle"""
        combined = f"{topic.lower()}|{angle_title.lower()}"
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    def _normalise_topic(self, topic: str) -> str:
        """Normalize topic for comparison"""
        return normalize_text(topic)

    def _normalise_angle(self, angle_title: str) -> str:
        """Normalize angle for comparison"""
        return normalize_text(angle_title)

    def _similarity_score(self, text1: str, text2: str) -> float:
        """Compute simple word overlap similarity (0-1)"""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = words1.intersection(words2)
        union = words1.union(words2)

        return len(intersection) / len(union)

    def _theme_tokens(self, text: str) -> set[str]:
        words = re.findall(r"[a-z0-9]+", text.lower())
        return {word for word in words if len(word) > 3 and word not in THEME_STOPWORDS}

    def _theme_similarity_score(self, text1: str, text2: str) -> float:
        words1 = self._theme_tokens(text1)
        words2 = self._theme_tokens(text2)

        if not words1 or not words2:
            return 0.0

        intersection = words1.intersection(words2)
        union = words1.union(words2)
        return len(intersection) / len(union)

    def _get_format_count_this_week(self, format_type: str) -> int:
        """Count how many of specific format generated in current week"""
        now = datetime.now()
        week_start = now - timedelta(days=now.weekday())  # Monday of current week
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

        format_count = 0
        for entry in self.history.get("generated", []):
            if entry.get("format") != format_type:
                continue

            try:
                entry_time = datetime.fromisoformat(entry.get("timestamp", ""))
                # Safely normalize naive and aware datetimes
                if entry_time.tzinfo is not None and week_start.tzinfo is None:
                    entry_time = entry_time.replace(tzinfo=None)
                elif entry_time.tzinfo is None and week_start.tzinfo is not None:
                    week_start = week_start.replace(tzinfo=None)
                if entry_time >= week_start:
                    format_count += 1
            except (ValueError, TypeError):
                # Skip entries with invalid timestamps
                continue

        return format_count

    def check_format_weekly_limit(self, format_type: str) -> tuple[bool, Optional[str]]:
        """
        Check if format generation is allowed this week

        Args:
            format_type: Format name (Thread, Single Tweet, Poll, Image)

        Returns:
            (is_blocked, reason)
        """
        limits = get_weekly_limits()
        limit = limits.get(format_type, 0)

        # 0 = unlimited
        if limit == 0:
            return False, None

        current_count = self._get_format_count_this_week(format_type)

        if current_count >= limit:
            return (
                True,
                f"Weekly {format_type} limit reached ({current_count}/{limit} this week). Try different format.",
            )

        return False, None

    def is_duplicate(
        self,
        topic: str,
        angle_title: str,
        content: str,
        similarity_threshold: float = 0.7,
    ) -> tuple[bool, Optional[str]]:
        """
        Check if content is duplicate or too similar to existing content

        Returns:
            (is_duplicate, reason)
        """
        content_hash = self._compute_content_hash(content)
        topic_hash = self._compute_topic_hash(topic, angle_title)

        for entry in self.history.get("generated", []):
            # Exact content match
            if entry.get("content_hash") == content_hash:
                return True, f"Exact duplicate of content from {entry.get('timestamp')}"

            # Same topic + angle
            if entry.get("topic_hash") == topic_hash:
                return (
                    True,
                    f"Same topic/angle already generated on {entry.get('timestamp')}",
                )

            # High similarity check (compare first 500 chars)
            prev_content = entry.get("content_preview", "")
            current_preview = content[:500]

            if (
                prev_content
                and self._similarity_score(prev_content, current_preview)
                > similarity_threshold
            ):
                return (
                    True,
                    f"Very similar content exists from {entry.get('timestamp')}",
                )

        return False, None

    def is_topic_angle_duplicate(
        self, topic: str, angle_title: str
    ) -> tuple[bool, Optional[str]]:
        """Check duplicate by topic + angle only before content generation."""
        topic_hash = self._compute_topic_hash(topic, angle_title)
        for entry in self.history.get("generated", []):
            if entry.get("topic_hash") == topic_hash:
                return (
                    True,
                    f"Same topic/angle already generated on {entry.get('timestamp')}",
                )
        return False, None

    def theme_seen_recently(
        self, text: str, limit: int = 20, threshold: float = 0.55
    ) -> bool:
        """Check whether a topic/angle theme overlaps recent history."""
        normalized = " ".join(text.lower().split()).strip()
        if not normalized:
            return False

        for entry in self.history.get("generated", [])[-limit:]:
            previous = " ".join(
                [
                    str(entry.get("topic", "")),
                    str(entry.get("angle_title", "")),
                ]
            ).strip()
            if (
                previous
                and self._theme_similarity_score(normalized, previous) >= threshold
            ):
                return True
        return False

    def get_recent_topic_angle_pairs(self, limit: int = 100) -> list[dict[str, str]]:
        entries = self.history.get("generated", [])[-limit:]
        pairs: list[dict[str, str]] = []
        for entry in entries:
            topic = str(entry.get("topic", "")).strip()
            angle_title = str(entry.get("angle_title", "")).strip()
            if topic or angle_title:
                pairs.append(
                    {
                        "topic": topic,
                        "angle_title": angle_title,
                    }
                )
        return pairs

    def get_recent_angles_for_topic(self, topic: str, limit: int = 100) -> set[str]:
        normalized_topic = self._normalise_topic(topic)
        recent_angles: set[str] = set()
        for entry in self.history.get("generated", [])[-limit:]:
            entry_topic = self._normalise_topic(str(entry.get("topic", "")))
            if entry_topic == normalized_topic:
                recent_angles.add(
                    self._normalise_angle(str(entry.get("angle_title", "")))
                )
        return recent_angles

    def topic_seen_recently(self, topic: str, limit: int = 20) -> bool:
        normalized_topic = self._normalise_topic(topic)
        if not normalized_topic:
            return False
        recent_topics = self.get_recent_topics(limit=limit)
        return any(
            self._normalise_topic(recent) == normalized_topic
            for recent in recent_topics
        )

    def record_generation(
        self,
        topic: str,
        angle_title: str,
        content: str,
        format_type: str,
        output_file: str,
    ):
        """Record a successful content generation"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "topic": topic,
            "angle_title": angle_title,
            "format": format_type,
            "content_hash": self._compute_content_hash(content),
            "topic_hash": self._compute_topic_hash(topic, angle_title),
            "content_preview": content[:500],  # First 500 chars for similarity check
            "output_file": output_file,
        }

        self.history.setdefault("generated", []).append(entry)

        # Keep only last 100 entries per account
        if len(self.history["generated"]) > 100:
            self.history["generated"] = self.history["generated"][-100:]

        self._save_history()

    def get_recent_topics(self, limit: int = 10) -> list[str]:
        """Get list of recently generated topics"""
        entries = self.history.get("generated", [])
        return [e["topic"] for e in entries[-limit:]]

    def clear_history(self):
        """Clear all history (use with caution)"""
        self.history = {"generated": []}
        self._save_history()


def check_duplicate_before_generation(
    account_id: str, topic: str, angle_title: str, content: str, format_type: str
) -> tuple[bool, Optional[str]]:
    """
    Convenience function to check for duplicates

    Returns:
        (should_skip, reason)
    """
    dedup = ContentDeduplicator(account_id)
    is_dup, reason = dedup.is_duplicate(topic, angle_title, content)
    return is_dup, reason


def record_successful_generation(
    account_id: str,
    topic: str,
    angle_title: str,
    content: str,
    format_type: str,
    output_file: str,
):
    """Record a successful generation to prevent future duplicates"""
    dedup = ContentDeduplicator(account_id)
    dedup.record_generation(topic, angle_title, content, format_type, output_file)
