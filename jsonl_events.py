"""
Real Claude Code session JSONL parsing.

This module is the actual fix for MILLER's core bug (Agent-Of/miller#3):
the original slurper never called json.loads on session content and
instead keyword/substring-matched raw text, which cannot distinguish
real message text from JSON syntax, tool-call arguments, or base64
signature blobs.

Every function here parses each line as real JSON first. Nothing in
this module (or in slurper.py's real-JSONL path) should ever run a
text search directly against an undecoded line.

Schema notes (verified directly against a real multi-entrypoint,
multi-compaction Claude Code session transcript, not assumed from
documentation):

- Each line is one JSON object. Common top-level keys: `type`
  ("user" | "assistant" | "system" | "summary" | "queue-operation" |
  others), `uuid`, `parentUuid`, `sessionId`, `timestamp` (ISO 8601),
  `entrypoint` ("cli" | "claude-vscode" | "claude-desktop" | others),
  `isSidechain`, `cwd`, `gitBranch`, `version`.
- `user`/`assistant` events carry `message.role` and `message.content`,
  which is EITHER a plain string OR a list of content blocks, each
  with its own `type` ("text", "tool_use", "tool_result", "thinking",
  ...). Only "text" blocks (and plain string content) are real
  human/model-facing prose; "tool_use"/"tool_result"/"thinking" blocks
  are structured data (tool names, JSON args, base64 signatures) that
  must never be scanned for signal the way prose is.
- Compaction boundaries are `type == "system"` events with
  `subtype == "compact_boundary"`. Their `parentUuid` is null; the
  event they logically continue from is in `logicalParentUuid`
  instead (a same-file field, not a cross-file bridge -- confirmed:
  it points at the `tailUuid` of the segment that was just
  compacted). `compactMetadata` holds `trigger` ("auto"/"manual"),
  `preTokens`, `postTokens`, `durationMs`, `cumulativeDroppedTokens`,
  `preservedSegment` ({headUuid, anchorUuid, tailUuid}), and
  `preservedMessages` ({anchorUuid, uuids, allUuids} -- `uuids` is a
  strict subset of `allUuids` in observed data, e.g. 227 vs 324 on a
  boundary from real data; which one is "the" preserved set is not
  fully documented, so both are surfaced rather than guessing).
"""

import json
from pathlib import Path
from typing import Iterator, Optional

# Event types that plausibly indicate a real Claude Code session line,
# used only to sniff a file -- never used as a substring match against
# raw text, always checked against an already-parsed dict.
_REAL_EVENT_TYPES = {"user", "assistant", "system", "summary", "queue-operation"}


def iter_jsonl_events(path: Path) -> Iterator[dict]:
    """
    Stream a JSONL file, yielding one parsed dict per valid line.

    Malformed lines are skipped (never raised on) -- real session files
    can be truncated mid-write if a session ends abruptly. Streaming
    line-by-line keeps memory bounded regardless of file size (a real
    session transcript can be hundreds of MB).
    """
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                yield obj


def iter_jsonl_events_sized(path: Path) -> Iterator[tuple[dict, int]]:
    """
    Like iter_jsonl_events, but also yields each line's raw UTF-8 byte
    length alongside the parsed event -- used by the slurper to report an
    honest raw_log_length per compaction segment without re-serializing
    (and thereby distorting) the parsed JSON.
    """
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                yield obj, len(stripped.encode("utf-8"))


def looks_like_real_session(path: Path, sniff_lines: int = 5) -> bool:
    """
    Sniff whether a file is a real Claude Code session JSONL, as opposed
    to a plain-text log (including this library's own legacy mock
    format). Reads only the first few lines, not the whole file.

    A file counts as "real" if at least one of the first few
    successfully-parsed JSON lines has a recognized `type` value.
    """
    for i, obj in enumerate(iter_jsonl_events(path)):
        if obj.get("type") in _REAL_EVENT_TYPES:
            return True
        if i + 1 >= sniff_lines:
            break
    return False


def is_compact_boundary(event: dict) -> bool:
    """True if this event is a real compaction boundary marker."""
    return event.get("type") == "system" and event.get("subtype") == "compact_boundary"


def extract_text_blocks(event: dict) -> list[str]:
    """
    Extract only real human/model-facing prose from a user/assistant
    event -- never tool_use input, tool_result output, or thinking
    signatures. Returns an empty list for non-message events.
    """
    message = event.get("message")
    if not isinstance(message, dict):
        return []

    content = message.get("content")
    texts: list[str] = []

    if isinstance(content, str):
        if content.strip():
            texts.append(content)
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if isinstance(text, str) and text.strip():
                    texts.append(text)

    return texts


def boundary_summary(event: dict) -> dict:
    """
    Extract the useful, verified fields from a compact_boundary event.
    Returns {} for anything that isn't actually a boundary.
    """
    if not is_compact_boundary(event):
        return {}

    meta = event.get("compactMetadata") or {}
    preserved = meta.get("preservedMessages") or {}

    return {
        "timestamp": event.get("timestamp"),
        "trigger": meta.get("trigger"),
        "pre_tokens": meta.get("preTokens"),
        "post_tokens": meta.get("postTokens"),
        "duration_ms": meta.get("durationMs"),
        "cumulative_dropped_tokens": meta.get("cumulativeDroppedTokens"),
        "logical_parent_uuid": event.get("logicalParentUuid"),
        "preserved_uuid_count": len(preserved.get("uuids", [])),
        "preserved_all_uuid_count": len(preserved.get("allUuids", [])),
    }


def event_entrypoint(event: dict) -> Optional[str]:
    """Return the entrypoint tag on an event, if present."""
    return event.get("entrypoint")


def event_timestamp(event: dict) -> Optional[str]:
    """Return the ISO timestamp on an event, if present."""
    return event.get("timestamp")
