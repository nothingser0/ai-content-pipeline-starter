#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Final package generator with improved structure and actionable format.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from infrastructure.constants import TWEET_MAX_LENGTH
from infrastructure.storage.versioning import VersioningSystem

# Pre-compiled regex patterns
_RE_VISUAL_BRIEF = re.compile(r"\s*VISUAL BRIEF:.*$", re.DOTALL)
_RE_HEADER_IMAGE_BRIEF = re.compile(r"\s*HEADER IMAGE BRIEF:.*$", re.DOTALL)
_RE_ADDITIONAL_IMAGE_BRIEFS = re.compile(r"\s*ADDITIONAL IMAGE BRIEFS:.*$", re.DOTALL)
_RE_IMAGE_CAPTION = re.compile(
    r"\*\*IMAGE:\*\*\s*\n\s*\n\s*\*\*Caption:\*\*\s*\n(.+?)(?=\n\n|\Z)", re.DOTALL
)
_RE_POLL_QUESTION = re.compile(
    r"\*\*POLL:\*\*\s*\n\s*\n\s*\*\*Question:\*\*\s*\n(.+?)(?=\n\n|\Z)", re.DOTALL
)
_RE_CORE_IDEA = re.compile(r"### CORE IDEA\s*\n(.+?)(?=\n\n|###)", re.DOTALL)
_RE_GENERATION_PROMPT = re.compile(
    r"### GENERATION PROMPT\s*\n(.+?)(?=\n\n|###|\Z)", re.DOTALL
)
_RE_SLIDE_BRIEFS = re.compile(
    r"\*\*Slide (\d+): VISUAL BRIEF\*\*.*?### GENERATION PROMPT\s*\n(.+?)(?=\n\n\*\*Slide|\Z)",
    re.DOTALL,
)


def _format_content_section(content: str, format_type: str) -> list[str]:
    """Format content section based on format type."""
    # Strip VISUAL BRIEF section from content
    content = _RE_VISUAL_BRIEF.sub("", content)
    content = _RE_HEADER_IMAGE_BRIEF.sub("", content)
    content = _RE_ADDITIONAL_IMAGE_BRIEFS.sub("", content)
    content = content.strip()

    lines = []

    if format_type == "Single Tweet":
        # Remove marker for char count
        body = content.replace("**SINGLE TWEET:**", "").strip()
        char_count = len(body)
        lines.extend(
            [
                "TWEET:",
                body,
                f"[{char_count}/{TWEET_MAX_LENGTH}]",
            ]
        )

    elif format_type == "Poll":
        # Remove marker for char count
        body = content.replace("**POLL:**", "").strip()
        char_count = len(body)
        lines.extend(
            [
                "TWEET (pertanyaan):",
                body,
                f"[{char_count}/{TWEET_MAX_LENGTH}]",
            ]
        )

    elif format_type == "Image":
        # For Image, only show CAPTION, not slide details
        caption_match = _RE_IMAGE_CAPTION.search(content)
        if caption_match:
            caption = caption_match.group(1).strip()
            char_count = len(caption)
            lines.extend(
                [
                    "CAPTION:",
                    caption,
                    f"[{char_count}/{TWEET_MAX_LENGTH}]",
                    "",
                    "(Slide details in VISUAL section)",
                ]
            )
        else:
            lines.append(content)

    elif format_type == "Thread":
        # Parse tweets only, no image briefs
        lines.append(content)

    else:
        lines.append(content)

    return lines


def _format_visual_section(package_data: dict[str, Any]) -> list[str]:
    """Format visual section based on format and visual status."""
    lines = []

    format_type = package_data.get("format", "Unknown")
    visual_brief = package_data.get("visual_brief") or ""
    visual_generated = package_data.get("visual_generated", False) and bool(visual_brief)
    thread_images = package_data.get("thread_images") or {}
    topic = str(package_data.get("topic") or "topic").lower().replace(" ", "_")[:30]

    if not visual_generated or not visual_brief:
        if format_type in ["Single Tweet", "Poll"]:
            lines.extend(["VISUAL: Skipped (no image needed or disabled)"])
        elif format_type == "Image":
            lines.extend(["VISUAL PLAN: (Skipped or disabled)"])
        elif format_type == "Thread":
            lines.extend(["VISUAL: Skipped (disabled or not generated)"])
        else:
            lines.extend(["VISUAL: None"])
        return lines

    if format_type in ["Single Tweet", "Poll"]:
        lines.extend(
            [
                "GENERATION PROMPT:",
                _extract_generation_prompt(visual_brief),
                "",
                "DREMINA SAFE EDIT:",
                _extract_dremina_safe_edit(visual_brief),
            ]
        )

    elif format_type == "Image":
        lines.extend(
            [
                "VISUAL PLAN:",
                "",
                _extract_image_slides(visual_brief, topic),
            ]
        )

    elif format_type == "Thread":
        if thread_images and len(thread_images) > 1:
            # Multiple images
            lines.extend(
                [
                    f"VISUAL: Required ({len(thread_images)} images)",
                    "",
                ]
            )

            for tweet_num in sorted(thread_images.keys()):
                if tweet_num == 1:
                    lines.extend(
                        [
                            "HEADER IMAGE (Tweet 1):",
                            "",
                            "GENERATION PROMPT:",
                            _extract_generation_prompt_from_brief(
                                thread_images[tweet_num]
                            ),
                            "",
                        ]
                    )
                else:
                    lines.extend(
                        [
                            f"ADDITIONAL IMAGE (Tweet {tweet_num}):",
                            "",
                            "GENERATION PROMPT:",
                            _extract_generation_prompt_from_brief(
                                thread_images[tweet_num]
                            ),
                            "",
                        ]
                    )
        else:
            # Header only
            lines.extend(
                [
                    "GENERATION PROMPT:",
                    _extract_generation_prompt(visual_brief),
                    "",
                    "DREMINA SAFE EDIT:",
                    _extract_dremina_safe_edit(visual_brief),
                ]
            )

    return lines


