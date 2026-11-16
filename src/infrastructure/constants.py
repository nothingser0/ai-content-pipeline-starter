"""
Application-wide constants (DEPRECATED)

DEPRECATED: This module is deprecated. Use src.infrastructure.config.settings instead.
Kept for backward compatibility during migration.
"""

import warnings

# Re-export from new settings module
try:
    from infrastructure.config.settings import (
        API_MAX_RETRIES,
        API_TIMEOUT_SECONDS,
        TWEET_MAX_LENGTH,
        VALIDATION_MAX_LENGTH,
    )
except ImportError:
    from src.infrastructure.config.settings import (
        API_MAX_RETRIES,
        API_TIMEOUT_SECONDS,
        TWEET_MAX_LENGTH,
        VALIDATION_MAX_LENGTH,
    )

warnings.warn(
    "infrastructure.constants is deprecated. Use infrastructure.config.settings instead.",
    DeprecationWarning,
    stacklevel=2,
)

# API configuration (kept for backward compatibility)
API_MAX_TOKENS = 4096

# Theme analysis stopwords
# Used for deduplication and similarity detection
THEME_STOPWORDS = {
    "a",
    "about",
    "after",
    "all",
    "and",
    "are",
    "for",
    "from",
    "how",
    "in",
    "into",
    "is",
    "it",
    "its",
    "latest",
    "new",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "trends",
    "tips",
    "underrated",
    "what",
    "when",
    "why",
    "with",
    "you",
    "your",
}

__all__ = [
    "API_MAX_RETRIES",
    "API_TIMEOUT_SECONDS",
    "TWEET_MAX_LENGTH",
    "VALIDATION_MAX_LENGTH",
    "API_MAX_TOKENS",
    "THEME_STOPWORDS",
]
