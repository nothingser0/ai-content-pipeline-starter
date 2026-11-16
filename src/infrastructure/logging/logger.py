#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Centralized Logging Configuration
Structured logging for the entire pipeline
"""

import json
import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

# Create logs directory if not exists
LOGS_DIR = Path(__file__).parent.parent.parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# Log files
LOG_FILE = LOGS_DIR / f"pipeline_{datetime.now().strftime('%Y%m%d')}.log"
ERROR_LOG_FILE = LOGS_DIR / f"errors_{datetime.now().strftime('%Y%m%d')}.log"
JSON_LOG_FILE = LOGS_DIR / f"structured_{datetime.now().strftime('%Y%m%d')}.jsonl"


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging"""

    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add context from record
        if hasattr(record, "request_id"):
            log_data["request_id"] = getattr(record, "request_id")
        if hasattr(record, "account_id"):
            log_data["account_id"] = getattr(record, "account_id")
        if hasattr(record, "content_format"):
            log_data["content_format"] = getattr(record, "content_format")
        if hasattr(record, "duration_ms"):
            log_data["duration_ms"] = getattr(record, "duration_ms")

        # Add exception info
        if record.exc_info and record.exc_info[0] is not None:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info),
            }

        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in [
                "name",
                "msg",
                "args",
                "created",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "thread",
                "threadName",
                "exc_info",
                "exc_text",
                "stack_info",
                "request_id",
                "account_id",
                "content_format",
                "duration_ms",
            ]:
                log_data[key] = value

        return json.dumps(log_data)


class ContextFilter(logging.Filter):
    """Add context information to log records"""

    def filter(self, record: logging.LogRecord) -> bool:
        # Import here to avoid circular dependency
        from src.infrastructure.logging.context import get_context

        context = get_context()
        if context:
            record.request_id = context.get("request_id", "")
            record.account_id = context.get("account_id", "")
            record.content_format = context.get("content_format", "")

        return True


class ColoredFormatter(logging.Formatter):
    """Colored console output for better readability"""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record):
        if sys.platform == "win32":
            # Windows console might not support colors
            return super().format(record)

        color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)


def setup_logger(
    name: str, level: int = logging.INFO, enable_json: bool = False
) -> logging.Logger:
    """
    Setup logger with console and file handlers

    Args:
        name: Logger name (usually __name__)
        level: Logging level (default: INFO)
        enable_json: Enable JSON structured logging (default: False)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # Add context filter
    context_filter = ContextFilter()
    logger.addFilter(context_filter)

    # Determine if production mode (JSON logging)
    # Check ENABLE_JSON_LOGS env var or enable_json parameter
    is_production = (
        os.getenv("ENVIRONMENT", "development") == "production" 
        or os.getenv("ENABLE_JSON_LOGS", "0") == "1"
        or enable_json
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    if is_production:
        console_formatter = JSONFormatter()
    else:
        console_formatter = ColoredFormatter("[%(levelname)s] %(name)s: %(message)s")
    console_handler.setFormatter(console_formatter)

    # File handler with rotation (daily + 10MB size limit)
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)

    # Error file handler (errors only)
    error_handler = logging.handlers.RotatingFileHandler(
        ERROR_LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(file_formatter)

    # JSON structured log handler
    if is_production:
        json_handler = logging.handlers.RotatingFileHandler(
            JSON_LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        json_handler.setLevel(logging.DEBUG)
        json_handler.setFormatter(JSONFormatter())
        logger.addHandler(json_handler)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.addHandler(error_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get configured logger (alias for setup_logger for compatibility)"""
    return setup_logger(name)


# Default logger for quick imports
default_logger = setup_logger("pipeline")
