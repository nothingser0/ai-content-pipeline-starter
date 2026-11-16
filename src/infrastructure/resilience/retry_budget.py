#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Retry Budget Tracker - Prevent silent failures from retry exhaustion

Tracks per-account daily retry budgets with Redis storage and in-memory fallback.
Auto-resets at midnight. Thread-safe with asyncio.Lock.
"""

import asyncio
import os
from datetime import datetime, timezone
from typing import Dict, Optional

from infrastructure.logging.logger import setup_logger

logger = setup_logger(__name__)


class RetryBudgetTracker:
    """
    Track retry budget per account to prevent silent failures.
    
    Features:
    - Per-account daily limits (default: 10 retries/day)
    - Redis storage with in-memory fallback
    - Auto-reset at midnight UTC
    - Thread-safe with asyncio.Lock
    """

    def __init__(
        self,
        daily_limit: Optional[int] = None,
        redis_client=None,
        timezone_offset: int = 0
    ):
        """
        Initialize retry budget tracker.
        
        Args:
            daily_limit: Max retries per account per day (default: 10)
            redis_client: Optional Redis client for persistence
            timezone_offset: Hours offset from UTC for daily reset (default: 0)
        """
        self.daily_limit = daily_limit or int(os.getenv("RETRY_BUDGET_DAILY", "10"))
        self.redis_client = redis_client
        self.timezone_offset = timezone_offset
        
        # In-memory fallback storage: {account_id: {date: count}}
        self._memory_store: Dict[str, Dict[str, int]] = {}
        self._lock = asyncio.Lock()
        
        # Track if Redis is available
        self._redis_available = redis_client is not None
        
        logger.info(
            f"RetryBudgetTracker initialized: daily_limit={self.daily_limit}, "
            f"redis={'enabled' if self._redis_available else 'disabled'}"
        )

    def _get_current_date(self) -> str:
        """Get current date string for budget key (YYYY-MM-DD)."""
        now = datetime.now(timezone.utc)
        # Apply timezone offset
        if self.timezone_offset != 0:
            from datetime import timedelta
            now = now + timedelta(hours=self.timezone_offset)
        return now.strftime("%Y-%m-%d")

    def _get_redis_key(self, account_id: str, date: str) -> str:
        """Generate Redis key for account budget."""
        return f"retry_budget:{account_id}:{date}"

    async def _get_count_from_redis(self, account_id: str, date: str) -> Optional[int]:
        """Get retry count from Redis."""
        if not self._redis_available:
            return None
        
        try:
            key = self._get_redis_key(account_id, date)
            value = await self.redis_client.get(key)
            return int(value) if value else 0
        except Exception as e:
            logger.warning(f"Redis get failed for {account_id}: {e}")
            return None

    async def _set_count_in_redis(self, account_id: str, date: str, count: int) -> bool:
        """Set retry count in Redis with 24h expiry."""
        if not self._redis_available:
            return False
        
        try:
            key = self._get_redis_key(account_id, date)
            # Set with 24h expiry (auto-cleanup old dates)
            await self.redis_client.setex(key, 86400, count)
            return True
        except Exception as e:
            logger.warning(f"Redis set failed for {account_id}: {e}")
            return False

    async def _get_count_from_memory(self, account_id: str, date: str) -> int:
        """Get retry count from in-memory store."""
        return self._memory_store.get(account_id, {}).get(date, 0)

    async def _set_count_in_memory(self, account_id: str, date: str, count: int):
        """Set retry count in in-memory store."""
        if account_id not in self._memory_store:
            self._memory_store[account_id] = {}
        self._memory_store[account_id][date] = count

    async def check_budget(self, account_id: str) -> bool:
        """
        Check if account has retry budget remaining.
        
        Args:
            account_id: Account identifier
            
        Returns:
            True if budget available, False if exhausted
        """
        async with self._lock:
            date = self._get_current_date()
            
            # Try Redis first
            count = await self._get_count_from_redis(account_id, date)
            
            # Fallback to memory
            if count is None:
                count = await self._get_count_from_memory(account_id, date)
            
            remaining = self.daily_limit - count
            has_budget = remaining > 0
            
            logger.debug(
                f"Budget check for {account_id}: used={count}/{self.daily_limit}, "
                f"remaining={remaining}, available={has_budget}"
            )
            
            return has_budget

    async def consume_retry(self, account_id: str) -> int:
        """
        Consume one retry from account budget.
        
        Args:
            account_id: Account identifier
            
        Returns:
            Remaining budget after consumption
        """
        async with self._lock:
            date = self._get_current_date()
            
            # Try Redis first
            count = await self._get_count_from_redis(account_id, date)
            
            # Fallback to memory
            if count is None:
                count = await self._get_count_from_memory(account_id, date)
            
            # Increment count
            new_count = count + 1
            
            # Update storage (try Redis, fallback to memory)
            redis_success = await self._set_count_in_redis(account_id, date, new_count)
            if not redis_success:
                await self._set_count_in_memory(account_id, date, new_count)
            
            remaining = self.daily_limit - new_count
            
            logger.info(
                f"Retry consumed for {account_id}: used={new_count}/{self.daily_limit}, "
                f"remaining={remaining}"
            )
            
            return remaining

    async def get_remaining(self, account_id: str) -> int:
        """
        Get remaining retry budget for account.
        
        Args:
            account_id: Account identifier
            
        Returns:
            Number of retries remaining
        """
        async with self._lock:
            date = self._get_current_date()
            
            # Try Redis first
            count = await self._get_count_from_redis(account_id, date)
            
            # Fallback to memory
            if count is None:
                count = await self._get_count_from_memory(account_id, date)
            
            remaining = self.daily_limit - count
            return max(0, remaining)

    async def reset_daily(self):
        """
        Reset all daily budgets (called at midnight).
        
        Note: Redis keys auto-expire after 24h, so only need to clear memory.
        """
        async with self._lock:
            date = self._get_current_date()
            
            # Clear old dates from memory (keep only current date)
            for account_id in list(self._memory_store.keys()):
                old_dates = [d for d in self._memory_store[account_id].keys() if d != date]
                for old_date in old_dates:
                    del self._memory_store[account_id][old_date]
            
            logger.info(f"Daily retry budgets reset for date: {date}")

    async def get_all_budgets(self) -> Dict[str, int]:
        """
        Get remaining budgets for all accounts (for monitoring).
        
        Returns:
            Dict mapping account_id to remaining budget
        """
        async with self._lock:
            budgets = {}
            
            # Get all accounts from memory store
            for account_id in self._memory_store.keys():
                remaining = await self.get_remaining(account_id)
                budgets[account_id] = remaining
            
            return budgets


# Singleton instance (shared across all API clients)
_retry_budget_tracker: Optional[RetryBudgetTracker] = None


def get_retry_budget_tracker(
    daily_limit: Optional[int] = None,
    redis_client=None,
    timezone_offset: int = 0
) -> RetryBudgetTracker:
    """
    Get or create singleton retry budget tracker.
    
    Args:
        daily_limit: Max retries per account per day
        redis_client: Optional Redis client
        timezone_offset: Hours offset from UTC
        
    Returns:
        Shared RetryBudgetTracker instance
    """
    global _retry_budget_tracker
    
    if _retry_budget_tracker is None:
        _retry_budget_tracker = RetryBudgetTracker(
            daily_limit=daily_limit,
            redis_client=redis_client,
            timezone_offset=timezone_offset
        )
    
    return _retry_budget_tracker
