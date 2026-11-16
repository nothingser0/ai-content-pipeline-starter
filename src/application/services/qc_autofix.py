#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Minimal QC helpers for multi-account pipeline MVP.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from domain.services.format_detection import detect_format
from infrastructure.api.api_client import APIClient
from infrastructure.api.model_router import get_model_for_task
from infrastructure.config.loader import load_api_config
from infrastructure.config.settings import (
    API_TEMPERATURE,
    QC_AUTOFIX_THRESHOLD,
    QC_PASS_THRESHOLD,
    THREAD_MAX_TWEETS,
    THREAD_MIN_TWEETS,
    TWEET_MAX_LENGTH,
    WHITESPACE_CLEANUP_THRESHOLD,
)
from infrastructure.logging.logger import setup_logger

logger = setup_logger(__name__)

# Pre-compiled regex patterns
_RE_KEYWORDS = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9\-\+\.]{2,}")
_RE_THREAD_TWEETS = re.compile(
    r"(?:^|\n)(?:\*\*)?(?:Tweet|TWEET)\s*\d+(?:\*\*)?:?\s*\n(.+?)(?=\n(?:\*\*)?(?:Tweet|TWEET)\s*\d+|\Z)",
    re.DOTALL,
)
_RE_CLEANUP_MARKERS = re.compile(r"\*\*(?:SINGLE TWEET|POLL|IMAGE):\*\*\s*\n\s*\n")
_RE_CLEANUP_VISUAL = re.compile(r"\n\n(?:VISUAL BRIEF|HEADER IMAGE BRIEF|ADDITIONAL IMAGE BRIEFS):.*", re.DOTALL)
_RE_CLEANUP_WHITESPACE = re.compile(r"\n{3,}")
_RE_IMAGE_MARKER = re.compile(r"\*\*IMAGE:\*\*\s*\n\s*\n\s*\*\*\.")
_RE_IMAGE_CLEANUP = re.compile(r"\*\*IMAGE:\*\*\s*\n\s*\n")


def _normalise_text(value: str) -> str:
    return " ".join(value.lower().split())


def _extract_keywords(text: str) -> set[str]:
    words = _RE_KEYWORDS.findall(text.lower())
    stopwords = {
        "that",
        "this",
        "with",
        "from",
        "your",
        "have",
        "will",
        "into",
        "about",
        "they",
        "them",
        "were",
        "what",
        "when",
        "where",
        "which",
        "only",
        "dont",
        "does",
        "just",
        "than",
        "then",
        "their",
        "there",
        "here",
        "while",
        "more",
        "most",
        "very",
        "actually",
        "tool",
        "tools",
        "tweet",
        "thread",
        "image",
        "poll",
    }
    return {word for word in words if word not in stopwords}


