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
        # (previously `.*?` with no trailing anchor here, which matches
        # zero characters and only strips the literal keyword itself --
        # anchored to end-of-line now that this is actually wired in)
        r"Authenticating.*$",
        r"Connecting to.*$",
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
        """Remove noise from log content while preserving signal.

        Two passes: first the multi-line/regex NOISE_PATTERNS (block-level
        noise like <function_calls>...</function_calls> that a single-line
        keyword check can't see), then the per-line keyword check. Previously
        NOISE_PATTERNS was defined but never applied anywhere -- this was a
        real bug (found while dogfooding, Agent-Of/miller#3): the README's
        "Tool invocation metadata" / "Bash execution details" removal claims
        were not actually happening.
        """
        for pattern in NoiseFilter.NOISE_PATTERNS:
            content = re.sub(pattern, "", content, flags=re.DOTALL | re.MULTILINE | re.IGNORECASE)

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


class PIIRedactor:
    """Detects and redacts personally identifiable information from logs."""

    # Patterns for PII/secrets to redact
    REDACTION_PATTERNS = [
        # File paths: C:\Users\username\... or /Users/... or /home/...
        # Matches 1-2 literal backslashes per separator: a single backslash
        # after json.loads() has decoded a real session's escaped path text,
        # or a doubled backslash if this ever runs against still-JSON-escaped
        # raw text. The original single-backslash-only pattern silently
        # never matched real (decoded) session content on Windows -- found
        # while dogfooding against a real transcript (Agent-Of/miller#3).
        (r"[A-Za-z]:\\{1,2}Users\\{1,2}[a-zA-Z0-9_.-]+", "{LOCAL_PATH}"),
        (r"/Users/[a-zA-Z0-9_.-]+", "{LOCAL_PATH}"),
        (r"/home/[a-zA-Z0-9_.-]+", "{LOCAL_PATH}"),
        # Session IDs: UUID format (8-4-4-4-12 hex)
        (r"\b[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\b", "{SESSION_ID}"),
        # API keys: common patterns like "Bearer ", "token=", "key=", "secret="
        (r"(Bearer|token|key|secret|password)\s*=\s*['\"]?[A-Za-z0-9_-]{20,}['\"]?", r"\1={SECRET}"),
        # Email addresses
        (r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b", "{EMAIL}"),
        # AWS-style credentials (AKIA...)
        (r"\bAKIA[0-9A-Z]{16}\b", "{AWS_KEY}"),
        # Generic secrets (40+ char hex strings often used for tokens)
        (r"\b[a-f0-9]{40,}\b", "{SECRET_HEX}"),
    ]

    @staticmethod
    def redact(content: str) -> str:
        """Redact PII from content, replacing with generic placeholders."""
        for pattern, replacement in PIIRedactor.REDACTION_PATTERNS:
            content = re.sub(pattern, replacement, content, flags=re.IGNORECASE)
        return content

    @staticmethod
    def contains_pii(content: str) -> bool:
        """Check if content contains any detectable PII patterns."""
        for pattern, _ in PIIRedactor.REDACTION_PATTERNS:
            if re.search(pattern, content, flags=re.IGNORECASE):
                return True
        return False


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
