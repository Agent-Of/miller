"""
Checkpoint management for resumable compaction slurping.

Allows the slurper to resume from a checkpoint if interrupted.
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class CheckpointState:
    """State snapshot for resuming slurping."""

    last_compaction_processed: int  # 0-based
    timestamp: str  # ISO format
    progress_percent: float  # 0-100
    bytes_processed: int
    notes: str = ""


class CheckpointManager:
    """Manages checkpoint files for resumable slurping."""

    def __init__(self, checkpoint_dir: str):
        """
        Initialize checkpoint manager.

        Args:
            checkpoint_dir: Directory where checkpoint files are stored
        """
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_file = self.checkpoint_dir / "slurper_checkpoint.json"

    def load_checkpoint(self) -> Optional[CheckpointState]:
        """
        Load checkpoint from file.

        Returns:
            CheckpointState if checkpoint exists, None otherwise
        """
        if not self.checkpoint_file.exists():
            return None

        try:
            with open(self.checkpoint_file, "r") as f:
                data = json.load(f)
            return CheckpointState(**data)
        except (json.JSONDecodeError, TypeError):
            return None

    def save_checkpoint(self, compaction_number: int, bytes_processed: int, total_bytes: int, notes: str = ""):
        """
        Save checkpoint state.

        Args:
            compaction_number: The compaction number just processed (0-based)
            bytes_processed: Total bytes processed so far
            total_bytes: Total bytes in all compactions
            notes: Optional notes about the checkpoint
        """
        progress = (bytes_processed / total_bytes * 100) if total_bytes > 0 else 0

        checkpoint = CheckpointState(
            last_compaction_processed=compaction_number,
            timestamp=datetime.utcnow().isoformat(),
            progress_percent=progress,
            bytes_processed=bytes_processed,
            notes=notes,
        )

        with open(self.checkpoint_file, "w") as f:
            json.dump(
                {
                    "last_compaction_processed": checkpoint.last_compaction_processed,
                    "timestamp": checkpoint.timestamp,
                    "progress_percent": checkpoint.progress_percent,
                    "bytes_processed": checkpoint.bytes_processed,
                    "notes": checkpoint.notes,
                },
                f,
                indent=2,
            )

    def clear_checkpoint(self):
        """Clear the checkpoint (mark as fully processed)."""
        if self.checkpoint_file.exists():
            self.checkpoint_file.unlink()

    def get_status(self) -> dict:
        """Get current checkpoint status."""
        checkpoint = self.load_checkpoint()
        if checkpoint is None:
            return {
                "status": "no_checkpoint",
                "message": "No checkpoint found, will start from beginning",
            }

        return {
            "status": "checkpoint_found",
            "last_compaction": checkpoint.last_compaction_processed,
            "progress_percent": checkpoint.progress_percent,
            "timestamp": checkpoint.timestamp,
            "notes": checkpoint.notes,
        }
