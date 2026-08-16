"""
Core agent compaction slurper.

Reads agent session logs and artifacts, extracts high-signal content,
and yields CompactionChunk objects one compaction at a time.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional

from checkpoints import CheckpointManager
from filters import NoiseFilter, PIIRedactor, extract_continuity_threads
from models import CompactionChunk, ContinuityThread, Decision, WorkProduct


class AgentSlurper:
    """Streaming agent compaction slurper."""

    def __init__(self, agent_dir: str, checkpoint_dir: Optional[str] = None):
        """
        Initialize the slurper.

        Args:
            agent_dir: Root directory containing agent's session logs and artifacts
            checkpoint_dir: Directory for checkpoint files (defaults to agent_dir/.checkpoints)
        """
        self.agent_dir = Path(agent_dir)
        if not self.agent_dir.exists():
            raise ValueError(f"Agent directory not found: {agent_dir}")

        if checkpoint_dir is None:
            checkpoint_dir = str(self.agent_dir / ".checkpoints")

        self.checkpoint_manager = CheckpointManager(checkpoint_dir)
        self.total_bytes = self._calculate_total_bytes()

    def _calculate_total_bytes(self) -> int:
        """Calculate total bytes in all log files."""
        total = 0
        for root, dirs, files in os.walk(self.agent_dir):
            for file in files:
                if file.endswith((".log", ".txt", ".md", ".jsonl")):
                    try:
                        total += os.path.getsize(os.path.join(root, file))
                    except OSError:
                        pass
        return max(total, 1)  # Avoid division by zero

    def _find_compaction_files(self) -> dict[int, list[Path]]:
        """
        Find and organize compaction files by compaction number.

        Returns:
            Dict mapping compaction_number -> list of file paths
        """
        compactions = {}

        # Look for files that indicate compaction number
        for root, dirs, files in os.walk(self.agent_dir):
            for file in files:
                if file.endswith((".log", ".txt", ".md", ".jsonl")):
                    path = Path(root) / file
                    compaction_num = self._extract_compaction_number(str(path))
                    if compaction_num is not None:
                        if compaction_num not in compactions:
                            compactions[compaction_num] = []
                        compactions[compaction_num].append(path)

        return dict(sorted(compactions.items()))

    def _extract_compaction_number(self, file_path: str) -> Optional[int]:
        """
        Extract compaction number from file path.

        Looks for patterns like 👽[0], compaction_0, session_0, etc.
        """
        import re

        # Pattern 1: 👽[N] notation
        match = re.search(r"👽\[(\d+)\]", file_path)
        if match:
            return int(match.group(1))

        # Pattern 2: compaction_N notation
        match = re.search(r"compaction[_-](\d+)", file_path, re.IGNORECASE)
        if match:
            return int(match.group(1))

        # Pattern 3: session_N notation
        match = re.search(r"session[_-](\d+)", file_path, re.IGNORECASE)
        if match:
            return int(match.group(1))

        return None

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
        """Extract high-signal sections from raw content."""
        # Redact PII before processing
        redacted_content = PIIRedactor.redact(raw_content)

        # Filter noise
        filtered = NoiseFilter.filter_log(redacted_content)

        # Extract key content
        signal = NoiseFilter.extract_key_content(filtered)

        # Extract continuity threads
        signal["threads"] = extract_continuity_threads(redacted_content)

        return signal

    def _build_chunk(self, compaction_number: int, raw_content: str, signal: dict) -> CompactionChunk:
        """Build a CompactionChunk from raw content and extracted signal."""
        # Create the chunk
        chunk = CompactionChunk(
            compaction_number=compaction_number,
            compaction_label=f"👽[{compaction_number}]",
            raw_log_length=len(raw_content.encode("utf-8")),
        )

        # Add decisions
        for decision_str in signal.get("decisions", []):
            chunk.decisions.append(Decision(
                context="Extracted from logs",
                decision=decision_str,
                rationale="See decision in context",
            ))

        # Add learnings
        chunk.learnings.extend(signal.get("learnings", []))

        # Add accomplishments
        chunk.key_accomplishments.extend(signal.get("accomplishments", []))

        # Add blockers
        chunk.blockers_encountered.extend(signal.get("blockers", []))

        # Add work products
        for product_str in signal.get("work_products", []):
            chunk.work_products.append(WorkProduct(
                name="Artifact",
                description=product_str,
                artifact_type="work_product",
            ))

        # Add continuity threads
        for thread_str in signal.get("threads", []):
            chunk.continuity_threads.append(ContinuityThread(
                thread_id=f"thread_{compaction_number}_{len(chunk.continuity_threads)}",
                description=thread_str,
                status="open",
            ))

        # Set summary
        if chunk.key_accomplishments:
            chunk.session_summary = f"Completed {len(chunk.key_accomplishments)} key tasks"
        elif chunk.blockers_encountered:
            chunk.session_summary = f"Encountered {len(chunk.blockers_encountered)} blockers"
        else:
            chunk.session_summary = f"Processed compaction {compaction_number}"

        return chunk

    def slurp(self, resume: bool = True) -> Generator[CompactionChunk, None, None]:
        """
        Slurp agent compactions and yield chunks.

        This is the main generator function.

        Args:
            resume: If True, resume from last checkpoint. If False, start fresh.

        Yields:
            CompactionChunk objects, one per compaction
        """
        # Check for checkpoint
        start_compaction = 0
        bytes_processed = 0

        if resume:
            checkpoint = self.checkpoint_manager.load_checkpoint()
            if checkpoint:
                start_compaction = checkpoint.last_compaction_processed + 1
                bytes_processed = checkpoint.bytes_processed
                print(f"Resuming from compaction {start_compaction} ({checkpoint.progress_percent:.1f}% done)")

        # Find all compaction files
        compactions = self._find_compaction_files()

        if not compactions:
            raise ValueError(f"No compaction files found in {self.agent_dir}")

        # Process each compaction
        for compaction_number in sorted(compactions.keys()):
            if compaction_number < start_compaction:
                continue

            # Read compaction content
            file_paths = compactions[compaction_number]
            raw_content = self._read_compaction_content(file_paths)

            # Extract signal
            signal = self._extract_signal(raw_content)

            # Build chunk
            chunk = self._build_chunk(compaction_number, raw_content, signal)
            chunk.checkpoint_path = str(self.checkpoint_manager.checkpoint_file)

            # Update progress
            bytes_processed += chunk.raw_log_length

            # Yield the chunk
            yield chunk

            # Save checkpoint
            self.checkpoint_manager.save_checkpoint(
                compaction_number,
                bytes_processed,
                self.total_bytes,
                notes=f"Processed {chunk.compaction_label}",
            )

    def get_checkpoint_status(self) -> dict:
        """Get current checkpoint status."""
        return self.checkpoint_manager.get_status()

    def clear_checkpoints(self):
        """Clear all checkpoint data."""
        self.checkpoint_manager.clear_checkpoint()
        print("Checkpoints cleared")


def create_slurper(agent_dir: str, checkpoint_dir: Optional[str] = None) -> AgentSlurper:
    """
    Factory function to create a slurper instance.

    Args:
        agent_dir: Root directory containing agent logs and artifacts
        checkpoint_dir: Optional checkpoint directory

    Returns:
        AgentSlurper instance
    """
    return AgentSlurper(agent_dir, checkpoint_dir)
