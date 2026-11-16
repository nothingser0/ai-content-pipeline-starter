#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Model Router with Fallback System
Simple per-task routing: strategist, writer, visual, engagement, qc
Each task has: Primary (Utama) → FB1 → FB2
"""

import os
from dataclasses import dataclass
from typing import Dict, List, Optional

from infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ModelConfig:
    """Model configuration with fallback chain"""
    primary: str  # Utama
    fallback1: str  # FB1
    fallback2: str  # FB2


class ModelRouter:
    """
    Routes model requests with automatic fallback per task
    Supports: strategist, writer, visual, engagement, qc
    """

    def __init__(self):
        """Initialize model router with configurations from environment"""
        self._configs: Dict[str, ModelConfig] = {}
        self._load_configs()

    def _load_configs(self):
        """Load task configurations from environment variables"""
        try:
            from infrastructure.config.loader import load_api_config
            load_api_config()
        except Exception:
            pass
        
        # STRATEGIST - Ideation & Strategy (10 angles + value scoring)
        self._configs["strategist"] = ModelConfig(
            primary=os.getenv("MODEL_STRATEGIST_PRIMARY", "ag/gemini-3-flash"),
            fallback1=os.getenv("MODEL_STRATEGIST_FB1", "groq/qwen/qwen3-32b"),
            fallback2=os.getenv("MODEL_STRATEGIST_FB2", "cerebras/zai-glm-4.7"),
        )

        # WRITER - Content Generation (HIGH VOLUME)
        # Note: Groq rotation handled automatically by 9router backend
        # No manual rotation needed - 9router distributes across multiple accounts
        self._configs["writer"] = ModelConfig(
            primary=os.getenv("MODEL_WRITER_PRIMARY", "groq/openai/gpt-oss-120b"),
            fallback1=os.getenv("MODEL_WRITER_FB1", "cerebras/gpt-oss-120b"),
            fallback2=os.getenv("MODEL_WRITER_FB2", "mistral/mistral-small-latest"),
        )

        # VISUAL - Visual Brief Generation
        self._configs["visual"] = ModelConfig(
            primary=os.getenv("MODEL_VISUAL_PRIMARY", "mistral/mistral-small-latest"),
            fallback1=os.getenv("MODEL_VISUAL_FB1", "gemini/gemma-4-31b-it"),
            fallback2=os.getenv("MODEL_VISUAL_FB2", "groq/meta-llama/llama-4-scout-17b-16e-instruct"),
        )

        # ENGAGEMENT - Engagement Strategy
        self._configs["engagement"] = ModelConfig(
            primary=os.getenv("MODEL_ENGAGEMENT_PRIMARY", "groq/meta-llama/llama-4-scout-17b-16e-instruct"),
            fallback1=os.getenv("MODEL_ENGAGEMENT_FB1", "groq/llama-3.3-70b-versatile"),
            fallback2=os.getenv("MODEL_ENGAGEMENT_FB2", "mistral/mistral-small-latest"),
        )

        # QC - Quality Control & Review
        # FB2 uses Kiro premium as last-resort safety net (should rarely trigger at current volume)
        self._configs["qc"] = ModelConfig(
            primary=os.getenv("MODEL_QC_PRIMARY", "oc/deepseek-v4-flash-free"),
            fallback1=os.getenv("MODEL_QC_FB1", "mistral/mistral-small-latest"),
            fallback2=os.getenv("MODEL_QC_FB2", "kr/claude-haiku-4.5-thinking-agentic"),
        )

        logger.info(f"Loaded {len(self._configs)} task configurations: {list(self._configs.keys())}")

    def get_model_chain(self, task_name: str) -> List[str]:
        """
        Get complete fallback chain for a task
        
        Args:
            task_name: Task name (strategist, writer, visual, engagement, qc)
            
        Returns:
            List of models in order: [primary, fallback1, fallback2]
        """
        task_key = task_name.lower()
        config = self._configs.get(task_key)
        
        if not config:
            logger.error(f"No configuration found for task: {task_name}")
            # Fallback to legacy env vars
            legacy_model = os.getenv(f"MODEL_{task_name.upper()}", "kr/claude-sonnet-4.5")
            logger.warning(f"Using legacy single model: {legacy_model}")
            return [legacy_model]
        
        return [config.primary, config.fallback1, config.fallback2]

    def get_model_for_attempt(
        self, task_name: str, attempt: int = 0
    ) -> Optional[str]:
        """
        Get model for specific attempt number
        
        Args:
            task_name: Task name (strategist, writer, visual, engagement, qc)
            attempt: Attempt number (0=primary, 1=FB1, 2=FB2)
            
        Returns:
            Model name or None if no more fallbacks
        """
        chain = self.get_model_chain(task_name)
        if 0 <= attempt < len(chain):
            model = chain[attempt]
            level = ["PRIMARY", "FB1", "FB2"][attempt] if attempt < 3 else f"ATTEMPT_{attempt}"
            logger.info(f"Task '{task_name}' - Using {level}: {model}")
            return model
        
        logger.error(f"No fallback available for task '{task_name}' at attempt {attempt}")
        return None


# Global singleton instance
_router_instance: Optional[ModelRouter] = None


def get_model_router() -> ModelRouter:
    """Get global model router instance"""
    global _router_instance
    if _router_instance is None:
        _router_instance = ModelRouter()
    return _router_instance


def get_model_for_task(task_name: str, attempt: int = 0) -> Optional[str]:
    """
    Convenience function: Get model for task with automatic fallback
    
    Args:
        task_name: Task name (strategist, writer, visual, engagement, qc)
        attempt: Attempt number (0=primary, 1=FB1, 2=FB2)
        
    Returns:
        Model name or None
        
    Example:
        >>> get_model_for_task("writer", 0)  # Returns primary model
        'codebuddy-cn/glm-5.0-turbo'
        >>> get_model_for_task("writer", 1)  # Returns FB1 after primary fails
        'kr/claude-sonnet-4.5'
    """
    router = get_model_router()
    return router.get_model_for_attempt(task_name, attempt)
