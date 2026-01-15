"""Template variable parsing utilities for {{user}} and {{char}}."""
from typing import Optional


def parse_template_variables(
    text: str,
    user_name: Optional[str] = None,
    char_name: Optional[str] = None
) -> str:
    """Parse template variables in text.
    
    Replaces:
    - {{user}} with user_name (or "User" if not provided)
    - {{char}} with char_name (or "Assistant" if not provided)
    
    Args:
        text: Text containing template variables
        user_name: Name of the user (defaults to "User")
        char_name: Name of the character (defaults to "Assistant")
    
    Returns:
        Text with template variables replaced
    """
    if not text:
        return text
    
    # Default values if not provided
    user_name = user_name or "User"
    char_name = char_name or "Assistant"
    
    # Replace template variables (case-sensitive)
    text = text.replace("{{user}}", user_name)
    text = text.replace("{{char}}", char_name)
    
    return text


def parse_stop_strings(
    stop_strings: Optional[list[str]],
    user_name: Optional[str] = None,
    char_name: Optional[str] = None
) -> Optional[list[str]]:
    """Parse template variables in stop strings.
    
    Args:
        stop_strings: List of stop strings that may contain template variables
        user_name: Name of the user (defaults to "User")
        char_name: Name of the character (defaults to "Assistant")
    
    Returns:
        List of stop strings with template variables replaced, or None if input was None
    """
    if stop_strings is None:
        return None
    
    return [parse_template_variables(s, user_name, char_name) for s in stop_strings]

