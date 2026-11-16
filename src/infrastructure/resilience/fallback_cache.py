#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fallback Cache - Store last successful generation per account
Used when circuit breaker is OPEN to provide cached content
"""

import json
import time
from typing import Any, Optional

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from infrastructure.logging.logger import setup_logger

logger = setup_logger(__name__)


class FallbackCache:
    """
    Cache last successful generation per account
    
    Cache structure: {account_id: {content, timestamp, qc_score, format}}
    TTL: 7 days
    Storage: Redis if available, else in-memory dict
    """
    
    def __init__(self, redis_url: Optional[str] = None, ttl_seconds: int = 604800):
        """
        Initialize fallback cache
        
        Args:
            redis_url: Redis connection URL (redis://host:port/db)
            ttl_seconds: Cache TTL in seconds (default: 7 days)
        """
        self.redis_url = redis_url
        self.ttl_seconds = ttl_seconds
        self._client: Optional[redis.Redis] = None
        self._fallback_dict: dict[str, dict[str, Any]] = {}
        self._use_redis = False
    
    async def connect(self) -> None:
        """Initialize Redis connection"""
        if not REDIS_AVAILABLE or not self.redis_url:
            logger.info("Fallback cache using in-memory storage")
            return
        
        try:
            self._client = redis.Redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            await self._client.ping()
            self._use_redis = True
            logger.info(f"Fallback cache connected to Redis: {self.redis_url}")
        except Exception as e:
            logger.warning(f"Fallback cache Redis connection failed: {e} - using in-memory")
            self._use_redis = False
            self._client = None
    
    async def store(
        self,
        account_id: str,
        content: str,
        qc_score: float,
        format: str,
    ) -> bool:
        """
        Store successful generation in cache
        
        Args:
            account_id: Account ID
            content: Generated content
            qc_score: Quality control score
            format: Content format
        
        Returns:
            True if stored successfully
        """
        cache_entry = {
            "content": content,
            "timestamp": time.time(),
            "qc_score": qc_score,
            "format": format,
        }
        
        key = f"fallback:{account_id}"
        
        # Try Redis first
        if self._use_redis and self._client:
            try:
                await self._client.setex(
                    key,
                    self.ttl_seconds,
                    json.dumps(cache_entry)
                )
                logger.debug(f"Stored fallback cache for {account_id} in Redis")
                return True
            except Exception as e:
                logger.warning(f"Failed to store in Redis: {e}")
                # Fall through to in-memory
        
        # In-memory fallback
        self._fallback_dict[key] = cache_entry
        logger.debug(f"Stored fallback cache for {account_id} in memory")
        return True
    
    async def get(self, account_id: str) -> Optional[dict[str, Any]]:
        """
        Get cached generation for account
        
        Args:
            account_id: Account ID
        
        Returns:
            Cache entry dict or None if not found/expired
        """
        key = f"fallback:{account_id}"
        
        # Try Redis first
        if self._use_redis and self._client:
            try:
                value = await self._client.get(key)
                if value:
                    cache_entry = json.loads(value)
                    logger.debug(f"Retrieved fallback cache for {account_id} from Redis")
                    
                    # Record cache hit metric
                    try:
                        from infrastructure.monitoring.metrics import record_fallback_cache_hit
                        record_fallback_cache_hit()
                    except ImportError:
                        pass
                    
                    return cache_entry
            except Exception as e:
                logger.warning(f"Failed to get from Redis: {e}")
                # Fall through to in-memory
        
        # In-memory fallback
        cache_entry = self._fallback_dict.get(key)
        if cache_entry:
            # Check TTL for in-memory cache
            age = time.time() - cache_entry["timestamp"]
            if age > self.ttl_seconds:
                # Expired, remove
                del self._fallback_dict[key]
                return None
            
            logger.debug(f"Retrieved fallback cache for {account_id} from memory")
            
            # Record cache hit metric
            try:
                from infrastructure.monitoring.metrics import record_fallback_cache_hit
                record_fallback_cache_hit()
            except ImportError:
                pass
            
            return cache_entry
        
        return None
    
    async def close(self) -> None:
        """Close Redis connection"""
        if self._client:
            await self._client.close()


# Global singleton instance
_fallback_cache: Optional[FallbackCache] = None


async def get_fallback_cache(redis_url: Optional[str] = None) -> FallbackCache:
    """Get or create global fallback cache instance"""
    global _fallback_cache
    if _fallback_cache is None:
        _fallback_cache = FallbackCache(redis_url=redis_url)
        await _fallback_cache.connect()
    return _fallback_cache
