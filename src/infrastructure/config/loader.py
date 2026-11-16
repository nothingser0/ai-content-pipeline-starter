#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuration loader
Supports both OPENCODE_* and legacy API_* environment variables.
"""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple

from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

# Default config (fallback)
DEFAULT_API_URL: str = "http://localhost:1430/v1"
DEFAULT_API_KEY: str = "enx-default-key"
DEFAULT_MODEL: str = "kiro/claude-sonnet-4.5"

# Weekly content limits (default values)
DEFAULT_WEEKLY_LIMITS = {"Thread": 1, "Single Tweet": 2, "Poll": 2, "Image": 2}

# Model selection by task
MODEL_STRATEGY = {
    "strategist": "kiro/claude-sonnet-4.5-thinking",
    "writer": "kiro/claude-sonnet-4.5",
    "qc_autofix": "kiro/claude-sonnet-4.5",
    "visual": "kiro/claude-sonnet-4.5",
    "engagement": "kiro/claude-sonnet-4.5",
    "default": "kiro/claude-sonnet-4.5",
}

# Alternative models for experimentation
ALTERNATIVE_MODELS = {
    "strategist": ["deepseek-3.2", "glm-5"],
    "writer": ["claude-sonnet-4", "deepseek-3.2"],
    "qc_autofix": ["claude-haiku-4.5", "minimax-m2.5"],
    "visual": ["claude-haiku-4.5", "glm-5"],
    "engagement": ["claude-haiku-4.5", "minimax-m2.5"],
}


@dataclass
class APIConfig:
    """API configuration"""

    base_url: str
    api_key: str


@dataclass
class ModelConfig:
    """Model configuration for different tasks"""

    strategist: str
    writer: str
    qc: str
    visual: str
    engagement: str
    default: str


@dataclass
class WeeklyLimits:
    """Weekly content limits per format"""

    thread: int
    single_tweet: int
    poll: int
    image: int


class ConfigLoader:
    """Load configuration from .env file"""

    def __init__(self, project_root: Optional[Path] = None) -> None:
        self.project_root = project_root or Path(__file__).parent.parent.parent.parent
        self._load_env_file()

    def _load_env_file(self):
        """Load .env file from project root"""
        project_env = self.project_root / ".env"

        if not project_env.exists():
            logger.warning(f".env file not found at {project_env}")
            logger.warning("Using default configuration")
            return

        try:
            from dotenv import load_dotenv

            load_dotenv(project_env, override=True)
            logger.debug(f"Loaded configuration from {project_env}")
        except Exception:
            # Fallback parser if dotenv is not available
            try:
                with open(project_env, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            os.environ[k.strip()] = v.strip().strip("'\"")
                logger.debug(f"Loaded configuration manually from {project_env}")
            except Exception as e:
                logger.error(f"Failed to load .env: {e}")

    def load_api_config(self) -> APIConfig:
        """Load API configuration from environment variables"""
        api_url = (
            os.getenv("OPENCODE_BASE_URL")
            or os.getenv("API_BASE_URL")
            or DEFAULT_API_URL
        )
        api_key = (
            os.getenv("OPENCODE_API_KEY") or os.getenv("API_KEY") or DEFAULT_API_KEY
        )

        return APIConfig(base_url=api_url, api_key=api_key)

    def load_model_config(self) -> ModelConfig:
        """Load model configuration from environment variables"""
        return ModelConfig(
            strategist=os.getenv("MODEL_STRATEGIST", MODEL_STRATEGY["strategist"]),
            writer=os.getenv("MODEL_WRITER", MODEL_STRATEGY["writer"]),
            qc=os.getenv("MODEL_QC", MODEL_STRATEGY["qc_autofix"]),
            visual=os.getenv("MODEL_VISUAL", MODEL_STRATEGY["visual"]),
            engagement=os.getenv("MODEL_ENGAGEMENT", MODEL_STRATEGY["engagement"]),
            default=os.getenv("MODEL_DEFAULT", MODEL_STRATEGY["default"]),
        )

    def load_weekly_limits(self) -> WeeklyLimits:
        """Load weekly content limits from environment variables"""

        def get_int_env(key: str, default: int) -> int:
            value = os.getenv(key)
            if value:
                try:
                    return int(value)
                except ValueError:
                    return default
            return default

        return WeeklyLimits(
            thread=get_int_env("WEEKLY_LIMIT_THREAD", DEFAULT_WEEKLY_LIMITS["Thread"]),
            single_tweet=get_int_env(
                "WEEKLY_LIMIT_SINGLE_TWEET", DEFAULT_WEEKLY_LIMITS["Single Tweet"]
            ),
            poll=get_int_env("WEEKLY_LIMIT_POLL", DEFAULT_WEEKLY_LIMITS["Poll"]),
            image=get_int_env("WEEKLY_LIMIT_IMAGE", DEFAULT_WEEKLY_LIMITS["Image"]),
        )


# Global instance
_config_loader: Optional[ConfigLoader] = None


def get_config_loader() -> ConfigLoader:
    """Get global config loader instance"""
    global _config_loader
    if _config_loader is None:
        _config_loader = ConfigLoader()
    return _config_loader


def get_model_for_task(task: str) -> str:
    """
    Get optimal model for specific task

    Args:
        task: Task name (strategist, writer, qc_autofix, visual, engagement)

    Returns:
        Model name for the task
    """
    env_key = f"MODEL_{task.upper()}"
    env_value = os.getenv(env_key)
    if env_value:
        return env_value
    return MODEL_STRATEGY.get(task, MODEL_STRATEGY["default"])


@lru_cache(maxsize=1)
def load_api_config() -> Tuple[str, str, str]:
    """
    Load API configuration from project .env

    Returns:
        tuple: (api_url, api_key, model)
    """
    loader = get_config_loader()
    api_config = loader.load_api_config()
    model_config = loader.load_model_config()

    return api_config.base_url, api_config.api_key, model_config.default


@lru_cache(maxsize=1)
def load_weekly_limits() -> dict[str, int]:
    """
    Load weekly content limits from environment variables

    Returns:
        dict: Format name -> weekly limit
    """
    loader = get_config_loader()
    limits = loader.load_weekly_limits()

    return {
        "Thread": limits.thread,
        "Single Tweet": limits.single_tweet,
        "Poll": limits.poll,
        "Image": limits.image,
    }


# Load config once when module is imported (for backward compatibility)
API_URL, API_KEY, MODEL = load_api_config()