def _extract_generation_prompt(visual_brief: Optional[str]) -> str:
    """Extract generation prompt from visual brief."""
    if not visual_brief:
        return "(No generation prompt found)"
    match = _RE_GENERATION_PROMPT.search(visual_brief)
    if match:
        return match.group(1).strip()
    return "(No generation prompt found)"


def _extract_generation_prompt_from_brief(brief: Optional[str]) -> str:
    """Extract generation prompt from brief text."""
    # For thread images, brief is already the prompt
    return brief.strip() if brief else "(No prompt)"


def _extract_brief_summary(visual_brief: Optional[str]) -> str:
    """Extract brief summary from visual brief."""
    if not visual_brief:
        return "(No brief summary)"
    match = _RE_CORE_IDEA.search(visual_brief)
    if match:
        return match.group(1).strip()
    return "(No brief summary)"


def _extract_editing_notes(visual_brief: Optional[str]) -> str:
    """Extract editing notes from visual brief."""
    if not visual_brief:
        return "(No editing notes)"
    # Try to find editing notes or text overlay section
    match = re.search(
        r"### (?:EDITING NOTES|TEXT OVERLAY)\s*\n(.+?)(?=\n\n|###|$)",
        visual_brief,
        re.DOTALL,
    )
    if match:
        return match.group(1).strip()
    return "(No editing notes)"


