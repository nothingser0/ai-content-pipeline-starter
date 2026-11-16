#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared Utilities - API Client with Retry Logic (Async)
Centralized API calls with exponential backoff using aiohttp
"""

import asyncio
import json
import os
import time
from typing import Optional

import aiohttp

from domain.exceptions import CircuitBreakerOpenError, RetryBudgetExhaustedError
from infrastructure.constants import API_MAX_RETRIES, API_MAX_TOKENS, API_TIMEOUT_SECONDS
from infrastructure.logging.logger import setup_logger
from infrastructure.monitoring.metrics import record_api_call_duration, record_api_error
# Rate limiter removed
# from infrastructure.ratelimit.limiter import TokenBucketLimiter
from infrastructure.resilience.circuit_breaker import get_circuit_breaker
from infrastructure.resilience.retry_budget import get_retry_budget_tracker

logger = setup_logger(__name__)


class APIError(Exception):
    """Custom exception for API errors"""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"API Error {status_code}: {message}")


class APIClient:
    """
    Reusable async API client with retry logic and exponential backoff
    """

    def __init__(
        self, base_url: str, api_key: str, max_retries: int = API_MAX_RETRIES, timeout: int = API_TIMEOUT_SECONDS
    ) -> None:
        """
        Initialize API client

        Args:
            base_url: API base URL
            api_key: API authentication key
            max_retries: Maximum retry attempts (default: 3)
            timeout: Request timeout in seconds (default: 180)
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.max_retries = max_retries
        self.timeout = timeout
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Rate limiter removed - no throttling
        # rate_limit = float(os.getenv("API_RATE_LIMIT", "10.0"))
        # burst_size = int(os.getenv("API_BURST_SIZE", str(int(rate_limit * 2))))
        # self._rate_limiter = TokenBucketLimiter(rate_limit, burst_size)
        
        # Circuit breaker (shared singleton, opt-in via env)
        self._circuit_breaker_enabled = os.getenv("ENABLE_CIRCUIT_BREAKER", "0") == "1"
        if self._circuit_breaker_enabled:
            self._circuit_breaker = get_circuit_breaker()
            logger.info("Circuit breaker enabled for API client")
        
        # Retry budget tracker (shared singleton, opt-in via env)
        self._retry_budget_enabled = os.getenv("ENABLE_RETRY_BUDGET", "0") == "1"
        if self._retry_budget_enabled:
            self._retry_budget_tracker = get_retry_budget_tracker()
            logger.info("Retry budget tracker enabled for API client")

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session with connection pooling"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            # Connection pooling: max 100 concurrent connections
            connector = aiohttp.TCPConnector(limit=100, limit_per_host=30)
            self._session = aiohttp.ClientSession(
                headers=self.headers,
                timeout=timeout,
                connector=connector
            )
        return self._session

    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff delay"""
        return min(2**attempt, 60)  # Max 60 seconds

    def _extract_content_robust(self, result: dict) -> Optional[str]:
        """
        Try multiple field paths to extract content from API response.
        Handles different provider response formats.
        """
        # Standard OpenAI format
        if "choices" in result:
            choices = result["choices"]
            if choices and len(choices) > 0:
                choice = choices[0]
                # Try message.content (standard)
                if "message" in choice and "content" in choice["message"]:
                    return choice["message"]["content"]
                # Try text field (some providers)
                if "text" in choice:
                    return choice["text"]
                # Try content directly in choice
                if "content" in choice:
                    return choice["content"]
        
        # Alternative top-level fields
        for field in ["content", "text", "output", "response", "completion"]:
            if field in result and result[field]:
                return result[field]
        
        return None

    async def _parse_response(self, response: aiohttp.ClientResponse) -> Optional[str]:
        """
        Parse API response based on Content-Type header.
        Supports: JSON, SSE (text/event-stream), streaming, and plain text.
        
        Args:
            response: aiohttp response object
            
        Returns:
            Extracted content string or None
        """
        content_type = response.headers.get("Content-Type", "").lower()
        transfer_encoding = response.headers.get("Transfer-Encoding", "")
        
        # DEBUG: Log response metadata for troubleshooting empty responses
        logger.debug(
            f"Response metadata - Status: {response.status}, "
            f"Content-Type: '{content_type}', "
            f"Transfer-Encoding: '{transfer_encoding}'"
        )
        
        # SSE (Server-Sent Events) format
        if "text/event-stream" in content_type:
            logger.debug("Detected SSE format, parsing event stream")
            content_parts = []
            async for line in response.content:
                line_str = line.decode('utf-8').strip()
                if line_str.startswith("data: "):
                    data = line_str[6:]  # Remove "data: " prefix
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta_content = (
                            chunk.get("choices", [{}])[0]
                            .get("delta", {})
                            .get("content", "")
                        )
                        if delta_content:
                            content_parts.append(delta_content)
                    except json.JSONDecodeError:
                        continue
            return "".join(content_parts) if content_parts else None
        
        # Plain text format
        elif "text/plain" in content_type:
            logger.debug("Detected plain text format")
            return await response.text()
        
        # Default: JSON format (application/json or unspecified, handles Transfer-Encoding: chunked)
        else:
            logger.debug("Using default JSON format")
            try:
                result = await response.json()
                content = self._extract_content_robust(result)
                if content:
                    return content
                logger.warning(
                    f"Empty content extracted. Response structure: "
                    f"{json.dumps(result, indent=2)[:500]}"
                )
                return content
            except (json.JSONDecodeError, aiohttp.ContentTypeError):
                # Fallback: Read full text and try parsing
                raw_text = await response.text()
                try:
                    result = json.loads(raw_text)
                    return self._extract_content_robust(result)
                except Exception:
                    # Check if it was streaming ndjson
                    content_parts = []
                    for line in raw_text.splitlines():
                        line = line.strip()
                        if line.startswith("data: "):
                            line = line[6:]
                        if not line or line == "[DONE]":
                            continue
                        try:
                            cj = json.loads(line)
                            delta = cj.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if delta:
                                content_parts.append(delta)
                            else:
                                sc = self._extract_content_robust(cj)
                                if sc:
                                    content_parts.append(sc)
                        except Exception:
                            continue
                    return "".join(content_parts) if content_parts else raw_text
            except (KeyError, IndexError) as e:
                logger.error(f"Failed to extract from JSON response: {e}")
                return None

    async def call_chat_completion(
        self,
        model: str,
        messages: list,
        max_tokens: int = API_MAX_TOKENS,
        temperature: float = 0.8,
        account_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Call chat completion API with retry logic

        Args:
            model: Model name
            messages: List of message dicts
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            account_id: Account identifier for retry budget tracking

        Returns:
            Generated content or None on failure

        Raises:
            APIError: On non-retryable errors
            CircuitBreakerOpenError: When circuit breaker is OPEN
            RetryBudgetExhaustedError: When retry budget exhausted
        """
        # Check circuit breaker before making request
        if self._circuit_breaker_enabled:
            if await self._circuit_breaker.is_open():
                logger.warning("Circuit breaker is OPEN - rejecting API request")
                raise CircuitBreakerOpenError("API circuit breaker is OPEN")
        
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            # "stream": False,  # Causes empty responses - API doesn't support this parameter
        }

        last_error = None
        start_time = time.time()
        session = await self._get_session()

        for attempt in range(self.max_retries):
            try:
                # Rate limiting removed
                # await self._rate_limiter.wait_for_token()
                
                logger.debug(f"API call attempt {attempt + 1}/{self.max_retries}")

                async with session.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                ) as response:
                    # Success
                    if response.status == 200:
                        content = await self._parse_response(response)

                        if not content:
                            logger.warning("Empty response from API")
                            # Record failure for circuit breaker
                            if self._circuit_breaker_enabled:
                                await self._circuit_breaker.record_failure()
                            return None

                        logger.debug("API call successful")

                        # Track performance
                        elapsed = time.time() - start_time
                        record_api_call_duration("openai", model, elapsed)
                        
                        # Record success for circuit breaker
                        if self._circuit_breaker_enabled:
                            await self._circuit_breaker.record_success()

                        return content

                    # Rate limit - always retry
                    elif response.status == 429:
                        retry_after = int(
                            response.headers.get(
                                "Retry-After", self._calculate_backoff(attempt)
                            )
                        )
                        logger.warning(f"Rate limited. Retrying after {retry_after}s")
                        record_api_error("openai", "rate_limit")
                        await asyncio.sleep(retry_after)
                        continue

                    # Server errors - retry
                    elif 500 <= response.status < 600:
                        # Check retry budget before retrying
                        if self._retry_budget_enabled and account_id:
                            has_budget = await self._retry_budget_tracker.check_budget(account_id)
                            if not has_budget:
                                remaining = await self._retry_budget_tracker.get_remaining(account_id)
                                logger.error(
                                    f"Retry budget exhausted for {account_id}. "
                                    f"Remaining: {remaining}"
                                )
                                raise RetryBudgetExhaustedError(account_id, remaining)
                            
                            # Consume retry from budget
                            remaining = await self._retry_budget_tracker.consume_retry(account_id)
                            logger.info(
                                f"Retry consumed for {account_id}. Remaining: {remaining}"
                            )
                        
                        backoff = self._calculate_backoff(attempt)
                        logger.warning(
                            f"Server error {response.status}. Retrying after {backoff}s"
                        )
                        record_api_error("openai", "server_error")
                        # Record failure for circuit breaker
                        if self._circuit_breaker_enabled:
                            await self._circuit_breaker.record_failure()
                        await asyncio.sleep(backoff)
                        continue

                    # Client errors - don't retry
                    else:
                        error_msg = await response.text()
                        logger.error(f"API error {response.status}: {error_msg}")
                        record_api_error("openai", "client_error")
                        # Record failure for circuit breaker
                        if self._circuit_breaker_enabled:
                            await self._circuit_breaker.record_failure()
                        raise APIError(response.status, error_msg)

            except asyncio.TimeoutError:
                # Check retry budget before retrying
                if self._retry_budget_enabled and account_id:
                    has_budget = await self._retry_budget_tracker.check_budget(account_id)
                    if not has_budget:
                        remaining = await self._retry_budget_tracker.get_remaining(account_id)
                        logger.error(
                            f"Retry budget exhausted for {account_id}. Remaining: {remaining}"
                        )
                        raise RetryBudgetExhaustedError(account_id, remaining)
                    
                    # Consume retry from budget
                    remaining = await self._retry_budget_tracker.consume_retry(account_id)
                    logger.info(f"Retry consumed for {account_id}. Remaining: {remaining}")
                
                backoff = self._calculate_backoff(attempt)
                logger.warning(f"Request timeout. Retrying after {backoff}s")
                record_api_error("openai", "timeout")
                # Record failure for circuit breaker
                if self._circuit_breaker_enabled:
                    await self._circuit_breaker.record_failure()
                await asyncio.sleep(backoff)
                last_error = "Request timeout"
                continue

            except aiohttp.ClientError as e:
                # Check retry budget before retrying
                if self._retry_budget_enabled and account_id:
                    has_budget = await self._retry_budget_tracker.check_budget(account_id)
                    if not has_budget:
                        remaining = await self._retry_budget_tracker.get_remaining(account_id)
                        logger.error(
                            f"Retry budget exhausted for {account_id}. Remaining: {remaining}"
                        )
                        raise RetryBudgetExhaustedError(account_id, remaining)
                    
                    # Consume retry from budget
                    remaining = await self._retry_budget_tracker.consume_retry(account_id)
                    logger.info(f"Retry consumed for {account_id}. Remaining: {remaining}")
                
                backoff = self._calculate_backoff(attempt)
                logger.warning(f"Connection error: {e}. Retrying after {backoff}s")
                record_api_error("openai", "connection_error")
                # Record failure for circuit breaker
                if self._circuit_breaker_enabled:
                    await self._circuit_breaker.record_failure()
                await asyncio.sleep(backoff)
                last_error = str(e)
                continue

            except APIError:
                # Don't retry client errors
                raise
            
            except CircuitBreakerOpenError:
                # Don't retry when circuit is open
                raise
            
            except RetryBudgetExhaustedError:
                # Don't retry when budget exhausted
                raise

            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                record_api_error("openai", "unknown_error")
                # Record failure for circuit breaker
                if self._circuit_breaker_enabled:
                    await self._circuit_breaker.record_failure()
                last_error = str(e)
                break

        # All retries exhausted
        logger.error(
            f"API call failed after {self.max_retries} attempts. Last error: {last_error}"
        )

        # Track failure
        elapsed = time.time() - start_time
        record_api_call_duration("openai", model, elapsed)
        
        # Record failure for circuit breaker
        if self._circuit_breaker_enabled:
            await self._circuit_breaker.record_failure()

        return None

    async def close(self):
        """Close session"""
        if self._session and not self._session.closed:
            await self._session.close()
