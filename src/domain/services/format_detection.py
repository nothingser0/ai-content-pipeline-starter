"""
Format detection utilities
Detect content format from markers in generated content
"""

from typing import Literal


def detect_format(content: str) -> Literal["Thread", "Poll", "Image", "Single Tweet"]:
    """
    Detect content format from markers in generated content.
    
    Args:
        content: Generated content string
        
    Returns:
        Format name: "Thread", "Poll", "Image", or "Single Tweet"
    """
    # Normalize for case-insensitive matching
    upper_content = content.upper()
    
    # Check for explicit format markers (most reliable)
    if "**IMAGE:**" in upper_content:
        return "Image"
    if "**POLL:**" in upper_content:
        return "Poll"
    if "**SINGLE TWEET:**" in upper_content:
        return "Single Tweet"
    if "**THREAD:**" in upper_content:
        return "Thread"
    
    # Check for structural markers
    if "TWEET 1:" in upper_content:
        return "Thread"
    if "SLIDE 1:" in upper_content:
        return "Image"
    
    # Default to Single Tweet
    return "Single Tweet"
