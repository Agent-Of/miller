# Agent Compaction Slurper (MILLER)

A Python tool for streaming and analyzing **real Claude Code session JSONL
transcripts** (and, for backward compatibility, a legacy plain-text mock
format used by earlier tests/demos). Extracts high-signal content, segments
by real `compact_boundary` events, filters harness noise, and supports
resumable processing via checkpoints.

**As of the JSONL-ingestion rewrite (Agent-Of/miller#3), this tool actually
parses JSON.** An earlier version claimed JSONL support but never called
`json.loads` on session content anywhere — it keyword/substring-matched raw
text, so real session files (named by session UUID, not by any
compaction-number convention) were invisible to it, and even worked around
by hand it misclassified tool-call JSON and base64 signature blobs as
"decisions"/"accomplishments". See the issue for the full failure analysis
and how the fix was verified against a real 400+MB, 100k+-event, 3-entrypoint
session transcript.

## Features

- **Real Claude Code JSONL parsing**: every line is `json.loads`'d; signal
  extraction only ever looks inside real `message.content` text blocks —
  never inside `tool_use` input, `tool_result` output, or `thinking`
  signatures, which routinely contain English words that look like signal
  but aren't.
- **Real compaction-boundary segmentation**: compactions are found via each
  file's own `type=="system"`/`subtype=="compact_boundary"` events (with
  `preTokens`/`postTokens`/`trigger`/`durationMs` surfaced), not by any
  filename convention. Real session files are discovered by content-sniffing,
  not renamed.
- **Streaming Generator Pattern**: processes one JSONL line at a time, so a
  400MB+ transcript never has to be loaded whole into memory.
- **Noise Filtering**: removes tool chatter, permission prompts, and harness
  metadata (both a keyword pass and the regex-pattern pass are actually
  applied — the regex pass used to be defined but never invoked).
- **PII Redaction**: redacts session IDs, local file paths (including real,
  `json.loads`-decoded single-backslash Windows paths), emails, and
  secret-shaped strings before extraction.
- **Checkpoint Recovery**: resume interrupted processing from the last
  checkpoint, using one monotonic compaction counter across all sources.
- **Legacy mock-format support kept**: the original plain-text
  `👽[N]`/`compaction_N`/`session_N` filename convention still works
  unchanged, for existing consumers of the bundled demo/tests.
- **Ships as an installable Claude Code subagent**: see
  [`.claude/agents/miller.md`](.claude/agents/miller.md).

## Installation

```bash
# No external dependencies required beyond Python 3.9+
# Simply copy the modules into your project
cp *.py /your/project/path/
```

### As a Claude Code subagent

Clone (or otherwise get) this repo into a project, and Claude Code will pick
up [`.claude/agents/miller.md`](.claude/agents/miller.md) automatically —
that's the documented, first-class mechanism a repo uses to ship an
installable subagent (checked into version control, no separate install
step). Invoke it directly (`Agent(subagent_type: "miller", ...)`) or let
Claude Code auto-delegate to it based on its `description`.

## Quick Start

Point it at a directory containing a real Claude Code session file (e.g.
`~/.claude/projects/<project>/<session-uuid>.jsonl`) — no renaming needed,
the file is discovered by content, not filename:

```python
from slurper import create_slurper

# Directory containing the real session .jsonl file(s)
slurper = create_slurper("/path/to/.claude/projects/<project-dir>")

# Stream through compactions (real compact_boundary-delimited segments)
for chunk in slurper.slurp(resume=True):
    print(f"{chunk.compaction_label}: {chunk.session_summary}")
    print(f"  source: {chunk.source_kind}, events: {chunk.event_count}, entrypoints: {chunk.entrypoints}")

    # Access high-signal content (extracted only from real message text,
    # never from tool-call JSON or thinking-block signatures)
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

    # Real-session provenance (populated when source_kind == "real_jsonl")
    source_kind: str                    # "real_jsonl" | "legacy_text"
    source_files: list[str]             # Path(s) this chunk came from
    event_count: int                    # Real events in this segment
    entrypoints: dict                   # {"cli": 12, "claude-vscode": 3, ...}
    boundary_trigger: Optional[str]     # "auto" | "manual" | None (segment ended at EOF)
    tokens_pre: Optional[int]           # compact_boundary preTokens, if this segment ended in one
    tokens_post: Optional[int]          # compact_boundary postTokens

    # Methods
    summary() -> str                    # Formatted text summary
```

`start_time`/`end_time` are genuinely populated for real sessions now (from
each event's own `timestamp` field, and the boundary event's timestamp when
a segment ends in one) — previously these were declared fields that were
never actually assigned anywhere.

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

