#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Token Bucket Rate Limiter
Prevents API rate limit errors by controlling request rate
"""

import asyncio
import time
from typing import Optional

from infrastructure.logging.logger import setup_logger

logger = setup_logger(__name__)


class TokenBucketLimiter:
    """
    Token bucket rate limiter for API calls
    Allows burst traffic while maintaining average rate
    """

    def __init__(
        self,
        tokens_per_second: float = 10.0,
        burst_size: Optional[int] = None,
    ) -> None:
        """
        Initialize token bucket limiter

        Args:
            tokens_per_second: Average tokens per second (default: 10)
            burst_size: Max burst tokens (default: 2x tokens_per_second)
        """
        self.tokens_per_second = tokens_per_second
        self.burst_size = burst_size or int(tokens_per_second * 2)
        self.tokens = float(self.burst_size)
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

        logger.info(
            f"Rate limiter initialized: {tokens_per_second} tokens/s, "
            f"burst: {self.burst_size}"
        )

    async def _refill_tokens(self) -> None:
        """Refill tokens based on elapsed time"""
        now = time.monotonic()
        elapsed = now - self.last_update

        # Add tokens based on elapsed time
        new_tokens = elapsed * self.tokens_per_second
        self.tokens = min(self.burst_size, self.tokens + new_tokens)
        self.last_update = now

    async def wait_for_token(self, tokens: int = 1) -> None:
        """
        Wait until tokens are available

        Args:
            tokens: Number of tokens to consume (default: 1)
        """
        async with self._lock:
            while True:
                await self._refill_tokens()

                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return

                # Calculate wait time for next token
                tokens_needed = tokens - self.tokens
                wait_time = tokens_needed / self.tokens_per_second

                logger.debug(
                    f"Rate limit: waiting {wait_time:.2f}s for {tokens} tokens "
                    f"(available: {self.tokens:.2f})"
                )

                # Release lock while waiting
                await asyncio.sleep(wait_time)

    async def try_acquire(self, tokens: int = 1) -> bool:
        """
        Try to acquire tokens without waiting

        Args:
            tokens: Number of tokens to consume (default: 1)

        Returns:
            True if tokens acquired, False otherwise
        """
        async with self._lock:
            await self._refill_tokens()

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True

            return False

    def get_available_tokens(self) -> float:
        """
        Get current available tokens (non-blocking)

        Returns:
            Number of available tokens
        """
        return self.tokens

    def reset(self) -> None:
        """Reset limiter to full burst capacity"""
        self.tokens = float(self.burst_size)
        self.last_update = time.monotonic()
        logger.info("Rate limiter reset")


# Global rate limiter instance
_limiter_instance: Optional[TokenBucketLimiter] = None


def get_rate_limiter(
    tokens_per_second: float = 10.0,
    burst_size: Optional[int] = None,
) -> TokenBucketLimiter:
    """
    Get or create global rate limiter instance

    Args:
        tokens_per_second: Average tokens per second
        burst_size: Max burst tokens

    Returns:
        TokenBucketLimiter instance
    """
    global _limiter_instance
    if _limiter_instance is None:
        _limiter_instance = TokenBucketLimiter(tokens_per_second, burst_size)
    return _limiter_instance
