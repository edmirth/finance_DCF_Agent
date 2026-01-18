"""
Utility class for parsing structured content from LLM output.

This module provides generic methods for extracting various structured elements
from LLM responses, including XML tags, sections, and numbered lists.
"""

from typing import Optional, List
import re


class LLMOutputParser:
    """Utility class for parsing structured content from LLM output"""

    @staticmethod
    def extract_xml_tag(text: str, tag: str) -> Optional[str]:
        """
        Extract content from XML-style tags (e.g., <thinking>...</thinking>).

        Args:
            text: The text to parse
            tag: The XML tag name (without angle brackets)

        Returns:
            Concatenated content from all matching tags, or None if no matches

        Example:
            >>> extract_xml_tag("<thinking>Plan A</thinking> text <thinking>Plan B</thinking>", "thinking")
            "Plan A Plan B"
        """
        if not text:
            return None

        pattern = rf'<{tag}>(.*?)</{tag}>'
        matches = re.findall(pattern, text, re.DOTALL)

        if matches:
            return ' '.join(m.strip() for m in matches)
        return None

    @staticmethod
    def extract_section(
        text: str,
        start_markers: List[str],
        end_markers: Optional[List[str]] = None,
        strip_marker: bool = True,
        min_length: int = 0
    ) -> Optional[str]:
        """
        Extract a section from text between markers.

        Args:
            text: The text to parse
            start_markers: List of possible section start patterns (e.g., ['thought:', 'thinking:'])
            end_markers: List of patterns that end the section (e.g., ['action:', 'plan:'])
                        If None, extracts to end of text
            strip_marker: Whether to remove the start marker from result
            min_length: Minimum length for result to be considered valid

        Returns:
            Extracted section text, or None if not found or too short

        Example:
            >>> extract_section("Thought: analyze data\\nAction: call tool",
            ...                 ['thought:'], ['action:'])
            "analyze data"
        """
        if not text:
            return None

        text_lower = text.lower()
        start_pos = -1
        marker_len = 0

        # Find first matching start marker (case-insensitive)
        for marker in start_markers:
            pos = text_lower.find(marker.lower())
            if pos != -1 and (start_pos == -1 or pos < start_pos):
                start_pos = pos
                marker_len = len(marker)

        if start_pos == -1:
            return None

        # Extract content after start marker
        content_start = start_pos + marker_len if strip_marker else start_pos
        remaining = text[content_start:]

        # Find end position (if end_markers provided)
        if end_markers:
            remaining_lower = remaining.lower()
            end_pos = len(remaining)
            for marker in end_markers:
                pos = remaining_lower.find(marker.lower())
                if pos != -1 and pos < end_pos:
                    end_pos = pos
            remaining = remaining[:end_pos]

        result = remaining.strip()
        return result if len(result) > min_length else None

    @staticmethod
    def extract_multiline_section(
        text: str,
        start_marker: str,
        end_markers: List[str],
        min_length: int = 0
    ) -> Optional[str]:
        """
        Extract a multi-line section that spans multiple lines.

        Similar to extract_section but optimized for multi-line content
        where the start marker is on one line and content follows.

        Args:
            text: The text to parse
            start_marker: Section start pattern (e.g., 'reflection:')
            end_markers: Patterns that end the section
            min_length: Minimum length for result to be considered valid

        Returns:
            Extracted multi-line section, or None if not found

        Example:
            >>> extract_multiline_section(
            ...     "Reflection:\\nLine 1\\nLine 2\\nAction: next",
            ...     "reflection:", ["action:"]
            ... )
            "Line 1\\nLine 2"
        """
        if not text:
            return None

        lines = text.strip().split('\n')
        content_lines = []
        in_section = False

        for line in lines:
            line_stripped = line.strip()
            line_lower = line_stripped.lower()

            # Check if we're starting the section
            if line_lower.startswith(start_marker.lower()):
                in_section = True
                # Include any content after the marker on the same line
                content_after_marker = line_stripped[len(start_marker):].strip()
                if content_after_marker:
                    content_lines.append(content_after_marker)
                continue

            # Check if we've hit an end marker
            if in_section and any(line_lower.startswith(marker.lower()) for marker in end_markers):
                break

            # Collect content lines
            if in_section and line_stripped:
                content_lines.append(line_stripped)

        result = ' '.join(content_lines).strip()
        return result if len(result) > min_length else None

    @staticmethod
    def extract_numbered_list(
        text: str,
        min_items: int = 1,
        min_item_length: int = 0,
        patterns: Optional[List[str]] = None
    ) -> Optional[List[str]]:
        """
        Extract numbered items from text (1. 2. 3. or 1) 2) 3) patterns).

        Args:
            text: The text to parse
            min_items: Minimum number of items required for list to be valid
            min_item_length: Minimum length for each item to be included
            patterns: Optional custom regex patterns for item prefixes
                     Default: ['\\d+[\\.\\):]', '-', '\\*', 'Phase\\s+\\d+:?']

        Returns:
            List of extracted items, or None if fewer than min_items found

        Example:
            >>> extract_numbered_list("1. First step\\n2. Second step\\n3. Third step")
            ["First step", "Second step", "Third step"]
        """
        if not text:
            return None

        if patterns is None:
            # Default patterns: "1.", "1)", "1:", "-", "*", "Phase 1:"
            patterns = [r'^\d+[\.\):]', r'^-', r'^\*', r'^Phase\s+\d+:?']

        items = []
        combined_pattern = '|'.join(f'({p})' for p in patterns)

        for line in text.split('\n'):
            line = line.strip()
            match = re.match(combined_pattern, line)
            if match:
                # Remove the numbering/bullet prefix
                item = re.sub(combined_pattern + r'\s*', '', line).strip()
                if item and len(item) > min_item_length:
                    items.append(item)

        return items if len(items) >= min_items else None

    @staticmethod
    def clean_code_artifacts(text: str) -> str:
        """
        Clean common code artifacts from text (code blocks, markdown, etc.).

        Args:
            text: The text to clean

        Returns:
            Cleaned text

        Example:
            >>> clean_code_artifacts("```python\\ncode\\n``` Some text")
            "Some text"
        """
        if not text:
            return ""

        # Remove markdown code blocks
        text = re.sub(r'```[\w]*\n.*?\n```', '', text, flags=re.DOTALL)
        # Remove inline code
        text = re.sub(r'`[^`]*`', '', text)
        # Remove extra whitespace
        text = ' '.join(text.split())

        return text.strip()

    @staticmethod
    def extract_search_query(tool_input: dict) -> Optional[str]:
        """
        Extract search query from tool input (web search tools).

        Args:
            tool_input: Tool input dictionary

        Returns:
            Search query string, or None if not found

        Example:
            >>> extract_search_query({"query": "Tesla stock price"})
            "Tesla stock price"
        """
        if not isinstance(tool_input, dict):
            return None

        # Try common query field names
        for field in ['query', 'search_query', 'q', 'question']:
            if field in tool_input:
                return str(tool_input[field])

        return None
