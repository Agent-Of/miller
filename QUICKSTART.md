# Quick Start Guide

Get the agent slurper running in 60 seconds.

> **Updated during the JSONL-ingestion rewrite (Agent-Of/miller#3):** this
> tool now actually parses real Claude Code session JSONL — point it at a
> directory containing a real `<session-uuid>.jsonl` file, no renaming
> needed. See `README.md`'s Quick Start for the real-session example; the
> mock-data walkthrough below still works unchanged and is still a fast way
> to sanity-check your install, but it is not what real usage looks like.
> `test_slurper.py` now has 11 tests (8 legacy + 3 real-JSONL), not 8.

## 1. Verify Installation

```bash
cd agent-slurper
ls -la *.py  # Should see 9 Python files (slurper, filters, models, checkpoints, jsonl_events, __init__, + examples/tests)
```

## 2. Run the Demo

```bash
python demo_with_mock_data.py
```

Should print 3 compactions being processed and checkpoint status. Takes ~2 seconds.

## 3. Run Tests

```bash
python test_slurper.py
```

Should show: `Results: 11 passed, 0 failed`

## 4. Use in Your Code

```python
from agent_slurper import create_slurper

# Point to your agent's log directory
slurper = create_slurper("/path/to/agent/logs")

# Stream through compactions
for chunk in slurper.slurp(resume=True):
    print(f"{chunk.compaction_label}: {chunk.session_summary}")
    
    # Extract what matters
    decisions = [d.decision for d in chunk.decisions]
    learnings = chunk.learnings
    threads = [t.description for t in chunk.continuity_threads]
    
    print(f"  Decisions: {len(decisions)}")
    print(f"  Learnings: {len(learnings)}")
    print(f"  Open threads: {len(threads)}")
```

## 5. Resume from Checkpoint

The slurper automatically saves progress after each compaction:

```python
slurper = create_slurper("/path/to/agent/logs")

# This resumes from last checkpoint by default
for chunk in slurper.slurp():
    process(chunk)
    
# Get status anytime
status = slurper.get_checkpoint_status()
print(f"Progress: {status['progress_percent']}%")
```

## 6. Start Fresh

```python
slurper = create_slurper("/path/to/agent/logs")
slurper.clear_checkpoints()

# Now slurp will start from beginning
for chunk in slurper.slurp():
    process(chunk)
```

---

## API Cheat Sheet

### Create Slurper
```python
slurper = create_slurper(agent_dir, checkpoint_dir=None)
```

### Stream Compactions
```python
for chunk in slurper.slurp(resume=True):
    chunk.compaction_number   # 0-based int
    chunk.compaction_label    # "👽[0]"
    chunk.session_summary     # str
    chunk.decisions           # list[Decision]
    chunk.learnings           # list[str]
    chunk.work_products       # list[WorkProduct]
    chunk.continuity_threads  # list[ContinuityThread]
    chunk.key_accomplishments # list[str]
    chunk.blockers_encountered # list[str]
    chunk.summary()           # formatted text
```

### Check Progress
```python
status = slurper.get_checkpoint_status()
# Returns: {'status': 'checkpoint_found' or 'no_checkpoint', 
#           'last_compaction': N, 'progress_percent': X.X, ...}
```

### Reset Progress
```python
slurper.clear_checkpoints()
```

---

## Example: Extract All Learnings

```python
from agent_slurper import create_slurper

slurper = create_slurper("/path/to/agent/logs")
all_learnings = []

for chunk in slurper.slurp():
    all_learnings.extend(chunk.learnings)

print(f"\n--- {len(all_learnings)} Learnings ---")
for learning in all_learnings:
    print(f"  • {learning}")
```

## Example: Resume Open Work

```python
from agent_slurper import create_slurper

slurper = create_slurper("/path/to/agent/logs")

open_work = []
for chunk in slurper.slurp(resume=True):
    for thread in chunk.continuity_threads:
        open_work.append({
            'compaction': chunk.compaction_label,
            'description': thread.description,
            'status': thread.status,
            'next_steps': thread.next_steps
        })

print(f"\nOpen Work from Prior Instances:")
for item in open_work:
    print(f"  [{item['compaction']}] {item['description']}")
    for step in item['next_steps']:
        print(f"    → {step}")
```

---

## Directory Structure

Your agent logs should be organized like:

```
agent_logs/
├── sessions/
│   ├── session_👽[0].log
│   ├── session_👽[1].log
│   └── session_👽[2].log
├── artifacts/
│   ├── types.py
│   └── slurper.py
└── .checkpoints/  (auto-created)
    └── slurper_checkpoint.json
```

The slurper looks for compaction numbers in filenames:
- `👽[0]` notation (preferred)
- `compaction_0` notation
- `session_0` notation

---

## Troubleshooting

**No compaction files found?**
- Check that files have compaction numbers in names
- Try: `session_0.log` or `compaction_0.log`

**UnicodeEncodeError?**
- Use UTF-8 encoding when writing files
- `with open(file, 'w', encoding='utf-8') as f:`

**Checkpoint not loading?**
- Check that `.checkpoints/` directory is writable
- Use `slurper.clear_checkpoints()` and retry

**Want all signal at once?**
```python
# Slurp all compactions into list
all_chunks = list(slurper.slurp())
```

---

## For SOPHIA-Class Agents

Use this to understand what prior instances learned:

```python
from agent_slurper import create_slurper

def integrate_prior_knowledge(agent_id):
    slurper = create_slurper(f"/path/to/{agent_id}/logs")
    
    # Gather prior knowledge
    prior_decisions = []
    prior_learnings = []
    open_threads = []
    
    for chunk in slurper.slurp(resume=True):
        prior_decisions.extend([d.decision for d in chunk.decisions])
        prior_learnings.extend(chunk.learnings)
        open_threads.extend(chunk.continuity_threads)
    
    context = {
        'prior_decisions': prior_decisions,
        'prior_learnings': prior_learnings,
        'resume_from': open_threads,
        'progress': slurper.get_checkpoint_status()
    }
    
    return context

# Then use context to guide your work
context = integrate_prior_knowledge("my_agent")
```

---

## Next: Full Documentation

See `README.md` for complete API reference and design details.