def _detect_alignment_issues(
    cleaned_content: str, angle: dict[str, Any], resolved_format: str
) -> list[str]:
    issues: list[str] = []
    normalised_content = _normalise_text(cleaned_content)

    title = str(angle.get("title", "")).strip()
    hook = str(angle.get("hook", "")).strip()
    key_points = angle.get("key_points", [])

    marker_map = {
        "Single Tweet": "**SINGLE TWEET:**",
        "Poll": "**POLL:**",
        "Image": "**IMAGE:**",
    }
    if resolved_format in marker_map:
        body = cleaned_content.replace(marker_map[resolved_format], "").strip()

        # For Image format, only count CAPTION section
        if resolved_format == "Image" and "CAPTION:" in body:
            caption_text = body.replace("**CAPTION:**", "").strip()
            if len(caption_text) > TWEET_MAX_LENGTH:
                issues.append(
                    f"Technical & Readability: caption too long ({len(caption_text)} chars > {TWEET_MAX_LENGTH})"
                )
        elif resolved_format != "Image" and len(body) > TWEET_MAX_LENGTH:
            issues.append(
                f"Technical & Readability: content too long ({len(body)} chars > {TWEET_MAX_LENGTH})"
            )

    if resolved_format == "Poll" and "?" not in cleaned_content:
        issues.append("Context & Functionality: poll must be written as question")

    # Image format structure validation (CAPTION only)
    if resolved_format == "Image":
        if "CAPTION:" not in cleaned_content:
            issues.append("Format Error: Image must have CAPTION section")

    if resolved_format == "Poll" and any(
        token in cleaned_content for token in ["A)", "B)", "C)", "D)"]
    ):
        issues.append("Context & Functionality: poll must not contain manual options")

    # Freshness & Timeliness check: flag outdated years presented as recent
    for yr in ["2020", "2021", "2022", "2023", "2024"]:
        if re.search(rf"\b(in|since|during|this year|released in|launched in|new in)\s+{yr}\b", cleaned_content, re.IGNORECASE):
            issues.append(f"Freshness Error: contains outdated historical timeframe reference ({yr})")
            break

    title_keywords = _extract_keywords(title)
    hook_keywords = _extract_keywords(hook)
    content_keywords = _extract_keywords(normalised_content)

    title_overlap = len(title_keywords & content_keywords)
    hook_overlap = len(hook_keywords & content_keywords)

    key_point_hits = 0
    if isinstance(key_points, list):
        for key_point in key_points:
            key_text = str(key_point).strip()
            if not key_text:
                continue
            key_keywords = _extract_keywords(key_text)
            if len(key_keywords & content_keywords) >= 1:
                key_point_hits += 1

    if title_overlap == 0 and hook_overlap == 0 and key_point_hits == 0:
        issues.append(
            "Context & Functionality: generated content weakly aligned with chosen angle"
        )

    strategy_triggers = [
        "?",
        "reply",
        "drop",
        "share",
        "tell",
        "setuju",
        "menurut",
        "bookmark",
        "save",
        "👇",
    ]
    if not any(trigger in normalised_content for trigger in strategy_triggers):
        issues.append("Engagement & Algorithm Check: weak interaction trigger or CTA")

    # Thread tweet length validation
    if resolved_format == "Thread":
        tweets = _RE_THREAD_TWEETS.findall(cleaned_content)

        if tweets:
            tweet_lengths = [(i + 1, len(text.strip())) for i, text in enumerate(tweets)]

            # Check for short tweets (excluding Tweet 10 CTA)
            short_tweets = [
                (num, length) for num, length in tweet_lengths[:-1] if length < 200
            ]

            if len(short_tweets) >= 3:
                # Too many short tweets - reject
                short_list = ", ".join(
                    [f"T{num}:{length}ch" for num, length in short_tweets[:5]]
                )
                issues.append(
                    f"Format Error: {len(short_tweets)} tweets below 200 chars ({short_list}). CRITICAL rule violated."
                )

    return issues


def _check_voice_consistency(
    content: str, account_config: Optional[Dict[str, Any]] = None
) -> list[str]:
    """
    Check if content matches account voice (optional enhancement).

    Args:
        content: Generated content
        account_config: Account configuration with voice fields

    Returns:
        List of voice consistency issues
    """
    if not account_config:
        return []

    issues: list[str] = []
    normalised_content = _normalise_text(content)

    # Check for forbidden phrases (not_this_voice)
    not_this_voice = account_config.get("not_this_voice", [])
    for forbidden in not_this_voice:
        if _normalise_text(forbidden) in normalised_content:
            issues.append(f"Voice Consistency: contains forbidden phrase '{forbidden}'")

    # Check for required tone markers (optional - only warn if completely missing)
    tone_markers = account_config.get("tone_markers", [])
    if tone_markers and len(tone_markers) > 0:
        # Extract key characteristics from tone markers
        # This is a soft check - just ensure content isn't completely off-brand
        pass  # Soft check - no hard failures

    return issues


