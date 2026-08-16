# Agent Compaction Slurper

A production-ready Python tool for streaming and analyzing agent compaction histories. Extracts high-signal content from agent session logs, filters harness noise, and supports resumable processing via checkpoints.

## Features

- **Streaming Generator Pattern**: Process large agent logs without loading everything into memory
- **Signal Extraction**: Automatically identifies decisions, learnings, work products, and continuity threads
- **Noise Filtering**: Removes tool chatter, permission prompts, and harness metadata
- **Checkpoint Recovery**: Resume interrupted processing from the last checkpoint
- **Compaction Support**: Handles multiple agent compactions (👽[0..N])
- **Resumable Processing**: Full state management for fault-tolerant slurping

## Installation

```bash
# No external dependencies required beyond Python 3.9+
# Simply copy the modules into your project
cp *.py /your/project/path/
```

## Quick Start

```python
from slurper import create_slurper

# Create a slurper for an agent's logs
slurper = create_slurper("/path/to/agent/logs")

# Stream through compactions
for chunk in slurper.slurp(resume=True):
    print(f"{chunk.compaction_label}: {chunk.session_summary}")
    
    # Access high-signal content
    for decision in chunk.decisions:
        print(f"  Decision: {decision.decision}")
    
    for learning in chunk.learnings:
        print(f"  Learning: {learning}")
    
    # Handle continuity threads
    for thread in chunk.continuity_threads:
        print(f"  Open: {thread.description}")
```

## API Reference

### AgentSlurper

Main class for streaming agent compactions.

```python
slurper = AgentSlurper(
    agent_dir: str,                    # Root directory of agent logs
    checkpoint_dir: Optional[str] = None  # Where to store checkpoints
)
```

**Methods:**

- `slurp(resume: bool = True) -> Generator[CompactionChunk]`
  - Main generator function
  - Yields one `CompactionChunk` per compaction
  - If `resume=True`, starts from last checkpoint
  - If `resume=False`, processes from beginning

- `get_checkpoint_status() -> dict`
  - Returns current checkpoint status
  - Shows progress and timestamp

- `clear_checkpoints() -> None`
  - Clears all checkpoint data for fresh start

### CompactionChunk

Represents one compaction's high-signal content.

```python
@dataclass
class CompactionChunk:
    compaction_number: int              # 0-based (👽[0] = 0)
    compaction_label: str               # "👽[N]"
    
    # Timing
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    
    # High-signal content
    decisions: list[Decision]           # Key decisions made
    work_products: list[WorkProduct]    # Artifacts created
    learnings: list[str]                # Key insights
    continuity_threads: list[ContinuityThread]  # Open threads
    
    # Context
    session_summary: str                # Brief summary
    key_accomplishments: list[str]      # What was completed
    blockers_encountered: list[str]     # What blocked progress
    
    # Metadata
    raw_log_length: int                 # Bytes before filtering
    checkpoint_path: Optional[str]      # Checkpoint file location
    
    # Methods
    summary() -> str                    # Formatted text summary
```

### Decision

Represents a decision point.

```python
@dataclass
class Decision:
    context: str          # Situation context
    decision: str         # What was decided
    rationale: str        # Why it was decided
```

### WorkProduct

Represents a deliverable or artifact.

```python
@dataclass
class WorkProduct:
    name: str             # Name of the product
    description: str      # What it does
    artifact_type: str    # e.g., 'file', 'commit', 'pull_request'
    path_or_ref: Optional[str]  # Path or reference
```

### ContinuityThread

Represents open work for the next instance.

```python
@dataclass
class ContinuityThread:
    thread_id: str        # Unique ID
    description: str      # What needs to happen
    status: str           # 'open', 'blocked', 'waiting'
    next_steps: list[str] # Recommended actions
```

## Checkpoint Format

Checkpoints are stored as JSON in `.checkpoints/slurper_checkpoint.json`:

```json
{
  "last_compaction_processed": 2,
  "timestamp": "2025-08-14T12:34:56.789123",
  "progress_percent": 66.7,
  "bytes_processed": 10544,
  "notes": "Processed 👽[2]"
}
```

## Directory Structure

The slurper looks for agent logs in this structure:

```
agent_dir/
├── sessions/
│   ├── session_👽[0].log
│   ├── session_👽[1].log
│   ├── compaction_0.txt
│   └── ...
├── artifacts/
│   ├── types.py
│   ├── slurper.py
│   └── ...
└── .checkpoints/
    └── slurper_checkpoint.json  (auto-created)
```

The slurper automatically:
1. Discovers files by compaction number (looks for 👽[N], compaction_N, session_N patterns)
2. Groups files by compaction
3. Processes in order (0, 1, 2, ...)

## Signal Extraction Strategy

The slurper uses multi-pass filtering:

1. **Noise Removal**: Strips tool metadata, permission prompts, token usage info
2. **Section Detection**: Identifies "Decision:", "Learning:", "Accomplishment:" headers
3. **Pattern Matching**: Extracts TODO, FIXME, "next step" as continuity threads
4. **Content Preservation**: Keeps context and rationale for decisions

## Error Handling

```python
from pathlib import Path
from slurper import create_slurper

try:
    slurper = create_slurper("/path/to/agent/logs")
    for chunk in slurper.slurp():
        print(chunk.summary())
except ValueError as e:
    print(f"Invalid agent directory: {e}")
except OSError as e:
    print(f"File I/O error: {e}")
```

## Performance Characteristics

- **Memory**: O(1) per compaction (streaming generator)
- **Disk I/O**: Sequential reads, minimal seeking
- **Time**: Linear in total log size
- **Resumption**: O(1) checkpoint load, no log rescanning

## Testing

Run the demo with mock data:

```bash
python demo_with_mock_data.py
```

This creates a realistic 3-compaction mock agent session and demonstrates:
- Slurper initialization
- Generator streaming
- Checkpoint creation and resumption
- Status reporting

## For SOPHIA-Class Agents

This tool is designed for use by SOPHIA-class agents testing agent architectures. Key capabilities:

- **Introspection**: Understand what prior instances accomplished
- **State Recovery**: Continue work from checkpoints
- **Decision Tracking**: Audit why choices were made
- **Progress Monitoring**: Track completion percentage

Use with:
```python
from slurper import create_slurper

# Your SOPHIA implementation
slurper = create_slurper(f"/path/to/{agent_id}/logs")
for chunk in slurper.slurp(resume=True):
    # Analyze what prior instances learned
    prior_knowledge = "\n".join(chunk.learnings)
    # Continue work based on open threads
    for thread in chunk.continuity_threads:
        # Resume from thread.description
        pass
```

## Limitations & Future Work

- Compaction numbers must be explicit in file paths
- Custom parsing may be needed for unusual log formats
- Checkpoint path must be writable
- No built-in log transport (provide paths locally)

## License

Built for Victor's agent orchestration system (VIRGIL).
