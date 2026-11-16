#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Redis Cache Client with Connection Pooling
Provides caching for config, prompts, and deduplication history
Falls back to in-memory cache if Redis unavailable
"""

import asyncio
import json
import os
from typing import Any, Optional

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from infrastructure.logging.logger import setup_logger

logger = setup_logger(__name__)


class RedisCache:
    """
    Redis cache client with connection pooling and fallback to in-memory
    """

    def __init__(self, redis_url: Optional[str] = None, max_connections: int = 50) -> None:
        """
        Initialize Redis cache client

        Args:
            redis_url: Redis connection URL (redis://host:port/db)
            max_connections: Max connections in pool (default: 50)
        """
        self.redis_url = redis_url or os.getenv("REDIS_URL")
        self.max_connections = max_connections
        self._pool: Optional[redis.ConnectionPool] = None
        self._client: Optional[redis.Redis] = None
        self._fallback_cache: dict[str, Any] = {}
        self._use_redis = False

    async def connect(self) -> None:
        """Initialize Redis connection pool"""
        if not REDIS_AVAILABLE:
            logger.warning("redis package not installed - using in-memory fallback")
            return

        if not self.redis_url:
            logger.info("REDIS_URL not configured - using in-memory fallback")
            return

        try:
            # Create connection pool
            self._pool = redis.ConnectionPool.from_url(
                self.redis_url,
                max_connections=self.max_connections,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )

            # Create client
            self._client = redis.Redis(connection_pool=self._pool)

            # Test connection
            await self._client.ping()
            self._use_redis = True
            logger.info(f"Redis connected: {self.redis_url} (pool size: {self.max_connections})")

        except Exception as e:
            logger.warning(f"Redis connection failed: {e} - using in-memory fallback")
            self._use_redis = False
            if self._pool:
                await self._pool.disconnect()
                self._pool = None
            self._client = None

    async def get(self, key: str) -> Optional[str]:
        """
        Get value from cache

        Args:
            key: Cache key

        Returns:
            Cached value or None
        """
        if self._use_redis and self._client:
            try:
                value = await self._client.get(key)
                return value
            except Exception as e:
                logger.warning(f"Redis get failed for key '{key}': {e}")
                # Fall through to in-memory cache

        # In-memory fallback
        return self._fallback_cache.get(key)

    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        """
        Set value in cache

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (None = no expiration)

        Returns:
            True if successful
        """
        if self._use_redis and self._client:
            try:
                if ttl:
                    await self._client.setex(key, ttl, value)
                else:
                    await self._client.set(key, value)
                return True
            except Exception as e:
                logger.warning(f"Redis set failed for key '{key}': {e}")
                # Fall through to in-memory cache

        # In-memory fallback
        self._fallback_cache[key] = value
        return True

    async def delete(self, key: str) -> bool:
        """
        Delete key from cache

        Args:
            key: Cache key

        Returns:
            True if key existed
        """
        if self._use_redis and self._client:
            try:
                result = await self._client.delete(key)
                return result > 0
            except Exception as e:
                logger.warning(f"Redis delete failed for key '{key}': {e}")
                # Fall through to in-memory cache

        # In-memory fallback
        if key in self._fallback_cache:
            del self._fallback_cache[key]
            return True
        return False

    async def exists(self, key: str) -> bool:
        """
        Check if key exists in cache

        Args:
            key: Cache key

        Returns:
            True if key exists
        """
        if self._use_redis and self._client:
            try:
                result = await self._client.exists(key)
                return result > 0
            except Exception as e:
                logger.warning(f"Redis exists failed for key '{key}': {e}")
                # Fall through to in-memory cache

        # In-memory fallback
        return key in self._fallback_cache

    async def get_json(self, key: str) -> Optional[Any]:
        """
        Get JSON value from cache

        Args:
            key: Cache key

        Returns:
            Parsed JSON value or None
        """
        value = await self.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON for key '{key}': {e}")
        return None

    async def set_json(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Set JSON value in cache

        Args:
            key: Cache key
            value: Value to serialize and cache
            ttl: Time-to-live in seconds

        Returns:
            True if successful
        """
        try:
            json_str = json.dumps(value)
            return await self.set(key, json_str, ttl)
        except (TypeError, ValueError) as e:
            logger.warning(f"Failed to serialize JSON for key '{key}': {e}")
            return False

    async def sadd(self, key: str, *members: str) -> int:
        """
        Add members to set

        Args:
            key: Set key
            members: Members to add

        Returns:
            Number of members added
        """
        if self._use_redis and self._client:
            try:
                return await self._client.sadd(key, *members)
            except Exception as e:
                logger.warning(f"Redis sadd failed for key '{key}': {e}")
                # Fall through to in-memory cache

        # In-memory fallback (set stored as list)
        if key not in self._fallback_cache:
            self._fallback_cache[key] = set()
        
        if not isinstance(self._fallback_cache[key], set):
            self._fallback_cache[key] = set()
        
        before_size = len(self._fallback_cache[key])
        self._fallback_cache[key].update(members)
        return len(self._fallback_cache[key]) - before_size

    async def sismember(self, key: str, member: str) -> bool:
        """
        Check if member exists in set

        Args:
            key: Set key
            member: Member to check

        Returns:
            True if member exists
        """
        if self._use_redis and self._client:
            try:
                return await self._client.sismember(key, member)
            except Exception as e:
                logger.warning(f"Redis sismember failed for key '{key}': {e}")
                # Fall through to in-memory cache

        # In-memory fallback
        if key in self._fallback_cache and isinstance(self._fallback_cache[key], set):
            return member in self._fallback_cache[key]
        return False

    async def smembers(self, key: str) -> set[str]:
        """
        Get all members of set

        Args:
            key: Set key

        Returns:
            Set of members
        """
        if self._use_redis and self._client:
            try:
                return await self._client.smembers(key)
            except Exception as e:
                logger.warning(f"Redis smembers failed for key '{key}': {e}")
                # Fall through to in-memory cache

        # In-memory fallback
        if key in self._fallback_cache and isinstance(self._fallback_cache[key], set):
            return self._fallback_cache[key].copy()
        return set()

    async def close(self) -> None:
        """Close Redis connection pool"""
        if self._client:
            await self._client.close()
            self._client = None

        if self._pool:
            await self._pool.disconnect()
            self._pool = None

        logger.info("Redis connection closed")

    @property
    def is_redis_enabled(self) -> bool:
        """Check if Redis is enabled and connected"""
        return self._use_redis


# Global cache instance
_cache_instance: Optional[RedisCache] = None


async def get_cache() -> RedisCache:
    """
    Get or create global cache instance

    Returns:
        RedisCache instance
    """
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = RedisCache()
        await _cache_instance.connect()
    return _cache_instance


async def close_cache() -> None:
    """Close global cache instance"""
    global _cache_instance
    if _cache_instance:
        await _cache_instance.close()
        _cache_instance = None
