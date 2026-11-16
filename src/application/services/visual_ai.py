#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Visual Brief Generator - AI-powered specific visual concepts
"""

import os
import re
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Optional

from domain.services.format_detection import detect_format
from infrastructure.api.api_client import APIClient
from infrastructure.api.model_router import get_model_for_task
from infrastructure.config.loader import load_api_config
from infrastructure.constants import API_MAX_RETRIES, API_TIMEOUT_SECONDS
from infrastructure.logging.logger import setup_logger
from infrastructure.utils.utils import setup_console_encoding

setup_console_encoding()
logger = setup_logger(__name__)


@lru_cache(maxsize=8)
def _load_template(template_name: str) -> str:
    """Load prompt template from file with caching"""
    # Get project root (3 levels up from src/application/services/)
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    template_path = project_root / "prompts" / template_name
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


def parse_thread_image_briefs(content: str) -> dict[int, str]:
    """
    Extract multiple image briefs from thread visual_brief

    Returns:
        {
            1: 'header generation prompt',
            3: 'tweet 3 generation prompt',
            5: 'tweet 5 generation prompt',
            ...
        }
    """
    briefs = {}

    # Extract header image brief (Tweet 1) - get GENERATION PROMPT
    header_section = re.search(
        r"\*\*HEADER IMAGE: VISUAL BRIEF\*\*.*?### GENERATION PROMPT\s*\n(.+?)(?=\n\n---|$)",
        content,
        re.DOTALL,
    )
    if header_section:
        briefs[1] = header_section.group(1).strip()

    # Extract additional image briefs (Tweet 2-8) - updated from 2-10
    # Find ADDITIONAL IMAGES section first
    additional_section = re.search(
        r"\*\*ADDITIONAL IMAGES: VISUAL BRIEF\*\*(.+?)(?=\n\n## |$)", content, re.DOTALL
    )

    if additional_section:
        additional_text = additional_section.group(1)

        # Find all **Tweet N:** sections
        tweet_sections = re.finditer(
            r"\*\*Tweet (\d+):\*\*.*?### GENERATION PROMPT\s*\n(.+?)(?=\n\n---|$|\*\*Tweet \d+:)",
            additional_text,
            re.DOTALL,
        )

        for match in tweet_sections:
            tweet_num = int(match.group(1))
            prompt = match.group(2).strip()
            if prompt and tweet_num >= 2 and tweet_num <= 8:  # Updated to 2-8
                briefs[tweet_num] = prompt

    return briefs


async def call_visual_ai(
    content: str, format_type: str, visual_type: str = "single", account_id: str = "unknown"
) -> Optional[str]:
    """
    Call AI to generate specific visual concepts

    Args:
        content: Content to generate visual for
        format_type: Thread, Image, Single Tweet, Poll
        visual_type: "slides" (1-4), "header" (1), "single" (1)
        account_id: Account identifier for retry budget tracking

    Returns:
        Visual brief text or None
    """

    # Get current date for context
    current_date = datetime.now().strftime("%B %d, %Y")  # e.g., "May 20, 2026"

    # Load base template
    base_template = _load_template("visual_brief_template.txt")

    # Determine format-specific instructions
    if format_type == "Image" and visual_type == "slides":
        format_instructions = _load_template("format_image_slides.txt")
    elif format_type == "Thread" and visual_type == "header":
        format_instructions = _load_template("format_thread_header.txt")
    elif format_type == "Thread" and visual_type == "slides":
        format_instructions = _load_template("format_thread_slides.txt")
    else:
        # Single visual (Single Tweet, Poll, or single Image)
        format_instructions = _load_template("format_single.txt")

    # Build final prompt
    prompt = base_template.format(
        current_date=current_date,
        content=content,
        format_type=format_type,
        visual_type=visual_type,
        format_specific_instructions=format_instructions,
    )

    # Call API with fallback
    api_url, api_key, _ = load_api_config()
    client = APIClient(api_url, api_key, max_retries=API_MAX_RETRIES, timeout=API_TIMEOUT_SECONDS)

    logger.info(f"Generating visual brief for {format_type} ({visual_type})")

    try:
        last_error = None
        
        # Try primary → FB1 → FB2
        for attempt in range(3):
            try:
                model = get_model_for_task("visual", attempt)
                if not model:
                    logger.warning(f"No model available for visual at attempt {attempt}")
                    continue
                
                logger.info(f"Attempt {attempt + 1}/3 with model: {model}")
                
                visual_brief = await client.call_chat_completion(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=4000,
                    temperature=0.8,
                    account_id=account_id,
                )

                if not visual_brief:
                    raise Exception("Failed to generate visual brief")
                
                logger.info(f"Visual brief generated successfully with model: {model}")
                return visual_brief
            
            except Exception as e:
                last_error = e
                logger.warning(f"Attempt {attempt + 1}/3 failed: {e}")
                if attempt == 2:  # Last attempt
                    logger.error(f"All visual attempts exhausted. Last error: {last_error}")
                    raise
                continue
        
        # Should not reach here
        logger.error(f"Failed to generate visual brief after all attempts: {last_error}")
        return None

    except Exception as e:
        logger.error(f"Error generating visual brief: {e}", exc_info=True)
        return None
    finally:
        await client.close()


def save_visual_brief(content_file, visual_brief):
    """Save visual brief to file"""
    content_path = Path(content_file)
    output_dir = Path(__file__).parent.parent / "output" / "visual"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Extract topic from filename
    filename = content_path.stem
    if "_content_" in filename:
        topic_part = filename.split("_content_")[0]
        timestamp = filename.split("_content_")[1]

        # Remove format prefix if exists
        if "__" in topic_part:
            parts = topic_part.split("__", 1)
            topic = parts[1] if len(parts) > 1 else topic_part
        else:
            topic = topic_part
    else:
        topic = content_path.stem or "visual"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Save
    output_file = output_dir / f"{topic}_visual_{timestamp}.txt"

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("═══════════════════════════════════════════════════════\n")
        f.write("VISUAL DESIGN BRIEF - SPECIFIC CONCEPTS\n")
        f.write("═══════════════════════════════════════════════════════\n\n")
        f.write(visual_brief)
        f.write("\n\n═══════════════════════════════════════════════════════\n")
        f.write("END OF VISUAL BRIEF\n")
        f.write("═══════════════════════════════════════════════════════\n")

    return output_file


def main():
    if len(sys.argv) < 2:
        print("[!] Usage: python visual.py <content_file>")
        sys.exit(1)

    content_file = sys.argv[1]

    if not os.path.exists(content_file):
        print(f"[!] File not found: {content_file}")
        sys.exit(1)

    # Read content
    with open(content_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Detect format
    format_type = detect_format(content)

    print("============================================================")
    print("VISUAL BRIEF GENERATOR - AI-POWERED")
    print("============================================================")
    print(f"[*] Detected format: {format_type}")
    print(f"[*] Generating specific visual concepts...")
    print()

    # Generate visual brief
    visual_brief = call_visual_ai(content, format_type)

    if not visual_brief:
        print("[!] Failed to generate visual brief")
        sys.exit(1)

    # Save
    output_file = save_visual_brief(content_file, visual_brief)

    print("[*] Visual brief generated!")
    print()
    print("============================================================")
    print("VISUAL DESIGN BRIEF")
    print("============================================================")
    print()
    print(f"[*] Saved to: {output_file}")
    print()


if __name__ == "__main__":
    main()
