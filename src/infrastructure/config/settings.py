#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Centralized configuration constants for the content pipeline.

This module consolidates all magic numbers and configuration values
to enable easy A/B testing and configuration management.
"""

from typing import Final


# Tweet and Content Limits
TWEET_MAX_LENGTH: Final[int] = 280
"""Maximum character length for a single tweet."""

THREAD_MIN_TWEETS: Final[int] = 8
"""Minimum number of tweets in a thread."""

THREAD_MAX_TWEETS: Final[int] = 12
"""Maximum number of tweets in a thread."""

POLL_OPTIONS_COUNT: Final[int] = 4
"""Number of options in a poll."""


# Deduplication Settings
DEDUP_SIMILARITY_THRESHOLD: Final[float] = 0.7
"""Similarity threshold for content deduplication (0.0-1.0).
Content with similarity >= this value is considered duplicate."""


# Quality Control Settings
QC_PASS_THRESHOLD: Final[int] = 8
"""Minimum QC score (0-10) required for content to pass quality control."""

QC_AUTOFIX_THRESHOLD: Final[int] = 8
"""QC score threshold below which autofix is attempted."""


# API Settings
API_MAX_RETRIES: Final[int] = 3
"""Maximum number of retry attempts for API calls."""

API_TIMEOUT_SECONDS: Final[int] = 180
"""Timeout in seconds for API requests."""

API_TEMPERATURE: Final[float] = 0.7
"""Default temperature for LLM generation."""


# Validation Settings
VALIDATION_MAX_LENGTH: Final[int] = 10000
"""Maximum character length for text validation."""


# Logging Settings
LOG_MAX_BYTES: Final[int] = 10 * 1024 * 1024
"""Maximum size in bytes for log files before rotation (10 MB)."""

LOG_BACKUP_COUNT: Final[int] = 5
"""Number of backup log files to keep."""


# Content Generation Settings
CONTENT_ANGLES_COUNT: Final[int] = 10
"""Number of content angles to generate in strategy phase."""

SHORT_TOKEN_MIN_LENGTH: Final[int] = 3
"""Minimum token length for deduplication (tokens <= this are filtered)."""

WHITESPACE_CLEANUP_THRESHOLD: Final[int] = 3
"""Maximum consecutive newlines allowed before cleanup."""
