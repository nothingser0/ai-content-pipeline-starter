#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Writer - Multi-Account Content Pipeline
Generate full content from selected angle
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from infrastructure.api.api_client import APIClient
from infrastructure.api.model_router import get_model_for_task as get_model_with_fallback

# Import shared utilities
from infrastructure.config.loader import load_api_config
from infrastructure.constants import API_MAX_RETRIES, API_MAX_TOKENS, API_TIMEOUT_SECONDS, TWEET_MAX_LENGTH
from infrastructure.logging.logger import setup_logger
from infrastructure.utils.utils import setup_console_encoding
from domain.services.validation import ValidationError, validate_format_choice

# Setup
setup_console_encoding()
logger = setup_logger(__name__)


def _load_prompt_template(prompt_name: str) -> str:
    """Load prompt template from file"""
    prompt_file = Path(__file__).parent.parent / "prompts" / f"{prompt_name}.txt"
    with open(prompt_file, "r", encoding="utf-8") as f:
        return f.read()


def _format_key_points(key_points: Any) -> str:
    """Format key points as string"""
    if isinstance(key_points, list):
        return "\n".join([f"- {p}" for p in key_points])
    return str(key_points)


def _clean_generated_content(content: str, format_choice: str) -> str:
    """Clean model output to fit exact format rules."""
    cleaned = content.strip()

    if format_choice == "Image":
        cleaned = re.sub(r"^\*\*Tweet:\*\*\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^Tweet:\s*", "", cleaned, flags=re.IGNORECASE)
        split_markers = [
            "\n---",
            "\n**[IMAGE CONTENT]**",
            "\n[IMAGE CONTENT]",
            "\nSlide 1:",
            "\n**Slide 1:**",
            "\nImage Content:",
        ]
        for marker in split_markers:
            if marker in cleaned:
                cleaned = cleaned.split(marker, 1)[0].strip()

    if format_choice == "Poll":
        lines = []
        for line in cleaned.splitlines():
            stripped = line.strip()
            if stripped.startswith(("A)", "B)", "C)", "D)", "1.", "2.", "3.", "4.")):
                continue
            lines.append(line)
        cleaned = "\n".join(lines).strip()

    return cleaned


def _compress_short_form_body(body: str) -> str:
    """Reduce avoidable whitespace before hard truncation."""
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    compact = " ".join(lines)
    compact = re.sub(r"\s+([,.!?;:])", r"\1", compact)
    compact = compact.replace("  ", "; ")
    compact = compact.replace("  ", " - ")
    compact = re.sub(r"\s*\|\s*", "; ", compact)
    compact = re.sub(r":\s*;", ": ", compact)
    compact = re.sub(r"\s*;\s*([A-Z][a-zA-Z0-9+#]+:)", r". \1", compact)
    compact = compact.replace("; ;", "; ")
    compact = re.sub(r"\b([a-z]{2,})\s([A-Z][a-zA-Z0-9+#]+:)", r"\1. \2", compact)
    compact = re.sub(r"\b([a-z]{2,})\s(Which\b)", r"\1. \2", compact)
    compact = re.sub(r"\s{2,}", " ", compact)
    return compact.strip()


def _compress_image_caption(body: str) -> str:
    """Keep image caption short, contextual, and non-listy."""
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    compact = " ".join(lines)
    compact = re.sub(r"\s+([,.!?;:])", r"\1", compact)
    # Remove tool name patterns (generic pattern instead of hardcoded names)
    compact = re.sub(r"\b[A-Z][a-zA-Z0-9+]+\b\s*[?:-]\s*[^.?!;]+", "", compact)
    compact = re.sub(r"\s{2,}", " ", compact)
    compact = compact.replace(" .", ".").replace(" ,", ",")
    compact = compact.replace("..", ".")

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", compact) if s.strip()]
    if len(sentences) > 3:
        sentences = sentences[:3]
    compact = " ".join(sentences).strip()

    if len(compact) > 240 and " What's " in f" {compact} ":
        compact = compact.split(" What", 1)[0].strip()

    return compact.strip()


def _truncate_at_word_boundary(text: str, max_length: int) -> str:
    """Truncate text at nearest word boundary with ellipsis."""
    if len(text) <= max_length:
        return text

    cutoff = max_length - 3
    truncated = text[:cutoff]
    if " " in truncated:
        truncated = truncated.rsplit(" ", 1)[0]
    return truncated.rstrip(" ,;:-") + "..."


