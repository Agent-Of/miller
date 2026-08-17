"""
Working demo with mock data showing the slurper in action.

This script creates a realistic mock agent session structure,
then demonstrates the slurper iterating through compactions.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

from slurper import create_slurper

# On Windows, stdout defaults to the legacy console codepage (e.g. cp1252),
# which cannot encode the 👽 compaction labels this demo prints
# (UnicodeEncodeError, crashing mid-run). Reconfigure to UTF-8 when available
# (Python 3.7+); harmless no-op on platforms where stdout is already UTF-8.
# (Same fix as PR #4, carried into this branch too since it was branched
# from main before #4 merged.)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def create_mock_agent_logs(base_dir: Path):
    """Create a mock agent session directory with realistic logs."""

    # Create subdirectories
    sessions_dir = base_dir / "sessions"
    artifacts_dir = base_dir / "artifacts"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # Mock log content for 3 compactions
    compactions = [
        {
            "number": 0,
            "filename": "session_👽[0].log",
            "content": """=== Agent Session 👽[0] ===
Starting session for task: Build initial structure

Decision: Chose Python for implementation to ensure cross-platform compatibility
Rationale: Python has excellent support for file operations and testing

Created Work Products:
- types.py with CompactionChunk dataclass
- CheckpointManager for state persistence
- NoiseFilter for log cleaning

Learnings:
- Generator pattern is ideal for streaming large logs
- Checkpoint state needs to track position and bytes
- Test coverage requires mock data structure

Accomplishment: Completed 3 foundational modules

Next Steps:
- TODO: Implement core slurper generator
- TODO: Create demo with realistic data
- FIXME: Add comprehensive error handling

Session complete. 2534 bytes processed.
""",
        },
        {
            "number": 1,
            "filename": "session_👽[1].log",
            "content": """=== Agent Session 👽[1] ===
Continuing from previous compaction. Building generator logic.

Decision: Implement streaming with checkpoint recovery for fault tolerance
Context: Need to handle large agent logs that may span multiple compactions
Rationale: Allows resumable processing without reprocessing completed work

Created Work Products:
- slurper.py with AgentSlurper generator class
- Integrated CheckpointManager for resume capability
- Built file discovery logic for compaction detection

Key Learnings:
- File path patterns vary across agents
- Need flexible compaction number extraction
- Signal extraction requires multi-pass filtering

Accomplishments:
- Implemented core generator function
- Tested with mock data structure
- Verified checkpoint state persistence

Blockers Encountered:
- Initial regex patterns too strict, refined for flexibility

Next Steps:
- TODO: Create comprehensive example usage
- TODO: Add demo script for testing
- TODO: Document API for SOPHIA-class agents

Session complete. 3891 bytes processed.
""",
        },
        {
            "number": 2,
            "filename": "session_👽[2].log",
            "content": """=== Agent Session 👽[2] ===
Final compaction. Creating demo and documentation.

Decision: Build working demo with mock data for immediate testing
Rationale: Customer will test immediately, need runnable code

Created Work Products:
- demo_with_mock_data.py showing complete workflow
- example_usage.py with simple API demonstration
- README.md with comprehensive documentation

Key Learnings:
- Mock data structure mirrors real agent logs
- Checkpoint format simple but effective
- Generator pattern scales well for large datasets

Accomplishments:
- Created 5 source modules
- Built working demo
- Documented complete API
- Ready for SOPHIA-class testing

Blockers Encountered:
- None, implementation smooth

Quality Metrics:
- 95% code coverage in tests
- Clean, readable implementation
- Minimal dependencies
- Production-ready

Next Steps:
- WAITING: Customer feedback from testing
- TODO: Implement requested changes
- TODO: Scale to handle 100+ compactions

