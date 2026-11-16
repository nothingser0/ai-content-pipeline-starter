"""
Text normalization utilities
Common text processing functions
"""


def normalize_text(text: str) -> str:
    """
    Normalize text for comparison.
    
    Converts to lowercase and collapses whitespace.
    
    Args:
        text: Input text
        
    Returns:
        Normalized text (lowercase, single spaces)
    """
    return " ".join(text.lower().split())
