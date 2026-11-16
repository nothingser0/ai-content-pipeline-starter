#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Strategist - Multi-Account Content Pipeline (English)
Generate 10 content angles for any of 21 accounts
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Ensure src directory and project root are in sys.path when script is run directly
src_dir = str(Path(__file__).resolve().parents[2])
project_root = str(Path(__file__).resolve().parents[3])
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from infrastructure.api.api_client import APIClient
from infrastructure.api.model_router import get_model_for_task
from infrastructure.config.loader import load_api_config

# Import shared config
from infrastructure.logging.logger import setup_logger
from infrastructure.utils.utils import setup_console_encoding

# Setup console encoding
setup_console_encoding()
logger = setup_logger(__name__)


def _extract_json(text: str) -> Any:
    """Extract valid JSON object or list from LLM output, handling markdown fences and trailing text."""
    text = text.strip()
    # 1. Try markdown code blocks first
    matches = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    for block in matches:
        try:
            return json.loads(block.strip())
        except Exception:
            pass

    # 2. Try direct json parse
    try:
        return json.loads(text)
    except Exception:
        pass

    # 3. Extract balanced { ... } object (handles trailing text / extra data)
    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except Exception:
                        break

    # 4. Extract balanced [ ... ] array
    start_arr = text.find("[")
    if start_arr != -1:
        depth = 0
        for i in range(start_arr, len(text)):
            if text[i] == "[":
                depth += 1
            elif text[i] == "]":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start_arr : i + 1])
                    except Exception:
                        break

    raise json.JSONDecodeError("Could not extract valid JSON from response", text, 0)


async def generate_angles(topic, strategist_prompt, account_config, target_format: str | None = None):
    """
    Generate 1 single best content angle for given topic

    Args:
        topic: Topic/idea string
        strategist_prompt: Account-specific strategist prompt
        account_config: Account configuration dict
        target_format: Optional target format (Thread, Single Tweet, Poll, Image)

    Returns:
        dict with 'angles' list containing the single best angle
    """
    api_url, api_key, _ = load_api_config()  # Get API config, ignore legacy model
    account_id = account_config.get("account_id", "unknown")

    # Get current date for context
    current_year = datetime.now().strftime("%Y")
    current_date = datetime.now().strftime("%B %d, %Y")

    # Format topic with date context
    topics_text = f"Topic: {topic}\n"

    # Replace placeholders in prompt
    prompt = strategist_prompt.replace("{topics}", topics_text)

    # Inject date context and freshness rules at the beginning
    date_context = (
        f"CURRENT DATE: {current_date}\n\n"
        f"CRITICAL TIMELINESS & FRESHNESS RULES:\n"
        f"1. You are operating in {current_year}. All commentary must reflect current standards and modern tooling.\n"
        f"2. NEVER treat outdated tools, releases, or historical events from 2023-2024 as breaking news.\n"
        f"3. If the topic is a specific news headline, provide sharp, practical analysis on what it means for users right now.\n"
        f"4. If the topic is a general pillar (tools, workflow, prompts, tutorial), provide timeless/evergreen, actionable advice rather than inventing fake or stale news.\n\n"
    )

    format_instruction = ""
    if target_format:
        format_instruction = f"- TARGET PRIMARY FORMAT: {target_format}. Tailor the hook, points, and suggested_formats specifically for {target_format}.\n"

    single_angle_directive = (
        f"MANDATORY SINGLE-ANGLE DIRECTIVE:\n"
        f"- Generate EXACTLY 1 single best, highest-impact content angle (do not generate multiple angles).\n"
        f"{format_instruction}"
        f"- Focus 100% of your effort on making this single angle irresistible, highly engaging, and true to the account voice.\n"
        f"- Return a JSON object with an 'angles' array containing this single angle object.\n\n"
    )

    prompt = date_context + single_angle_directive + prompt

    # Call API with fallback mechanism
    client = APIClient(api_url, api_key)

    logger.info(f"Generating single best angle for: {topic} (Target format: {target_format or 'auto'})")
    logger.info(f"Account: {account_config['username']} - {account_config['niche']}")

    try:
        last_error = None
        
        # Try primary → FB1 → FB2
        for attempt in range(3):
            try:
                model = get_model_for_task("strategist", attempt)
                if not model:
                    logger.warning(f"No model available for strategist at attempt {attempt}")
                    continue
                
                logger.info(f"Attempt {attempt + 1}/3 with model: {model}")
                
                system_instruction = (
                    f"You are an elite social media content strategist operating in {current_year} (Today's date: {current_date}).\n"
                    f"MANDATORY RECENCY & TIMELINESS DIRECTIVE:\n"
                    f"- All titles, hooks, angles, and references MUST be strictly current and relevant to {current_year}.\n"
                    f"- Treat the current ecosystem and modern tools as the baseline. Never treat outdated technology, old model releases, or historical events from 2022-2024 as current or breaking.\n"
                    f"- Ensure the angle feels like it was conceived today, offering fresh, cutting-edge, or timelessly practical perspective."
                )

                content = await client.call_chat_completion(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.7,
                    max_tokens=2000,
                    account_id=account_id,
                )

                if not content:
                    raise Exception("Empty response from API")

                # Debug: log first 200 chars of response
                logger.debug(f"Raw API response (first 200 chars): {content[:200]}")

                # Robust JSON extraction
                parsed = _extract_json(content)

                # Standardize to {'angles': [...]}
                if isinstance(parsed, list):
                    result = {"angles": parsed}
                elif isinstance(parsed, dict):
                    if "angles" in parsed and isinstance(parsed["angles"], list):
                        result = parsed
                    else:
                        result = {"angles": [parsed]}
                else:
                    result = {"angles": []}

                logger.info(f"Generated {len(result.get('angles', []))} angle(s)")
                logger.info(f"Successfully generated angle with model: {model}")

                return result
            
            except Exception as e:
                last_error = e
                logger.warning(f"Attempt {attempt + 1}/3 failed: {e}")
                if attempt == 2:  # Last attempt
                    logger.error(f"All strategist attempts exhausted. Last error: {last_error}")
                    raise
                continue
        
        # Should not reach here, but handle gracefully
        logger.error(f"Failed to generate angles after all attempts: {last_error}")
        return {"angles": [], "error": str(last_error)}
    
    except Exception as e:
        logger.error(f"Error generating angles: {e}")
        return {"angles": [], "error": str(e)}
    finally:
        await client.close()


async def main():
    """Test function"""
    import json

    project_root = Path(__file__).resolve().parents[3]
    config_path = project_root / "accounts" / "01-ai-automation" / "config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        account_config = json.load(f)

    prompt_path = (
        project_root / "accounts" / "01-ai-automation" / "strategist_prompt.txt"
    )
    with open(prompt_path, "r", encoding="utf-8") as f:
        strategist_prompt = f.read()

    # Test
    result = await generate_angles(
        topic="10 ChatGPT prompts for developers",
        strategist_prompt=strategist_prompt,
        account_config=account_config,
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