Session complete. 4156 bytes processed.
All compactions processed successfully!
""",
        },
    ]

    # Write mock log files
    for comp in compactions:
        log_file = sessions_dir / comp["filename"]
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(comp["content"])

    # Create mock artifact files
    artifacts = [
        ("types.py", "Dataclasses for CompactionChunk and related types"),
        ("slurper.py", "Core AgentSlurper with generator pattern"),
        ("filters.py", "NoiseFilter for extracting signal from logs"),
        ("checkpoints.py", "CheckpointManager for resumable processing"),
    ]

    for artifact_name, description in artifacts:
        artifact_file = artifacts_dir / artifact_name
        with open(artifact_file, "w") as f:
            f.write(f"# {artifact_name}\n# {description}\n")


def main():
    """Run the demo."""
    print("Agent Compaction Slurper Demo")
    print("=" * 70)

    # Create a temporary directory for mock logs
    with tempfile.TemporaryDirectory() as tmpdir:
        agent_dir = Path(tmpdir) / "mock_agent"
        agent_dir.mkdir()

        print(f"\n1. Creating mock agent session in {agent_dir}")
        create_mock_agent_logs(agent_dir)
        print("   Mock session created with 3 compactions")

        # Create the slurper
        print(f"\n2. Initializing slurper for agent")
        slurper = create_slurper(str(agent_dir))
        status = slurper.get_checkpoint_status()
        print(f"   Status: {status}")

        # Iterate through compactions
        print(f"\n3. Processing compactions:")
        print("-" * 70)

        chunk_count = 0
        total_bytes = 0

        for chunk in slurper.slurp(resume=True):
            chunk_count += 1
            total_bytes += chunk.raw_log_length

            print(f"\n{chunk.compaction_label} - {chunk.session_summary}")
            print(f"  Raw log size: {chunk.raw_log_length} bytes")

            if chunk.key_accomplishments:
                print(f"  Accomplishments: {len(chunk.key_accomplishments)}")
                for acc in chunk.key_accomplishments[:2]:
                    print(f"    - {acc[:60]}")

            if chunk.decisions:
                print(f"  Decisions: {len(chunk.decisions)}")
                for dec in chunk.decisions[:1]:
                    print(f"    - {dec.decision[:60]}")

            if chunk.learnings:
                print(f"  Learnings: {len(chunk.learnings)}")
                for learn in chunk.learnings[:1]:
                    print(f"    - {learn[:60]}")

            if chunk.continuity_threads:
                print(f"  Open threads: {len(chunk.continuity_threads)}")
                for thread in chunk.continuity_threads[:1]:
                    print(f"    - {thread.description[:60]}")

            print(f"  Checkpoint: {Path(chunk.checkpoint_path).name}")

        print("\n" + "-" * 70)
        print(f"\n4. Summary:")
        print(f"   Total compactions processed: {chunk_count}")
        print(f"   Total bytes slurped: {total_bytes}")
        print(f"   Average chunk size: {total_bytes // max(chunk_count, 1)} bytes")

        # Check final checkpoint status
        final_status = slurper.get_checkpoint_status()
        print(f"\n5. Final checkpoint status:")
        print(f"   {final_status}")

        # Test resumption
        print(f"\n6. Testing resumption from checkpoint:")
        slurper2 = create_slurper(str(agent_dir))
        status2 = slurper2.get_checkpoint_status()
        print(f"   New slurper loaded checkpoint: {status2['status']}")

        resumed_chunks = 0
        for chunk in slurper2.slurp(resume=True):
            resumed_chunks += 1

        print(f"   Resumed from saved checkpoint")
        print(f"   Would process {resumed_chunks} compactions from checkpoint")

        if resumed_chunks == 0:
            print(f"   (All compactions already processed!)")

        print(f"\n7. Clearing checkpoints for fresh start:")
        slurper.clear_checkpoints()
        fresh_status = slurper.get_checkpoint_status()
        print(f"   Status after clear: {fresh_status['status']}")

    print("\n" + "=" * 70)
    print("Demo complete! Slurper is production-ready.")
    print("\nKey features demonstrated:")
    print("  - Streaming generator pattern")
    print("  - Checkpoint persistence and resumption")
    print("  - Signal extraction from noisy logs")
    print("  - Scalable to multiple compactions")


if __name__ == "__main__":
    main()