def _build_prompt(template: str, angle_data: Dict[str, Any], format_choice: str) -> str:
    """Build prompt from template and data with freshness constraints."""
    # Get current date and year for context
    current_year = datetime.now().strftime("%Y")
    current_date = datetime.now().strftime("%B %d, %Y")

    # Inject date context and freshness rules at the beginning
    date_context = (
        f"CURRENT DATE: {current_date}\n\n"
        f"CRITICAL FRESHNESS & ACCURACY RULES:\n"
        f"1. Current year is {current_year}. Do NOT present old models (like GPT-3, initial GPT-4, or old Claude 3) as brand-new.\n"
        f"2. Never hallucinate outdated news or past historical events as current breaking news.\n"
        f"3. Focus on practical takeaways, real-world utility, and timeless actionable advice for modern creators/professionals.\n\n"
    )

    prompt = template.replace("{title}", angle_data.get("title", ""))
    prompt = prompt.replace("{hook}", angle_data.get("hook", ""))
    prompt = prompt.replace("{pillar}", angle_data.get("pillar", ""))
    prompt = prompt.replace("{format}", format_choice)
    prompt = prompt.replace(
        "{key_points}", _format_key_points(angle_data.get("key_points", []))
    )
    prompt = prompt.replace("{cta}", angle_data.get("cta", ""))

    # Add date context at the beginning
    prompt = date_context + prompt

    return prompt