async def ai_autofix_content(
    content: str, issues: list[str], angle: dict[str, Any], resolved_format: str, account_id: str = "unknown"
) -> Optional[str]:
    """
    Use AI to fix content issues

    Args:
        content: Original content
        issues: List of detected issues
        angle: Angle data
        resolved_format: Content format
        account_id: Account identifier for retry budget tracking

    Returns:
        Fixed content or None on failure
    """
    api_url, api_key, _ = load_api_config()
    client = APIClient(api_url, api_key)

    # Build fix prompt
    issues_text = "\n".join([f"- {issue}" for issue in issues])

    prompt = f"""You are a content quality fixer. Fix the following content to address these issues:

ISSUES:
{issues_text}

ORIGINAL CONTENT:
{content}

ANGLE CONTEXT:
Title: {angle.get('title', 'N/A')}
Hook: {angle.get('hook', 'N/A')}
Format: {resolved_format}

INSTRUCTIONS:
1. Fix all listed issues
2. Maintain the original format marker (e.g., **SINGLE TWEET:**, **THREAD:**, etc.)
3. Keep the core message and voice
4. For Single Tweet/Poll/Image: ensure content is under {TWEET_MAX_LENGTH} characters (excluding format marker)
5. For Thread: ensure {THREAD_MIN_TWEETS}-{THREAD_MAX_TWEETS} tweets
6. For Poll: ensure question format with no manual options (A), B), etc.)
7. For Image: ensure CAPTION section only
8. Ensure all dates, tools, models, and industry standards are up to date and strictly relevant to today. Replace any obsolete years (2020-2024) or discontinued tools with modern equivalents.

Return ONLY the fixed content, no explanations."""

    try:
        last_error = None
        
        # Try primary → FB1 → FB2
        for attempt in range(3):
            try:
                model = get_model_for_task("qc", attempt)
                if not model:
                    logger.warning(f"No model available for qc at attempt {attempt}")
                    continue
                
                logger.info(f"Attempt {attempt + 1}/3 with model: {model}")
                
                fixed_content = await client.call_chat_completion(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=4000,
                    temperature=API_TEMPERATURE,
                    account_id=account_id,
                )

                if not fixed_content:
                    raise Exception("AI autofix returned empty content")
                
                logger.info(f"AI autofix successful with model: {model}")
                return fixed_content.strip()
            
            except Exception as e:
                last_error = e
                logger.warning(f"Attempt {attempt + 1}/3 failed: {e}")
                if attempt == 2:  # Last attempt
                    logger.error(f"All qc attempts exhausted. Last error: {last_error}")
                    raise
                continue
        
        # Should not reach here
        logger.error(f"AI autofix failed after all attempts: {last_error}")
        return None

    except Exception as e:
        logger.error(f"AI autofix failed: {e}")
        return None
    finally:
        await client.close()


