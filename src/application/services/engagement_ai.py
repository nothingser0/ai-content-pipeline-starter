#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Engagement Strategy Generator - AI-powered from content analysis
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

src_dir = str(Path(__file__).resolve().parents[2])
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from domain.services.format_detection import detect_format
from infrastructure.api.api_client import APIClient
from infrastructure.api.model_router import get_model_for_task
from infrastructure.config.loader import load_api_config
from infrastructure.constants import API_MAX_RETRIES, API_TIMEOUT_SECONDS
from infrastructure.logging.logger import setup_logger
from infrastructure.utils.utils import setup_console_encoding

# Setup
setup_console_encoding()
logger = setup_logger(__name__)


async def call_engagement_ai(
    content: str,
    format_type: str,
    engagement_prompt: str,
    account_config: Optional[Dict[str, Any]] = None,
    client: Optional[APIClient] = None,
) -> Optional[str]:
    """
    Generate engagement strategy using account-specific prompt.

    Args:
        content: Generated content to analyze
        format_type: Content format (Thread, Single Tweet, Poll, Image)
        engagement_prompt: Account-specific engagement prompt template
        account_config: Optional account configuration (reserved for future use)
        client: Optional API client

    Returns:
        Engagement strategy string or None on failure
    """
    # Extract account_id for retry budget tracking
    account_id = account_config.get("account_id", "unknown") if account_config else "unknown"

    # Get current date for context
    current_date = datetime.now().strftime("%B %d, %Y")

    # Build prompt from template
    prompt = engagement_prompt.replace("{content}", content)
    prompt = prompt.replace("{format_type}", format_type)

    # Add date context
    date_context = f"CURRENT DATE: {current_date}\n\nIMPORTANT: Consider current trends and timing for {current_date}.\n\n"
    prompt = date_context + prompt

    # Load config and create client if not provided
    api_url, api_key, _ = load_api_config()
    should_close_client = False

    if client is None:
        client = APIClient(api_url, api_key, max_retries=API_MAX_RETRIES, timeout=API_TIMEOUT_SECONDS)
        should_close_client = True

    try:
        logger.info(f"Generating engagement strategy for {format_type}")
        
        last_error = None
        
        # Try primary → FB1 → FB2
        for attempt in range(3):
            try:
                model = get_model_for_task("engagement", attempt)
                if not model:
                    logger.warning(f"No model available for engagement at attempt {attempt}")
                    continue
                
                logger.info(f"Attempt {attempt + 1}/3 with model: {model}")
                
                result = await client.call_chat_completion(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=3000,
                    temperature=0.8,
                    account_id=account_id,
                )

                if not result:
                    raise Exception("Failed to generate engagement strategy")
                
                logger.info(f"Engagement strategy generated successfully with model: {model}")
                return result
            
            except Exception as e:
                last_error = e
                logger.warning(f"Attempt {attempt + 1}/3 failed: {e}")
                if attempt == 2:  # Last attempt
                    logger.error(f"All engagement attempts exhausted. Last error: {last_error}")
                    raise
                continue
        
        # Should not reach here
        logger.error(f"Failed to generate engagement strategy after all attempts: {last_error}")
        return None

    except Exception as e:
        logger.error(f"Error generating engagement strategy: {e}", exc_info=True)
        return None
    finally:
        if should_close_client:
            await client.close()


def save_engagement_strategy(content_file: str, engagement_strategy: str) -> None:
    """Save engagement strategy to file"""
    content_path = Path(content_file)
    output_dir = content_path.parent

    # Create engagement file
    engagement_file = output_dir / f"{content_path.stem}_engagement.txt"

    with open(engagement_file, "w", encoding="utf-8") as f:
        f.write(engagement_strategy)

    logger.info(f"Saved engagement strategy to: {engagement_file}")


async def main() -> None:
    """Main function for standalone usage"""
    import argparse

    from infrastructure.utils.engagement_prompt import generate_engagement_prompt

    parser = argparse.ArgumentParser(
        description="Generate engagement strategy from content"
    )
    parser.add_argument("content_file", help="Path to content file")
    parser.add_argument("--account", help="Account ID for account-specific strategy")
    args = parser.parse_args()

    # Read content
    try:
        with open(args.content_file, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        logger.error(f"Error reading content file: {e}")
        sys.exit(1)

    # Detect format
    format_type = detect_format(content)
    logger.info(f"Detected format: {format_type}")

    # Load account config if specified
    engagement_prompt = None
    if args.account:
        account_dir = Path(__file__).resolve().parents[3] / "accounts" / args.account
        config_path = account_dir / "config.json"

        if config_path.exists():
            with open(config_path, "r", encoding="utf-8-sig") as f:
                account_config = json.load(f)

            # Generate engagement prompt from config
            engagement_prompt = generate_engagement_prompt(account_config)
            logger.info(f"Using account-specific engagement prompt for {args.account}")
        else:
            logger.warning(f"Account config not found: {config_path}")

    # Use default prompt if no account-specific prompt
    if not engagement_prompt:
        # Load default engagement prompt template
        default_config = {
            "username": "@account",
            "niche": "General",
            "target_audience": "General audience",
            "timezone": "UTC",
            "platform_mix": ["Twitter"],
        }
        engagement_prompt = generate_engagement_prompt(default_config)
        logger.info("Using default engagement prompt")

    # Generate engagement strategy
    strategy = await call_engagement_ai(content, format_type, engagement_prompt)

    if strategy:
        # Save to file
        save_engagement_strategy(args.content_file, strategy)

        # Print to stdout
        print("\n" + "=" * 60)
        print("ENGAGEMENT STRATEGY")
        print("=" * 60)
        print(strategy)
    else:
        logger.error("Failed to generate engagement strategy")
        sys.exit(1)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