Two source kinds are discovered, and can coexist in the same directory:

**Real Claude Code sessions** (the primary, intended use case): any
`.jsonl` file under `agent_dir` (searched recursively) that sniffs as a
real session transcript — i.e. its first few lines parse as JSON with a
recognized `type` (`user`/`assistant`/`system`/...). Filename is
irrelevant; a real session file is named by session UUID, e.g.:

```
agent_dir/
└── 6ff45d9a-8628-4005-8063-402692a24a94.jsonl   # discovered by content, not name
```

Compaction segments come from each file's own `compact_boundary` events,
in file order — a file with N boundaries yields N+1 segments (the last one
still open). Multiple real files in one directory are processed in
mtime order, each contributing its own segments to one continuous,
monotonically-numbered checkpoint sequence.

**Legacy plain-text mock format** (kept for backward compatibility with
the bundled demo/tests, not what a real session looks like): `.log`/`.txt`/
`.md`/`.jsonl` files whose *filename* contains `👽[N]`, `compaction_N`, or
`session_N`:

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

Real sources are always processed before legacy ones, but both share one
compaction-number sequence.

## Signal Extraction Strategy

**Real JSONL sources:** signal is extracted only from real message text —
`message.content` when it's a plain string, or `{"type":"text","text":...}`
blocks when it's a list. `tool_use` input, `tool_result` output, and
`thinking` blocks (which can contain large base64 signatures) are never
scanned for keywords; a tool call's JSON arguments routinely contain
ordinary English that looks like signal but isn't (this was the root
cause of Agent-Of/miller#3 — matching "completed" inside
`"status":"completed"` JSON produced hundreds of false positives on real
data). The resulting text then goes through the same multi-pass filtering
as the legacy path below.

**Legacy plain-text sources**, and the reconstructed real-message text
above, both go through:

1. **Noise Removal**: strips tool metadata, permission prompts, token usage
   info — both a regex-pattern pass (block-level noise like
   `<function_calls>...</function_calls>`) and a per-line keyword pass are
   applied (previously only the keyword pass actually ran; the regex
   patterns were defined but never invoked).
2. **PII Redaction**: session IDs, local file paths, emails, and
   secret-shaped strings are redacted before extraction. The file-path
   pattern matches 1-2 literal backslashes, so it works whether it's
   applied to text already decoded by `json.loads` (single backslash) or
   to still-JSON-escaped raw text (doubled backslash) — the original
   pattern only matched the doubled form and so never fired on real
   decoded session content.
3. **Section Detection**: Identifies "Decision:", "Learning:", "Accomplishment:" headers
4. **Pattern Matching**: Extracts TODO, FIXME, "next step" as continuity threads
5. **Content Preservation**: Keeps context and rationale for decisions

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

```bash
python test_slurper.py       # 11 tests: 8 legacy-format + 3 real-JSONL
python demo_with_mock_data.py  # legacy mock-data demo, unchanged behavior
```

The 3 real-JSONL tests cover: discovery + compact_boundary segmentation of
a UUID-named session file with no special naming, PII redaction on real
`json.loads`-decoded text, and — the actual regression test for the
original bug — that a tool-call's JSON `input` containing signal-shaped
substrings ("Accomplishment:", "completed") never leaks into extracted
signal, only real message text does.

These are still synthetic (small, hand-built) real-shaped JSONL, not a
committed real transcript — session files are a real person's/agent's
working history and aren't something to check into a public repo as test
fixtures. The rewrite was additionally verified live against a real
400+MB / ~118,000-event / 3-entrypoint / 48-boundary Claude Code session
transcript (not included here), with entrypoint/event counts cross-checked
against an independent, differently-implemented JSONL parser and found to
reconcile exactly.

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

- **Multi-file real sessions aren't lineage-aware yet.** If a directory
  holds several real session files that are actually forks/continuations of
  each other (`logicalParentUuid` bridging across files, per real Claude
  Code fork/resume behavior), this library currently processes each file's
  segments independently in mtime order — it does not yet follow
  `logicalParentUuid` across file boundaries to reconstruct a true
  cross-file lineage graph. `session_ops.js` (a separate, independently
  built Node tool referenced in Agent-Of/miller#3) does real parentUuid
  graph construction and is a useful reference if that's needed.
- Which of `preservedMessages.uuids` vs `.allUuids` is authoritative for
  "what survived a compaction" isn't documented anywhere found so far;
  both are surfaced rather than one being silently chosen.
- Legacy-format compaction numbers must still be explicit in file paths
  (unchanged, backward-compatible behavior).
- Checkpoint path must be writable.
- No built-in log transport (provide paths locally).

## License

Built for Victor's agent orchestration system (VIRGIL).