async def generate_content(
    angle_data: Dict[str, Any],
    format_choice: str,
    writer_prompt: str,
    account_config: Optional[Dict[str, Any]] = None,
    client: Optional[APIClient] = None,
) -> Optional[str]:
    """
    Generate content using account-specific writer prompt.

    Args:
        angle_data: Selected angle data
        format_choice: Requested output format
        writer_prompt: Account-specific writer prompt template
        account_config: Optional account configuration dict (reserved for future use)
        client: Optional API client

    Returns:
        Generated content string or None on failure
    """
    # Extract account_id for retry budget tracking
    account_id = account_config.get("account_id", "unknown") if account_config else "unknown"

    try:
        format_choice = validate_format_choice(format_choice)
    except ValidationError as e:
        logger.error(f"Invalid format choice: {e}")
        return None

    prompt = _build_prompt(writer_prompt, angle_data, format_choice)

    api_url, api_key, _ = load_api_config()
    should_close_client = False

    if client is None:
        client = APIClient(api_url, api_key, max_retries=API_MAX_RETRIES, timeout=API_TIMEOUT_SECONDS)
        should_close_client = True

    try:
        logger.debug(f"Generating content for account format: {format_choice}")
        logger.debug(f"Angle title: {angle_data.get('title', 'Unknown')}")
        
        last_error = None
        
        # Try primary → FB1 → FB2
        for attempt in range(3):
            try:
                model = get_model_with_fallback("writer", attempt)
                if not model:
                    logger.warning(f"No model available for writer at attempt {attempt}")
                    continue
                
                logger.info(f"Attempt {attempt + 1}/3 with model: {model}")
                
                current_year = datetime.now().strftime("%Y")
                current_date = datetime.now().strftime("%B %d, %Y")
                writer_system_instruction = (
                    f"You are a master social media copywriter writing today in {current_year} (Date: {current_date}).\n"
                    f"MANDATORY RECENCY & VALUE DIRECTIVE:\n"
                    f"- Every tweet, thread slide, hook, and CTA must feel freshly written today, matching the {current_year} industry landscape.\n"
                    f"- Never mention obsolete tools, old years (2022-2024), or outdated software versions as current.\n"
                    f"- Provide crisp, practical, high-value insights that practitioners can use immediately."
                )

                content = await client.call_chat_completion(
                    model=model,
                    messages=[
                        {
                            "role": "system",
                            "content": writer_system_instruction,
                        },
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=API_MAX_TOKENS,
                    temperature=0.8,
                    account_id=account_id,
                )

                if not content:
                    raise Exception("Failed to generate content")

                content = _clean_generated_content(content, format_choice)

                # Format-specific marker for requested format only
                format_markers = {
                    "Single Tweet": "**SINGLE TWEET:**",
                    "Thread": "**THREAD:**",
                    "Poll": "**POLL:**",
                    "Image": "**IMAGE:**",
                }

                # Check if content has the correct format marker for requested format
                expected_marker = format_markers.get(
                    format_choice, f"**{format_choice.upper()}:**"
                )
                has_correct_marker = expected_marker in content

                if not has_correct_marker:
                    content = f"{expected_marker}\n\n{content}"

                if format_choice in {"Single Tweet", "Poll", "Image"}:
                    marker = format_markers[format_choice] + "\n\n"
                    body = content.replace(marker, "").strip()
                    if format_choice == "Single Tweet":
                        body = _compress_short_form_body(body)
                        content = f"{format_markers[format_choice]}\n\n{body}"
                    elif format_choice == "Image":
                        body = _compress_image_caption(body)
                        content = f"{format_markers[format_choice]}\n\n{body}"
                    if len(body) > TWEET_MAX_LENGTH:
                        logger.warning(
                            f"{format_choice} too long ({len(body)} chars), truncating to {TWEET_MAX_LENGTH}"
                        )
                        body = _truncate_at_word_boundary(body, TWEET_MAX_LENGTH)
                        content = f"{format_markers[format_choice]}\n\n{body}"

                logger.info(f"Successfully generated content with model: {model}")
                return content
            
            except Exception as e:
                last_error = e
                logger.warning(f"Attempt {attempt + 1}/3 failed: {e}")
                if attempt == 2:  # Last attempt
                    logger.error(f"All writer attempts exhausted. Last error: {last_error}")
                    raise
                continue
        
        # Should not reach here
        logger.error(f"Failed to generate content after all attempts: {last_error}")
        return None
    
    except Exception as e:
        logger.error(f"Unexpected error in generate_content: {e}", exc_info=True)
        return None
    finally:
        if should_close_client:
            await client.close()


async def call_writer_ai(
    angle_data: Dict[str, Any], format_choice: str, client: Optional[APIClient] = None
) -> Optional[str]:
    """
    Call AI to generate content from selected angle (legacy wrapper).

    Args:
        angle_data: Dictionary containing angle information (title, hook, pillar, key_points, cta)
        format_choice: Content format (Thread, Single Tweet, Poll, Image)
        client: Optional APIClient instance (for dependency injection)

    Returns:
        Generated content string or None on failure
    """
    # Load default writer prompt template
    try:
        writer_prompt = _load_prompt_template("writer_surabaya")
    except Exception as e:
        logger.error(f"Failed to load writer prompt template: {e}")
        return None

    # Delegate to generate_content
    return await generate_content(
        angle_data=angle_data,
        format_choice=format_choice,
        writer_prompt=writer_prompt,
        account_config=None,
        client=client,
    )


async def main() -> None:
    """Main function"""
    import sys

    from infrastructure.utils.utils import exit_with_error, print_section

    print_section("AI WRITER - Web3 Content Pipeline (Surabaya Style)")

    # Read angle from stdin or file
    if len(sys.argv) > 1:
        # Read from file
        input_file = sys.argv[1]
        try:
            with open(input_file, "r", encoding="utf-8-sig") as f:
                angle_data = json.load(f)
        except Exception as e:
            exit_with_error(f"Error reading file: {e}")
    else:
        # Read from stdin
        try:
            angle_data = json.load(sys.stdin)
        except (json.JSONDecodeError, ValueError) as e:
            exit_with_error(
                f"Invalid JSON from stdin: {e}\nUsage: python writer.py <angle_file.json> or pipe angle JSON to stdin"
            )
        except Exception as e:
            exit_with_error(
                f"Error reading stdin: {e}\nUsage: python writer.py <angle_file.json> or pipe angle JSON to stdin"
            )

    logger.info(f"Loaded angle: {angle_data.get('title', 'Unknown')}")

    # Get format choice - prioritize 'format' key (user choice) over suggested_formats
    format_choice = angle_data.get("format")

    # If no 'format' key, use first from suggested_formats
    if not format_choice and isinstance(angle_data.get("suggested_formats"), list):
        format_choice = angle_data["suggested_formats"][0]

    # Default to Thread if still no format
    if not format_choice:
        format_choice = "Thread"

    logger.debug(f"Format: {format_choice}")

    # Generate content
    content = await call_writer_ai(angle_data, format_choice)

    if not content:
        exit_with_error("Failed to generate content")

    # Post-processing: Add format marker if not present
    format_markers = {
        "Single Tweet": "**SINGLE TWEET:**",
        "Thread": "**THREAD:**",
        "Poll": "**POLL:**",
        "Image": "**IMAGE:**",
    }

    # Check if content has the correct format marker for requested format
    expected_marker = format_markers.get(format_choice, f"**{format_choice.upper()}:**")
    has_correct_marker = expected_marker in content

    if not has_correct_marker:
        content = f"{expected_marker}\n\n{content}"

    # Post-processing: Enforce character limit for Single Tweet
    if format_choice == "Single Tweet":
        # Remove format marker for character count
        content_without_marker = content.replace("**SINGLE TWEET:**\n\n", "")
        if len(content_without_marker) > TWEET_MAX_LENGTH:
            logger.warning(
                f"Single Tweet too long ({len(content_without_marker)} chars), truncating to {TWEET_MAX_LENGTH}"
            )
            content_without_marker = _truncate_at_word_boundary(
                content_without_marker, TWEET_MAX_LENGTH
            )
            content = f"**SINGLE TWEET:**\n\n{content_without_marker}"

    logger.info("Content generated successfully")

    # Extract topic from angle data (use title, fallback to first line of content)
    if "title" in angle_data and angle_data["title"]:
        topic = angle_data["title"]
    else:
        # Fallback: extract from content first line
        first_line = content.split("\n")[0]
        topic = first_line.replace("#", "").replace("*", "").strip()

    # Clean topic for filename
    from domain.services.validation import sanitize_filename

    try:
        safe_topic = sanitize_filename(topic[:50])
    except ValidationError:
        safe_topic = "content"

    # Output content
    print_section("GENERATED CONTENT")

    # Print to stdout (for piping)
    print(content)

    # Save to file
    output_dir = Path(__file__).parent.parent / "output" / "writer"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"{safe_topic}_content_{timestamp}.txt"

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info(f"Saved to: {output_file}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
