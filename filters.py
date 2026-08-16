"""
Noise filtering for agent logs.

Removes harness-level metadata, tool chatter, and low-signal content
while preserving decisions, work products, and learnings.
"""

import re
from typing import Optional


class NoiseFilter:
    """Filters out harness noise from agent logs."""

    # Patterns to filter (noise)
    NOISE_PATTERNS = [
        # Tool invocation metadata
        r"<function_calls>.*?</function_calls>",
        # Permission prompts and responses
        r"Permission.*?to.*?[A-Z]",
        r"<system-reminder>.*?</system-reminder>",
        r"<total_tokens>.*?</total_tokens>",
        # Connection/authentication logs
        r"Authenticating.*?",
        r"Connecting to.*?",
        r"Session.*?established",
        # Token usage summaries
        r"Token usage:.*?$",
        r"Tokens? (left|used|remaining):.*?$",
        # Tool result metadata
        r"function_results>.*?</function_results>",
        # Bash execution details
        r"Bash tool:\s+.*?$",
        r"Running.*?bash.*?$",
    ]

    @staticmethod
    def is_noise(line: str) -> bool:
        """Check if a line is noise that should be filtered."""
        noise_keywords = [
            "function_calls",
            "function_results",
            "total_tokens",
            "Permission",
            "permission",
            "Authenticating",
            "Connecting",
            "established",
            "Token usage",
            "system-reminder",
        ]
        return any(kw in line for kw in noise_keywords)

    @staticmethod
    def filter_log(content: str) -> str:
        """Remove noise from log content while preserving signal."""
        lines = content.split("\n")
        filtered = []

        for line in lines:
            if NoiseFilter.is_noise(line):
                continue
            # Keep the line if it contains signal
            if line.strip() and not line.strip().startswith(("<", ">")):
                filtered.append(line)

        return "\n".join(filtered)

    @staticmethod
    def extract_key_content(content: str) -> dict:
        """
        Extract high-signal sections from log content.

        Returns a dict with keys like 'decisions', 'learnings', 'work_products', etc.
        """
        result = {
            "decisions": [],
            "learnings": [],
            "work_products": [],
            "blockers": [],
            "accomplishments": [],
        }

        lines = content.split("\n")
        current_section = None

        for line in lines:
            stripped = line.strip()

            # Detect section headers
            if any(x in stripped.lower() for x in ["decision", "decided"]):
                current_section = "decisions"
            elif any(x in stripped.lower() for x in ["learning", "learned", "insight"]):
                current_section = "learnings"
            elif any(x in stripped.lower() for x in ["work product", "artifact", "created", "built"]):
                current_section = "work_products"
            elif any(x in stripped.lower() for x in ["blocker", "blocked", "issue", "problem"]):
                current_section = "blockers"
            elif any(x in stripped.lower() for x in ["accomplish", "completed", "finished", "done"]):
                current_section = "accomplishments"

            # Add content to current section
            if current_section and stripped and not NoiseFilter.is_noise(line):
                result[current_section].append(stripped)

        return result


def extract_continuity_threads(content: str) -> list[str]:
    """Extract open threads that should continue to the next instance."""
    threads = []

    # Look for common patterns indicating unfinished work
    patterns = [
        r"TODO:.*?$",
        r"FIXME:.*?$",
        r"next step:.*?$",
        r"pending:.*?$",
        r"waiting for:.*?$",
    ]

    for pattern in patterns:
        matches = re.findall(pattern, content, re.IGNORECASE | re.MULTILINE)
        threads.extend(matches)

    return threads