def _extract_dremina_safe_edit(visual_brief: Optional[str]) -> str:
    """Extract Dreamina safe edit prompt from visual brief."""
    if not visual_brief:
        return "(No Dreamina safe edit prompt found)"
    # Look for DREAMINA SAFE EDIT PROMPT within EDITING NOTES section
    match = re.search(
        r"DREAMINA SAFE EDIT PROMPT[^:]*:\s*\n(.+?)(?=\n\n---|###|$)",
        visual_brief,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    return "(No Dreamina safe edit prompt found)"


def _extract_image_slides(visual_brief: Optional[str], topic: str) -> str:
    """Extract image slides information."""
    if not visual_brief:
        return "(No slide information found)"
    slides = []
    slide_matches = _RE_SLIDE_BRIEFS.finditer(visual_brief)

    for match in slide_matches:
        slide_num = match.group(1)
        prompt = match.group(2).strip()
        slides.append(f"SLIDE {slide_num}:\nGeneration Prompt:\n{prompt}\n")

    if slides:
        return "\n".join(slides)
    return "(No slide information found)"


def _extract_shared_notes(visual_brief: Optional[str]) -> str:
    """Extract shared visual notes."""
    if not visual_brief:
        return "(No shared notes)"
    notes = []

    # Extract color
    color_match = re.search(
        r"### COLOR & GRADE\s*\n(.+?)(?=\n\n|###)", visual_brief, re.DOTALL
    )
    if color_match:
        notes.append(f"Color: {color_match.group(1).strip()}")

    # Extract style
    style_match = re.search(
        r"### STYLE REFERENCE\s*\n(.+?)(?=\n\n|###)", visual_brief, re.DOTALL
    )
    if style_match:
        notes.append(f"Style: {style_match.group(1).strip()}")

    return "\n".join(notes) if notes else "(No shared notes)"


def _format_engagement_section(engagement_strategy: Optional[str]) -> list[str]:
    """Format engagement strategy section."""
    if not engagement_strategy:
        return ["(No engagement strategy generated)"]

    import re

    lines = []

    # Extract posting time
    time_match = re.search(
        r"POSTING TIME:(.+?)(?=\n\n|HASHTAGS:|$)", engagement_strategy, re.DOTALL
    )
    if time_match:
        lines.append(f"POSTING TIME:{time_match.group(1).strip()}")

    # Extract hashtags
    hashtag_match = re.search(
        r"HASHTAGS:(.+?)(?=\n\n|CTA:|$)", engagement_strategy, re.DOTALL
    )
    if hashtag_match:
        lines.append(f"\nHASHTAGS:{hashtag_match.group(1).strip()}")

    # Extract CTA
    cta_match = re.search(
        r"CTA:(.+?)(?=\n\n|FIRST COMMENT:|$)", engagement_strategy, re.DOTALL
    )
    if cta_match:
        lines.append(f"\nCTA:{cta_match.group(1).strip()}")

    # Extract first comment
    comment_match = re.search(
        r"FIRST COMMENT:(.+?)(?=\n\n|PLATFORM STRATEGY:|$)",
        engagement_strategy,
        re.DOTALL,
    )
    if comment_match:
        lines.append(f"\nFIRST COMMENT:{comment_match.group(1).strip()}")

    # Extract platform strategy
    platform_match = re.search(
        r"PLATFORM STRATEGY:(.+?)$", engagement_strategy, re.DOTALL
    )
    if platform_match:
        lines.append(f"\nREPURPOSE OPPORTUNITIES:{platform_match.group(1).strip()}")

    return lines if lines else [engagement_strategy.strip()]


def build_package_text(package_data: dict[str, Any]) -> str:
    """Build readable final package text with improved structure."""
    account = package_data.get("account", {})
    angle = package_data.get("angle", {})
    qc = package_data.get("qc", {})
    format_type = package_data.get("format", "Unknown")
    content = package_data.get("content", "")
    engagement_strategy = package_data.get("engagement_strategy")

    # Extract posting time from engagement
    posting_time = "TBD"
    if engagement_strategy:
        import re

        time_match = re.search(r"POSTING TIME:\s*(.+?)(?:\n|$)", engagement_strategy)
        if time_match:
            posting_time = time_match.group(1).strip()

    # Build header
    lines = [
        "=" * 72,
        "21 ACCOUNTS CONTENT PIPELINE",
        "=" * 72,
        f"Account:        @{account.get('username', 'unknown')}",
        f"Niche:          {account.get('niche', 'unknown')}",
        f"Topic:          {package_data.get('topic', '')}",
        f"Angle:          {angle.get('title', 'Untitled')}",
        f"Format:         {format_type}",
        f"Generated:      {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Scheduled:      {posting_time}",
        "",
        "STATUS: [ ] Draft  [ ] Ready  [ ] Scheduled  [ ] Posted",
        f"QC Score: {qc.get('overall_score', 'N/A')}/10  |  QC Passed: {qc.get('passed', False)}",
        "",
        "=" * 72,
        "1. CONTENT",
        "=" * 72,
        "",
    ]

    # Add content section
    lines.extend(_format_content_section(content, format_type))

    # Add visual section
    lines.extend(
        [
            "",
            "=" * 72,
            "2. VISUAL",
            "=" * 72,
            "",
        ]
    )
    lines.extend(_format_visual_section(package_data))

    # Add engagement section
    lines.extend(
        [
            "",
            "=" * 72,
            "3. ENGAGEMENT STRATEGY",
            "=" * 72,
            "PLATFORM: Twitter/X",
            "",
        ]
    )
    lines.extend(_format_engagement_section(engagement_strategy))

    # Add QC section
    lines.extend(
        [
            "",
            "=" * 72,
            "4. QC NOTES",
            "=" * 72,
            f"SCORE: {qc.get('overall_score', 'N/A')}/10",
            f"PASSED: {qc.get('passed', False)}",
            "",
        ]
    )

    # Show autofix info if applied
    autofix_applied = qc.get("autofix_applied", False)
    if autofix_applied:
        lines.append("✓ QC AUTOFIX APPLIED")

        # Show what was fixed (from original issues before autofix)
        original_issues = qc.get("original_issues", [])
        if original_issues:
            lines.append("")
            lines.append("Issues fixed by autofix:")
            for issue in original_issues:
                lines.append(f"  ✓ {issue}")
        lines.append("")

    # Show remaining issues (if any)
    if qc.get("issues"):
        lines.append("REMAINING ISSUES:")
        for issue in qc.get("issues", []):
            lines.append(f"[ ] {issue}")
    else:
        if not autofix_applied:
            lines.append("No issues found.")
        else:
            lines.append("All issues resolved by autofix.")

    # Add performance tracking section
    lines.extend(
        [
            "",
            "=" * 72,
            "5. PERFORMANCE (isi setelah posting)",
            "=" * 72,
            "Posted At:",
            "Impressions:",
            "Engagements:",
            "Replies:",
            "Saves/Bookmarks:",
            "Best performing element:",
            "Notes for next content:",
            "",
        ]
    )

    return "\n".join(lines)


def create_final_package(package_data: dict[str, Any], output_file: str | Path) -> Path:
    """Write final package file with optional versioning."""
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    content = build_package_text(package_data)
    output_path.write_text(content, encoding="utf-8")
    
    # Save version if enabled
    if os.getenv("ENABLE_VERSIONING", "0") == "1":
        account_id = package_data.get("account_id", "unknown")
        topic = package_data.get("topic", "unknown")
        qc_score = package_data.get("qc", {}).get("score", 0.0)
        model = package_data.get("model", "unknown")
        
        versioning = VersioningSystem(account_id, output_path.parent)
        version_id = versioning.save_version(topic, content, qc_score, model)
        
        if version_id:
            from infrastructure.logging.logger import get_logger
            logger = get_logger(__name__)
            logger.info(f"Saved as {version_id} for '{topic}'")
    
    return output_path


__all__ = ["build_package_text", "create_final_package"]
