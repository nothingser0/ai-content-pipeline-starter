#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Custom exception classes for the content pipeline.

Provides specific exception types for better error handling and debugging.
"""


class PipelineError(Exception):
    """Base exception for all pipeline errors."""

    pass


class APIError(PipelineError):
    """Raised when API calls fail (network, timeout, rate limit, etc.)."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ConfigError(PipelineError):
    """Raised when configuration is invalid or missing."""

    pass


class ValidationError(PipelineError):
    """Raised when content validation fails."""

    pass


class DeduplicationError(PipelineError):
    """Raised when deduplication process fails."""

    pass


class QCError(PipelineError):
    """Raised when quality control checks fail."""

    pass


class FormatError(PipelineError):
    """Raised when content format is invalid."""

    pass


class AccountError(PipelineError):
    """Raised when account configuration or loading fails."""

    pass


class CircuitBreakerOpenError(PipelineError):
    """Raised when circuit breaker is OPEN (API failing)."""

    pass


class RetryBudgetExhaustedError(PipelineError):
    """Raised when account retry budget is exhausted."""

    def __init__(self, account_id: str, remaining: int = 0):
        self.account_id = account_id
        self.remaining = remaining
        super().__init__(
            f"Retry budget exhausted for account {account_id}. "
            f"Remaining: {remaining}. Daily limit will reset at midnight."
        )
