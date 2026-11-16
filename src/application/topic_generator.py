"""
Topic Generator - Auto topic selection logic
"""

from pathlib import Path
from typing import Any, Optional

from src.domain.services.deduplication import ContentDeduplicator
from src.infrastructure.utils.fresh_topics import fresh_topics_enabled, pick_fresh_topic
from src.infrastructure.utils.text_utils import normalize_text

AccountConfig = dict[str, Any]


def _normalise_label(value: str) -> str:
    """Normalize label for comparison (alias for normalize_text)"""
    return normalize_text(value)


def _pillar_keys(account_config: AccountConfig) -> list[str]:
    """Extract sorted pillar keys from account config

    Args:
        account_config: Account configuration dict

    Returns:
        List of pillar names sorted by priority
    """
    pillars = account_config.get("content_pillars", {})
    if not isinstance(pillars, dict):
        return []
    return [
        str(name)
        for name, _ in sorted(pillars.items(), key=lambda item: item[1], reverse=True)
    ]


def select_rotating_pillar(
    account_config: AccountConfig, dedup: ContentDeduplicator
) -> Optional[str]:
    """Select next pillar for rotation based on recent usage

    Args:
        account_config: Account configuration dict
        dedup: Content deduplicator instance

    Returns:
        Selected pillar name or None if no pillars available
    """
    pillar_keys = _pillar_keys(account_config)
    if not pillar_keys:
        return None

    recent_topics = " ".join(dedup.get_recent_topics(limit=len(pillar_keys) * 2)).lower()
    for pillar_key in pillar_keys:
        pillar_label = _normalise_label(pillar_key).lower()
        if pillar_label and pillar_label not in recent_topics:
            return pillar_key

    recent_count = len(dedup.get_recent_topic_angle_pairs(limit=100))
    return pillar_keys[recent_count % len(pillar_keys)]


class TopicGenerator:
    """Generates topics automatically based on account config and niche"""

    def __init__(
        self,
        account_id: str,
        account_config: AccountConfig,
        accounts_path: Path,
    ):
        self.account_id = account_id
        self.account_config = account_config
        self.accounts_path = accounts_path
        self.dedup = ContentDeduplicator(account_id)

    def generate(self) -> str:
        """
        Generate auto topic based on account niche and content pillars

        Returns:
            Generated topic string
        """
        # Check if fresh_topics is enabled
        if fresh_topics_enabled():
            print("\n🔄 Fresh Topics enabled - picking from trending topics...")
            recent_topics = self.dedup.get_recent_topics(limit=20)
            selected_pillar = select_rotating_pillar(self.account_config, self.dedup)
            fresh_topic = pick_fresh_topic(
                self.account_config, recent_topics, selected_pillar
            )
            if fresh_topic:
                print(f"✅ Selected fresh topic: {fresh_topic}")
                return fresh_topic
            else:
                print("⚠️  No fresh topics available, falling back to pillar rotation")

        # Fallback to pillar rotation
        niche = self.account_config.get("niche", "general")
        selected_pillar = select_rotating_pillar(self.account_config, self.dedup)

        if selected_pillar:
            topic = f"{niche} - {selected_pillar}"
            print(f"\n📌 Auto-selected pillar: {selected_pillar}")
        else:
            topic = niche
            print(f"\n📌 Using niche as topic: {niche}")

        return topic
