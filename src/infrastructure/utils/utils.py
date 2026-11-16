#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared Utilities - Console Encoding and Common Helpers
Centralized utilities to avoid code duplication
"""

import io
import os
import sys
from typing import NoReturn


def setup_console_encoding() -> None:
    """
    Setup Windows console encoding for UTF-8 support
    Call this at the start of every script that outputs Unicode
    """
    if sys.platform == "win32":
        if getattr(sys.stdout, "_opencode_utf8_wrapped", False):
            return
        if not hasattr(sys.stdout, "buffer") or not hasattr(sys.stderr, "buffer"):
            return

        # Fix console encoding
        stdout_wrapper = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
        stderr_wrapper = io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", errors="replace"
        )

        setattr(stdout_wrapper, "_opencode_utf8_wrapped", True)
        setattr(stderr_wrapper, "_opencode_utf8_wrapped", True)

        sys.stdout = stdout_wrapper
        sys.stderr = stderr_wrapper

        # Set console code page to UTF-8
        os.system("chcp 65001 > nul 2>&1")


def exit_with_error(message: str, code: int = 1) -> NoReturn:
    """
    Print error message and exit

    Args:
        message: Error message to display
        code: Exit code (default: 1)
    """
    print(f"\n[ERROR] {message}", file=sys.stderr)
    sys.exit(code)


def print_section(title: str, width: int = 60) -> None:
    """
    Print a formatted section header

    Args:
        title: Section title
        width: Total width of the header
    """
    print("\n" + "=" * width)
    print(title.center(width))
    print("=" * width)


def print_success(message: str) -> None:
    """Print success message with formatting"""
    print(f"\n✓ {message}")


def print_warning(message: str) -> None:
    """Print warning message with formatting"""
    print(f"\n⚠ {message}", file=sys.stderr)


def print_info(message: str) -> None:
    """Print info message with formatting"""
    print(f"\nℹ {message}")
