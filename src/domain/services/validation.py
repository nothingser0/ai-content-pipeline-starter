#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Input Validation and Sanitization
Prevent injection attacks and validate user input
"""

import re
from typing import Optional

from infrastructure.constants import VALIDATION_MAX_LENGTH
from infrastructure.logging.logger import setup_logger

logger = setup_logger(__name__)


class ValidationError(Exception):
    """Custom exception for validation errors"""

    pass


def sanitize_text(text: str, max_length: int = VALIDATION_MAX_LENGTH) -> str:
    """
    Sanitize user text input

    Args:
        text: Raw user input
        max_length: Maximum allowed length

    Returns:
        Sanitized text

    Raises:
        ValidationError: If input is invalid
    """
    if not isinstance(text, str):
        raise ValidationError("Input must be a string")

    # Strip whitespace
    text = text.strip()

    # Check length
    if len(text) == 0:
        raise ValidationError("Input cannot be empty")

    if len(text) > max_length:
        raise ValidationError(f"Input too long (max {max_length} characters)")

    # Remove null bytes
    text = text.replace("\x00", "")

    # Normalize newlines
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    return text


def validate_topic(topic: str) -> str:
    """
    Validate and sanitize topic input

    Args:
        topic: User-provided topic

    Returns:
        Validated topic

    Raises:
        ValidationError: If topic is invalid
    """
    topic = sanitize_text(topic, max_length=500)

    # Check minimum length
    if len(topic) < 3:
        raise ValidationError("Topic too short (minimum 3 characters)")

    # Warn about suspicious patterns
    suspicious_patterns = [
        r"<script",
        r"javascript:",
        r"onerror=",
        r"onclick=",
        r"\$\{.*\}",  # Template injection
    ]

    for pattern in suspicious_patterns:
        if re.search(pattern, topic, re.IGNORECASE):
            logger.warning(f"Suspicious pattern detected in topic: {pattern}")
            # Remove the pattern
            topic = re.sub(pattern, "", topic, flags=re.IGNORECASE)

    return topic


def validate_context(context: str) -> str:
    """
    Validate and sanitize context input

    Args:
        context: User-provided context

    Returns:
        Validated context

    Raises:
        ValidationError: If context is invalid
    """
    # Context is optional, empty is OK
    if not context or not context.strip():
        return ""

    return sanitize_text(context, max_length=2000)


def validate_pillar(pillar: str) -> str:
    """
    Validate content pillar selection

    Args:
        pillar: User-selected pillar

    Returns:
        Validated pillar

    Raises:
        ValidationError: If pillar is invalid
    """
    valid_pillars = [
        "airdrop",
        "defi",
        "nft",
        "blockchain",
        "crypto",
        "web3",
        "general",
    ]

    pillar = pillar.lower().strip()

    if pillar not in valid_pillars:
        raise ValidationError(
            f"Invalid pillar. Must be one of: {', '.join(valid_pillars)}"
        )

    return pillar


def validate_format_choice(format_choice: str) -> str:
    """
    Validate content format selection

    Args:
        format_choice: User-selected format

    Returns:
        Validated format

    Raises:
        ValidationError: If format is invalid
    """
    valid_formats = ["Single Tweet", "Thread", "Poll", "Image"]

    # Normalize
    format_choice = format_choice.strip()

    # Case-insensitive match
    for valid_format in valid_formats:
        if format_choice.lower() == valid_format.lower():
            return valid_format

    raise ValidationError(f"Invalid format. Must be one of: {', '.join(valid_formats)}")


def validate_angle_selection(selection: str, max_angles: int = 10) -> int:
    """
    Validate angle selection input

    Args:
        selection: User input (number or '0' for auto)
        max_angles: Maximum number of angles

    Returns:
        Validated selection as integer

    Raises:
        ValidationError: If selection is invalid
    """
    selection = selection.strip()

    # Check if numeric
    if not selection.isdigit():
        raise ValidationError("Selection must be a number")

    num = int(selection)

    # Validate range
    if num < 0 or num > max_angles:
        raise ValidationError(f"Selection must be between 0 and {max_angles}")

    return num


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal

    Args:
        filename: User-provided filename

    Returns:
        Safe filename

    Raises:
        ValidationError: If filename is invalid
    """
    if not filename:
        raise ValidationError("Filename cannot be empty")

    # Remove path separators
    filename = filename.replace("/", "_").replace("\\", "_")

    # Remove dangerous characters
    filename = re.sub(r'[<>:"|?*\x00-\x1f]', "", filename)

    # Remove leading/trailing dots and spaces
    filename = filename.strip(". ")

    # Check length
    if len(filename) == 0:
        raise ValidationError("Filename invalid after sanitization")

    if len(filename) > 255:
        filename = filename[:255]

    return filename
