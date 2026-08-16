"""
Data types for agent compaction slurper.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class WorkProduct:
    """Represents a work artifact or output from a compaction."""

    name: str
    description: str
    artifact_type: str  # e.g., 'file', 'commit', 'pull_request'
    path_or_ref: Optional[str] = None


@dataclass
class Decision:
    """Represents a decision point in the agent's work."""

    context: str
    decision: str
    rationale: str


@dataclass
class ContinuityThread:
    """Open thread for the next agent instance to pick up."""

    thread_id: str
    description: str
    status: str  # e.g., 'open', 'blocked', 'waiting'
    next_steps: list[str] = field(default_factory=list)


@dataclass
class CompactionChunk:
    """
    A chunk of high-signal content from one compaction cycle.

    Represents one agent's compaction (👽[N]) extracted from its logs and artifacts.
    """

    # Identity
    compaction_number: int  # 0-based: 0 = 👽[0], 1 = 👽[1], etc.
    compaction_label: str  # e.g., "👽[3]"

    # Timing
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    # High-signal content
    decisions: list[Decision] = field(default_factory=list)
    work_products: list[WorkProduct] = field(default_factory=list)
    learnings: list[str] = field(default_factory=list)
    continuity_threads: list[ContinuityThread] = field(default_factory=list)

    # Context
    session_summary: str = ""
    key_accomplishments: list[str] = field(default_factory=list)
    blockers_encountered: list[str] = field(default_factory=list)

    # Metadata
    raw_log_length: int = 0  # bytes of original log before filtering
    checkpoint_path: Optional[str] = None

    def summary(self) -> str:
        """Generate a text summary of this compaction chunk."""
        lines = [
            f"=== {self.compaction_label} ===",
            f"Time: {self.start_time} -> {self.end_time}",
            "",
        ]

        if self.session_summary:
            lines.append(f"Summary: {self.session_summary}")
            lines.append("")

        if self.key_accomplishments:
            lines.append("Accomplishments:")
            for acc in self.key_accomplishments:
                lines.append(f"  - {acc}")
            lines.append("")

        if self.decisions:
            lines.append("Decisions:")
            for d in self.decisions:
                lines.append(f"  - {d.decision}")
                lines.append(f"    Context: {d.context}")
            lines.append("")

        if self.work_products:
            lines.append("Work Products:")
            for p in self.work_products:
                lines.append(f"  - {p.name} ({p.artifact_type})")
                if p.description:
                    lines.append(f"    {p.description}")
            lines.append("")

        if self.learnings:
            lines.append("Key Learnings:")
            for l in self.learnings:
                lines.append(f"  - {l}")
            lines.append("")

        if self.blockers_encountered:
            lines.append("Blockers:")
            for b in self.blockers_encountered:
                lines.append(f"  - {b}")
            lines.append("")

        if self.continuity_threads:
            lines.append("Open Threads for Next Instance:")
            for t in self.continuity_threads:
                lines.append(f"  - {t.description} [{t.status}]")
                if t.next_steps:
                    for step in t.next_steps:
                        lines.append(f"    → {step}")
            lines.append("")

        return "\n".join(lines)