async def quality_check_and_fix(
    content: str,
    angle: dict[str, Any],
    format_type: str,
    enable_autofix: bool = True,
    max_fix_attempts: int = 2,
    autofix_threshold: int = QC_AUTOFIX_THRESHOLD,
    account_config: Optional[Dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Quality check with optional AI autofix.

    Args:
        content: Generated content
        angle: Original angle data
        format_type: Content format
        enable_autofix: Whether to attempt AI fixes
        max_fix_attempts: Max autofix attempts
        autofix_threshold: Only autofix if score < this value (default from settings)
        account_config: Optional account config for voice consistency check

    Returns:
        QC result dict with fixed_content
    """
    issues: list[str] = []
    cleaned_content = content.strip()
    resolved_format = format_type or detect_format(cleaned_content)

    if not cleaned_content:
        issues.append("Technical & Readability: empty content")

    # PRE-QC: Strip visual briefs and trim to TWEET_MAX_LENGTH chars for Single Tweet/Poll
    cleaned_content = _RE_CLEANUP_MARKERS.sub("", cleaned_content)
    cleaned_content = _RE_CLEANUP_VISUAL.sub("", cleaned_content)
    cleaned_content = _RE_CLEANUP_WHITESPACE.sub("\n\n", cleaned_content)
    cleaned_content = cleaned_content.strip()

    # PRE-QC: Fix Image format corruption (writer outputs "**. " instead of "**CAPTION:**")
    if resolved_format == "Image":
        # Pattern: **IMAGE:**\n\n**. [text]
        # Fix to: **IMAGE:**\n\n**CAPTION:**\n[text]
        if _RE_IMAGE_MARKER.match(cleaned_content):
            cleaned_content = _RE_IMAGE_CLEANUP.sub(
                "**IMAGE:**\n\n**CAPTION:**\n",
                cleaned_content,
            )
            logger.info(
                "Fixed Image format corruption: replaced '**.' with '**CAPTION:**'"
            )

    # Auto-trim if over TWEET_MAX_LENGTH chars for Single Tweet/Poll
    if resolved_format in ["Single Tweet", "Poll"]:
        marker_map = {
            "Single Tweet": "**SINGLE TWEET:**",
            "Poll": "**POLL:**",
        }
        marker = marker_map.get(resolved_format, "")
        body = cleaned_content.replace(marker, "").strip()

        # Remove ellipsis from end
        if body.endswith("..."):
            body = body[:-WHITESPACE_CLEANUP_THRESHOLD].rstrip()
            logger.info("Removed ellipsis from end of content")
        elif body.endswith("…."):
            body = body[:-2].rstrip()
            logger.info("Removed ellipsis from end of content")

        if len(body) > TWEET_MAX_LENGTH:
            # Trim at word boundary
            trimmed = body[:TWEET_MAX_LENGTH].rsplit(" ", 1)[0]
            # Remove ellipsis if trim created one
            if trimmed.endswith("..."):
                trimmed = trimmed[:-WHITESPACE_CLEANUP_THRESHOLD].rstrip()

            # Poll-specific: ensure question mark after trim
            if resolved_format == "Poll" and "?" not in trimmed:
                # Find last sentence with question mark before trim point
                sentences = body.split(".")
                for sent in sentences:
                    if "?" in sent and len(sent.strip()) <= TWEET_MAX_LENGTH:
                        trimmed = sent.strip()
                        break
                else:
                    # No question found, add question mark
                    if not trimmed.endswith("?"):
                        trimmed = trimmed.rstrip(".!,;") + "?"
                logger.info("Poll: ensured question mark after trim")

            if marker:
                cleaned_content = f"{marker}\n\n{trimmed}"
            else:
                cleaned_content = trimmed
            logger.info(
                f"Auto-trimmed content from {len(body)} to {len(trimmed)} chars"
            )
        else:
            # Update content with ellipsis removed
            if marker:
                cleaned_content = f"{marker}\n\n{body}"
            else:
                cleaned_content = body

    issues.extend(_detect_alignment_issues(cleaned_content, angle, resolved_format))

    # Optional: Check voice consistency if account_config provided
    if account_config:
        issues.extend(_check_voice_consistency(cleaned_content, account_config))

    critical_issues = [
        issue
        for issue in issues
        if "CRITICAL" in issue or issue.startswith("Format Error:")
    ]

    # Calculate initial score. Critical format issues must force autofix/fail path.
    score = 0 if critical_issues else max(0, 10 - len(issues))

    # Attempt autofix only if score below threshold and issues exist
    fixed_content = cleaned_content
    autofix_applied = False
    original_issues = []  # Track original issues before autofix
    
    # Extract account_id for retry budget tracking
    account_id = account_config.get("account_id", "unknown") if account_config else "unknown"

    if issues and enable_autofix and (score < autofix_threshold or critical_issues):
        logger.info(
            f"QC score {score}/10 below threshold {autofix_threshold}, attempting autofix..."
        )
        original_issues = issues.copy()  # Save original issues

        for attempt in range(1, max_fix_attempts + 1):
            fixed_attempt = await ai_autofix_content(
                fixed_content, issues, angle, resolved_format, account_id
            )

            if fixed_attempt:
                # Re-check fixed content
                recheck_issues = _detect_alignment_issues(
                    fixed_attempt, angle, resolved_format
                )
                recheck_critical = [
                    issue
                    for issue in recheck_issues
                    if "CRITICAL" in issue or issue.startswith("Format Error:")
                ]

                if not recheck_critical and (
                    not recheck_issues or len(recheck_issues) <= 2
                ):
                    # Fix successful
                    fixed_content = fixed_attempt
                    issues = recheck_issues
                    autofix_applied = True
                    logger.info(f"Autofix successful on attempt {attempt}")
                    break
                else:
                    # Still has issues, try again
                    logger.warning(
                        f"Autofix attempt {attempt} still has issues: {recheck_issues}"
                    )
                    fixed_content = fixed_attempt
                    issues = recheck_issues
            else:
                logger.warning(f"Autofix attempt {attempt} returned no content")
                break
    elif issues and enable_autofix:
        logger.info(
            f"QC score {score}/10 above threshold {autofix_threshold}, skipping autofix"
        )

    # Recalculate final score after autofix
    final_critical_issues = [
        issue
        for issue in issues
        if "CRITICAL" in issue or issue.startswith("Format Error:")
    ]
    final_score = 0 if final_critical_issues else max(0, 10 - len(issues))

    return {
        "passed": not final_critical_issues and (len(issues) == 0 or final_score >= QC_PASS_THRESHOLD),
        "overall_score": final_score,
        "issues": issues,
        "fixed_content": fixed_content,
        "format": resolved_format,
        "autofix_applied": autofix_applied,
        "original_issues": original_issues if autofix_applied else [],
    }


__all__ = ["detect_format", "quality_check_and_fix", "ai_autofix_content"]
