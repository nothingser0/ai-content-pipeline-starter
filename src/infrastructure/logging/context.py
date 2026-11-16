#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Logging Context Management
Thread-local storage for request context
"""

import threading
from typing import Any, Dict, Optional

# Thread-local storage
_context = threading.local()


def set_context(
    request_id: Optional[str] = None,
    account_id: Optional[str] = None,
    content_format: Optional[str] = None,
    **kwargs: Any,
) -> None:
    """
    Set logging context for current thread

    Args:
        request_id: Unique request identifier
        account_id: Account being processed
        content_format: Content format (Thread, Single Tweet, etc.)
        **kwargs: Additional context fields
    """
    if not hasattr(_context, "data"):
        _context.data = {}

    if request_id is not None:
        _context.data["request_id"] = request_id
    if account_id is not None:
        _context.data["account_id"] = account_id
    if content_format is not None:
        _context.data["content_format"] = content_format

    # Add any extra fields
    _context.data.update(kwargs)


def get_context() -> Dict[str, Any]:
    """
    Get current logging context

    Returns:
        Dictionary of context fields
    """
    if not hasattr(_context, "data"):
        return {}
    return _context.data.copy()


def clear_context() -> None:
    """Clear logging context for current thread"""
    if hasattr(_context, "data"):
        _context.data.clear()


def update_context(**kwargs: Any) -> None:
    """
    Update specific context fields

    Args:
        **kwargs: Fields to update
    """
    if not hasattr(_context, "data"):
        _context.data = {}
    _context.data.update(kwargs)
