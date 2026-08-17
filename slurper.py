"""
Core agent compaction slurper.

Reads agent session logs and artifacts, extracts high-signal content,
and yields CompactionChunk objects one compaction at a time.

Two source kinds are supported:

- **Real Claude Code session JSONL** (source_kind="real_jsonl"): any
  `.jsonl` file that sniffs as a real session transcript (see
  jsonl_events.looks_like_real_session). Discovered regardless of
  filename -- real sessions are named by session UUID, not by any
  compaction-number convention. Compaction boundaries come from the
  file's own `compact_boundary` system events, not from filenames.
  Signal is extracted only from real message text blocks, never from
  raw JSON syntax, tool_use arguments, or thinking-block signatures.

- **Legacy plain-text logs** (source_kind="legacy_text"): the
  library's original mock-data format (`👽[N]` / `compaction_N` /
  `session_N` in the filename, `Decision:`/`Learning:`/etc. headers in
  the body). Kept for backward compatibility with existing consumers
  and the bundled demo/tests -- this is NOT what a real Claude Code
  session file looks like.

This is the fix for Agent-Of/miller#3: previously `.jsonl` files were
treated identically to `.log`/`.txt`/`.md` (regex/keyword matched as
opaque text), so real session files were either invisible (no
compaction number in a UUID filename) or produced garbage once that
was worked around (every JSON line containing a stray keyword
substring got misclassified as signal).
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional

from checkpoints import CheckpointManager
from filters import NoiseFilter, PIIRedactor, extract_continuity_threads
from jsonl_events import (
    boundary_summary,
    event_entrypoint,
    event_timestamp,
    extract_text_blocks,
    is_compact_boundary,
    iter_jsonl_events_sized,
    looks_like_real_session,
)
from models import CompactionChunk, ContinuityThread, Decision, WorkProduct


class AgentSlurper:
    """Streaming agent compaction slurper."""

    def __init__(
        self,
        agent_dir: str,
        checkpoint_dir: Optional[str] = None,
        session_id: Optional[str] = None,
    ):
        """
        Initialize the slurper.

        Args:
            agent_dir: Either (a) the path to one specific real Claude Code
                session `.jsonl` file, or (b) a directory containing agent
                session logs. A real Claude Code project directory
                routinely holds MANY unrelated top-level session files
                (past, separate conversations) plus per-session sidecar
                subdirectories (named after a session UUID, holding
                subagent transcripts / tool-results -- internal plumbing,
                never additional top-level sessions). Passing a directory
                processes every top-level real session file found in it
                (each contributing its own independently-tagged segments,
                never merged together) -- pass a specific file, or set
                `session_id`, when you mean one particular session.
                Sidecar subdirectories are never descended into for real
                session discovery (a real fix for a real bug: they used
                to be, silently pooling unrelated subagent transcripts and
                other sessions' data into the total -- Agent-Of/miller#3
                follow-up, found during dogfooding of this very rewrite).
            checkpoint_dir: Directory for checkpoint files (defaults to agent_dir/.checkpoints,
                or the parent directory's .checkpoints when agent_dir is a file)
            session_id: When agent_dir is a directory, restrict real-session
                discovery to the single top-level file named
                `<session_id>.jsonl`, ignoring any other real session files
                present. Ignored when agent_dir is already a specific file.
        """
        candidate = Path(agent_dir)
        if not candidate.exists():
            raise ValueError(f"Agent directory not found: {agent_dir}")

        self._explicit_file: Optional[Path] = candidate if candidate.is_file() else None
        self._session_id = session_id
        self.agent_dir = candidate if candidate.is_dir() else candidate.parent

        if checkpoint_dir is None:
            checkpoint_dir = str(self.agent_dir / ".checkpoints")

        self.checkpoint_manager = CheckpointManager(checkpoint_dir)
        self._sources = self._discover_sources()
        self.total_bytes = self._calculate_total_bytes()

    def _calculate_total_bytes(self) -> int:
        """Total bytes across only the files actually discovered as sources
        (not a blind directory walk) -- used solely as the checkpoint
        progress-percent denominator."""
        total = 0
        for path in self._sources["real"]:
            try:
                total += os.path.getsize(path)
            except OSError:
                pass
        for paths in self._sources["legacy"].values():
            for path in paths:
                try:
                    total += os.path.getsize(path)
                except OSError:
                    pass
        return max(total, 1)  # Avoid division by zero

    # ------------------------------------------------------------------
    # Source discovery
    # ------------------------------------------------------------------

    def _discover_sources(self) -> dict:
        """
        Classify every candidate file as either a real Claude Code session
        JSONL or a legacy plain-text log.

        Real-session discovery is deliberately TOP-LEVEL ONLY (never
        recurses into subdirectories): a real Claude Code project directory
        holds per-session sidecar subdirectories (named after a session
        UUID) containing subagent transcripts and tool-results, which are
        not additional sessions and must never be silently pooled into
        whatever session's data the caller actually asked for. Legacy
        (mock-format) discovery keeps its original recursive walk, since
        that format's own convention (this library's bundled demo/tests)
        nests logs under a `sessions/` subdirectory.

        Returns:
            {
                "real": [Path, ...] sorted by mtime (oldest first),
                "legacy": {compaction_number: [Path, ...]} sorted by number,
            }
        """
        real_files: list[Path] = []
        legacy: dict[int, list[Path]] = {}

        if self._explicit_file is not None:
            real_files.append(self._explicit_file)
        else:
            for entry in sorted(self.agent_dir.iterdir()):
                if not entry.is_file() or not entry.name.endswith(".jsonl"):
                    continue
                if self._session_id is not None and entry.stem != self._session_id:
                    continue
                if looks_like_real_session(entry):
                    real_files.append(entry)

        for root, dirs, files in os.walk(self.agent_dir):
            if ".checkpoints" in Path(root).parts:
                continue
            for file in files:
                if not file.endswith((".log", ".txt", ".md", ".jsonl")):
                    continue
                path = Path(root) / file
                if path in real_files:
                    continue  # already claimed by the top-level real-session scan
                if file.endswith(".jsonl") and looks_like_real_session(path):
                    # A real-shaped session file sitting somewhere other than
                    # agent_dir's top level (e.g. a sidecar subagent
                    # transcript). Deliberately not added to `real_files` --
                    # see the docstring above -- and just as deliberately
                    # not misclassified as a legacy compaction either.
                    continue
                compaction_num = self._extract_compaction_number(str(path))
                if compaction_num is not None:
                    legacy.setdefault(compaction_num, []).append(path)

        real_files.sort(key=lambda p: p.stat().st_mtime)
        return {"real": real_files, "legacy": dict(sorted(legacy.items()))}

    @staticmethod
    def _parse_ts(ts: Optional[str]) -> Optional[datetime]:
        """Parse a real session's ISO-8601 timestamp (e.g. '...Z' suffix) into
        a datetime, matching CompactionChunk.start_time/end_time's declared
        type. Returns None on anything unparseable rather than raising --
        timing metadata is best-effort, never load-bearing for extraction."""
        if not ts:
            return None
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _extract_compaction_number(self, file_path: str) -> Optional[int]:
        """
        Extract compaction number from a LEGACY-format file path.

        Looks for patterns like 👽[0], compaction_0, session_0, etc. Real
        Claude Code session files are named by session UUID and will never
        match this -- that's expected, they're discovered via
        _discover_sources's real-session sniff instead, not by filename.
        """
        import re

        match = re.search(r"👽\[(\d+)\]", file_path)
        if match:
            return int(match.group(1))

        match = re.search(r"compaction[_-](\d+)", file_path, re.IGNORECASE)
        if match:
            return int(match.group(1))

        match = re.search(r"session[_-](\d+)", file_path, re.IGNORECASE)
        if match:
            return int(match.group(1))

        return None

    # ------------------------------------------------------------------
    # Legacy (plain-text) path -- unchanged behavior, kept for
    # backward compatibility with the bundled mock-data format.
    # ------------------------------------------------------------------

    def _read_compaction_content(self, file_paths: list[Path]) -> str:
        """Read and concatenate content from multiple compaction files."""
        content_parts = []

        for path in sorted(file_paths):
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content_parts.append(f.read())
            except OSError:
                pass

        return "\n".join(content_parts)

    def _extract_signal(self, raw_content: str) -> dict:
        """Extract high-signal sections from raw content (legacy text path)."""
        redacted_content = PIIRedactor.redact(raw_content)
        filtered = NoiseFilter.filter_log(redacted_content)
        signal = NoiseFilter.extract_key_content(filtered)
        signal["threads"] = extract_continuity_threads(redacted_content)
        return signal

    def _build_legacy_chunk(self, compaction_number: int, raw_content: str, signal: dict) -> CompactionChunk:
        """Build a CompactionChunk from legacy plain-text content and extracted signal."""
        chunk = CompactionChunk(
            compaction_number=compaction_number,
            compaction_label=f"👽[{compaction_number}]",
            raw_log_length=len(raw_content.encode("utf-8")),
            source_kind="legacy_text",
        )
        self._populate_signal(chunk, signal)

        if chunk.key_accomplishments:
            chunk.session_summary = f"Completed {len(chunk.key_accomplishments)} key tasks"
        elif chunk.blockers_encountered:
            chunk.session_summary = f"Encountered {len(chunk.blockers_encountered)} blockers"
        else:
            chunk.session_summary = f"Processed compaction {compaction_number}"

        return chunk

    # ------------------------------------------------------------------
    # Real JSONL path -- the actual fix.
    # ------------------------------------------------------------------

    def _iter_real_file_segments(self, path: Path):
        """
        Stream one real session JSONL file, yielding one compaction segment
        at a time: (events, total_bytes, boundary_event_or_None).

        A segment ends either at a compact_boundary event or at
        end-of-file (boundary_event is None in the latter case). The
        boundary event itself IS included as the last element of `events`
        for the segment it closes (it's chronologically the final event of
        that segment -- the compaction happened at that point) -- so
        `len(events)` and per-event tallies (entrypoint counts, etc.) count
        every real line in the file exactly once, matching the plain
        "count every JSON line" convention other tools use (verified
        against session-ops.js, a separate independently-built parser, on
        the same real file: segment-sum event/entrypoint counts now
        reconcile exactly, not just "off by the boundary count" -- a real
        second bug found during the Org Lead's own dogfooding pass, not
        merely a documented convention difference). `boundary_event` is
        still passed separately too, for boundary-specific metadata
        (trigger/tokens/etc) -- it is simply no longer *excluded* from the
        segment's own event accounting.

        Streams the file line-by-line -- a segment's events are buffered
        in memory, but the whole file never is, which matters for real
        transcripts that can run hundreds of MB.
        """
        buffer: list[dict] = []
        buffer_bytes = 0

        for event, line_bytes in iter_jsonl_events_sized(path):
            if is_compact_boundary(event):
                buffer.append(event)
                buffer_bytes += line_bytes
                yield buffer, buffer_bytes, event
                buffer = []
                buffer_bytes = 0
            else:
                buffer.append(event)
                buffer_bytes += line_bytes

        if buffer:
            yield buffer, buffer_bytes, None

    def _build_real_chunk(
        self,
        compaction_number: int,
        source_path: Path,
        events: list[dict],
        raw_bytes: int,
        boundary_event: Optional[dict],
    ) -> CompactionChunk:
        """Build a CompactionChunk from a real-session event segment."""
        text_parts: list[str] = []
        entrypoints: dict[str, int] = {}
        timestamps: list[str] = []

        for event in events:
            ep = event_entrypoint(event)
            if ep:
                entrypoints[ep] = entrypoints.get(ep, 0) + 1

            ts = event_timestamp(event)
            if ts:
                timestamps.append(ts)

            # Only real message text -- never tool_use input, tool_result
            # output, or thinking signatures. This is the actual fix for
            # the "979 false accomplishments" failure mode found while
            # dogfooding: those were raw JSON lines and base64 blobs being
            # substring-matched, not real prose.
            text_parts.extend(extract_text_blocks(event))

        raw_text = "\n".join(text_parts)
        signal = self._extract_signal(raw_text)

        chunk = CompactionChunk(
            compaction_number=compaction_number,
            compaction_label=f"👽[{compaction_number}]",
            raw_log_length=raw_bytes,
            source_kind="real_jsonl",
            source_files=[str(source_path)],
            event_count=len(events),
            entrypoints=entrypoints,
        )
        self._populate_signal(chunk, signal)

        if timestamps:
            chunk.start_time = self._parse_ts(timestamps[0])
            chunk.end_time = self._parse_ts(timestamps[-1])

        if boundary_event is not None:
            b = boundary_summary(boundary_event)
            chunk.boundary_trigger = b.get("trigger")
            chunk.tokens_pre = b.get("pre_tokens")
            chunk.tokens_post = b.get("post_tokens")
            if b.get("timestamp"):
                chunk.end_time = self._parse_ts(b["timestamp"])

        if chunk.key_accomplishments:
            chunk.session_summary = f"Completed {len(chunk.key_accomplishments)} key tasks"
        elif chunk.blockers_encountered:
            chunk.session_summary = f"Encountered {len(chunk.blockers_encountered)} blockers"
        else:
            chunk.session_summary = (
                f"Real session segment: {len(events)} events"
                + (f" ({', '.join(f'{k}={v}' for k, v in entrypoints.items())})" if entrypoints else "")
            )

        return chunk

    # ------------------------------------------------------------------
    # Shared
    # ------------------------------------------------------------------

    def _populate_signal(self, chunk: CompactionChunk, signal: dict) -> None:
        """Populate a CompactionChunk's signal fields from an extracted-signal dict.

        Shared between the legacy and real-JSONL paths so the two don't
        duplicate the decision/learning/work-product/blocker/thread
        assembly logic.
        """
        for decision_str in signal.get("decisions", []):
            chunk.decisions.append(Decision(
                context="Extracted from logs",
                decision=decision_str,
                rationale="See decision in context",
            ))

        chunk.learnings.extend(signal.get("learnings", []))
        chunk.key_accomplishments.extend(signal.get("accomplishments", []))
        chunk.blockers_encountered.extend(signal.get("blockers", []))

        for product_str in signal.get("work_products", []):
            chunk.work_products.append(WorkProduct(
                name="Artifact",
                description=product_str,
                artifact_type="work_product",
            ))

        for thread_str in signal.get("threads", []):
            chunk.continuity_threads.append(ContinuityThread(
                thread_id=f"thread_{chunk.compaction_number}_{len(chunk.continuity_threads)}",
                description=thread_str,
                status="open",
            ))

    def slurp(self, resume: bool = True) -> Generator[CompactionChunk, None, None]:
        """
        Slurp agent compactions and yield chunks.

        This is the main generator function.

        Args:
            resume: If True, resume from last checkpoint. If False, start fresh.

        Yields:
            CompactionChunk objects, one per compaction. Real session
            segments are numbered first (in file-mtime, then in-file
            order), followed by any legacy-format compactions, so
            checkpoint/resume works off a single monotonic counter
            regardless of which source kind a given number came from.
        """
        start_compaction = 0
        bytes_processed = 0

        if resume:
            checkpoint = self.checkpoint_manager.load_checkpoint()
            if checkpoint:
                start_compaction = checkpoint.last_compaction_processed + 1
                bytes_processed = checkpoint.bytes_processed
                print(f"Resuming from compaction {start_compaction} ({checkpoint.progress_percent:.1f}% done)")

        sources = self._sources
        if not sources["real"] and not sources["legacy"]:
            raise ValueError(f"No compaction files found in {self.agent_dir}")

        compaction_number = 0

        for path in sources["real"]:
            for events, raw_bytes, boundary_event in self._iter_real_file_segments(path):
                if not events and boundary_event is None:
                    continue
                if compaction_number < start_compaction:
                    compaction_number += 1
                    continue

                chunk = self._build_real_chunk(compaction_number, path, events, raw_bytes, boundary_event)
                chunk.checkpoint_path = str(self.checkpoint_manager.checkpoint_file)

                bytes_processed += chunk.raw_log_length
                yield chunk

                self.checkpoint_manager.save_checkpoint(
                    compaction_number,
                    bytes_processed,
                    self.total_bytes,
                    notes=f"Processed {chunk.compaction_label} (real_jsonl, {path.name})",
                )
                compaction_number += 1

        for _legacy_num, file_paths in sources["legacy"].items():
            if compaction_number < start_compaction:
                compaction_number += 1
                continue

            raw_content = self._read_compaction_content(file_paths)
            signal = self._extract_signal(raw_content)
            chunk = self._build_legacy_chunk(compaction_number, raw_content, signal)
            chunk.checkpoint_path = str(self.checkpoint_manager.checkpoint_file)

            bytes_processed += chunk.raw_log_length
            yield chunk

            self.checkpoint_manager.save_checkpoint(
                compaction_number,
                bytes_processed,
                self.total_bytes,
                notes=f"Processed {chunk.compaction_label} (legacy_text)",
            )
            compaction_number += 1

    def get_checkpoint_status(self) -> dict:
        """Get current checkpoint status."""
        return self.checkpoint_manager.get_status()

    def clear_checkpoints(self):
        """Clear all checkpoint data."""
        self.checkpoint_manager.clear_checkpoint()
        print("Checkpoints cleared")


def create_slurper(
    agent_dir: str,
    checkpoint_dir: Optional[str] = None,
    session_id: Optional[str] = None,
) -> AgentSlurper:
    """
    Factory function to create a slurper instance.

    Args:
        agent_dir: A specific real session `.jsonl` file, or a directory
            containing agent logs (see AgentSlurper's docstring for why
            those two aren't the same thing for real Claude Code project
            directories, which routinely hold several unrelated sessions).
        checkpoint_dir: Optional checkpoint directory
        session_id: Optional -- when agent_dir is a directory, restrict to
            the single top-level session file named `<session_id>.jsonl`.

    Returns:
        AgentSlurper instance
    """
    return AgentSlurper(agent_dir, checkpoint_dir, session_id=session_id)
