"""
Test suite for agent compaction slurper.

SOPHIA-class agents can use this to verify the implementation.
"""

import json
import sys
import tempfile
from pathlib import Path
from slurper import create_slurper, AgentSlurper
from models import CompactionChunk, Decision, WorkProduct
from filters import NoiseFilter, PIIRedactor

# On Windows, stdout defaults to the legacy console codepage (e.g. cp1252),
# which cannot encode the emoji/checkmark characters this suite prints
# (UnicodeEncodeError, crashing before any test result is shown). Reconfigure
# to UTF-8 when available (Python 3.7+); harmless no-op on platforms where
# stdout is already UTF-8. (Same fix as PR #4, carried into this branch too
# since it was branched from main before #4 merged.)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def test_basic_slurping():
    """Test basic slurping functionality."""
    print("Test 1: Basic slurping...")

    with tempfile.TemporaryDirectory() as tmpdir:
        agent_dir = Path(tmpdir) / "test_agent"
        agent_dir.mkdir()

        # Create a mock session
        sessions_dir = agent_dir / "sessions"
        sessions_dir.mkdir()

        log_content = """=== Agent Session 👽[0] ===
Decision: Choose Python implementation
Created: types.py, slurper.py
Learned: Generator pattern works well
Accomplished: Basic structure built
TODO: Add more features
"""
        log_file = sessions_dir / "session_👽[0].log"
        log_file.write_text(log_content, encoding="utf-8")

        # Test slurping
        slurper = create_slurper(str(agent_dir))
        chunks = list(slurper.slurp(resume=False))

        assert len(chunks) == 1, f"Expected 1 chunk, got {len(chunks)}"
        chunk = chunks[0]
        assert chunk.compaction_number == 0
        assert chunk.compaction_label == "👽[0]"
        assert len(chunk.decisions) > 0
        assert len(chunk.learnings) > 0
        assert len(chunk.continuity_threads) > 0

    print("  ✓ Basic slurping passed")


def test_multiple_compactions():
    """Test handling multiple compactions."""
    print("Test 2: Multiple compactions...")

    with tempfile.TemporaryDirectory() as tmpdir:
        agent_dir = Path(tmpdir) / "test_agent"
        sessions_dir = (agent_dir / "sessions")
        sessions_dir.mkdir(parents=True)

        # Create 3 compactions
        for i in range(3):
            content = f"""=== Compaction 👽[{i}] ===
Accomplished: Task {i} completed
Learning: Progress checkpoint
TODO: Continue to next phase
"""
            (sessions_dir / f"compaction_{i}.log").write_text(content, encoding="utf-8")

        slurper = create_slurper(str(agent_dir))
        chunks = list(slurper.slurp(resume=False))

        assert len(chunks) == 3, f"Expected 3 chunks, got {len(chunks)}"
        for i, chunk in enumerate(chunks):
            assert chunk.compaction_number == i
            assert chunk.compaction_label == f"👽[{i}]"

    print("  ✓ Multiple compactions passed")


def test_checkpoint_persistence():
    """Test checkpoint save and load."""
    print("Test 3: Checkpoint persistence...")

    with tempfile.TemporaryDirectory() as tmpdir:
        agent_dir = Path(tmpdir) / "test_agent"
        sessions_dir = (agent_dir / "sessions")
        sessions_dir.mkdir(parents=True)

        # Create 2 compactions
        for i in range(2):
            content = f"Compaction {i}\nAccomplishment: Task {i}"
            (sessions_dir / f"session_{i}.log").write_text(content, encoding="utf-8")

        # Process all compactions to trigger checkpoint saves
        slurper = create_slurper(str(agent_dir))
        chunks = list(slurper.slurp(resume=False))

        # At least one compaction should have been processed
        assert len(chunks) >= 1, f"Expected at least 1 chunk, got {len(chunks)}"

        # Check checkpoint was created
        checkpoint_file = agent_dir / ".checkpoints" / "slurper_checkpoint.json"
        assert checkpoint_file.exists(), f"Checkpoint file not created at {checkpoint_file}"

        # Verify checkpoint content
        with open(checkpoint_file, encoding="utf-8") as f:
            checkpoint = json.load(f)
        assert checkpoint["last_compaction_processed"] >= 0

        # Create new slurper and check it resumes
        slurper2 = create_slurper(str(agent_dir))
        status = slurper2.get_checkpoint_status()
        assert status["status"] == "checkpoint_found", f"Expected checkpoint_found, got {status['status']}"
        # The last compaction might be 1, not 0 (we have 2 compactions with session_0.log and session_1.log)
        assert status["last_compaction"] >= 0

    print("  ✓ Checkpoint persistence passed")


def test_noise_filtering():
    """Test that noise is filtered from output."""
    print("Test 4: Noise filtering...")

    with tempfile.TemporaryDirectory() as tmpdir:
        agent_dir = Path(tmpdir) / "test_agent"
        sessions_dir = (agent_dir / "sessions")
        sessions_dir.mkdir(parents=True)

        # Create log with lots of noise
        log_content = """Signal content here
<function_calls>
  <invoke>...</invoke>
</function_calls>
<function_results>
Some noise
</function_results>
More signal
<total_tokens>12345</total_tokens>
Decision: This is important
"""
        (sessions_dir / "session_👽[0].log").write_text(log_content, encoding="utf-8")

        slurper = create_slurper(str(agent_dir))
        chunks = list(slurper.slurp(resume=False))

        # The raw log should be smaller than original
        # (because we're filtering, filtered content should still be extracted)
        assert len(chunks) == 1
        chunk = chunks[0]
        # Verify decisions were found despite noise
        assert len(chunk.decisions) > 0 or "Decision" in chunk.session_summary

    print("  ✓ Noise filtering passed")


def test_generator_pattern():
    """Test that slurper uses generator pattern (memory efficient)."""
    print("Test 5: Generator pattern...")

    with tempfile.TemporaryDirectory() as tmpdir:
        agent_dir = Path(tmpdir) / "test_agent"
        sessions_dir = (agent_dir / "sessions")
        sessions_dir.mkdir(parents=True)

        # Create compaction
        (sessions_dir / "session_👽[0].log").write_text("Test content", encoding="utf-8")

        slurper = create_slurper(str(agent_dir))
        gen = slurper.slurp(resume=False)

        # Verify it's actually a generator
        import types
        assert isinstance(gen, types.GeneratorType), "slurp() should return a generator"

        # Consume one item
        chunk = next(gen)
        assert isinstance(chunk, CompactionChunk)

    print("  ✓ Generator pattern passed")


def test_chunk_summary():
    """Test CompactionChunk.summary() method."""
    print("Test 6: Chunk summary method...")

    chunk = CompactionChunk(
        compaction_number=0,
        compaction_label="👽[0]",
        session_summary="Test session",
        key_accomplishments=["Task 1", "Task 2"],
        learnings=["Learning 1"],
    )

    summary = chunk.summary()
    assert "👽[0]" in summary
    assert "Test session" in summary
    assert "Task 1" in summary
    assert "Learning 1" in summary

    print("  ✓ Chunk summary passed")


def test_empty_directory():
    """Test handling of empty/missing directories."""
    print("Test 7: Empty directory handling...")

    with tempfile.TemporaryDirectory() as tmpdir:
        agent_dir = Path(tmpdir) / "empty_agent"
        agent_dir.mkdir()

        slurper = create_slurper(str(agent_dir))

        try:
            list(slurper.slurp(resume=False))
            assert False, "Should raise ValueError for empty directory"
        except ValueError as e:
            assert "No compaction files found" in str(e)

    print("  ✓ Empty directory handling passed")


def test_clear_checkpoints():
    """Test clearing checkpoints."""
    print("Test 8: Clear checkpoints...")

    with tempfile.TemporaryDirectory() as tmpdir:
        agent_dir = Path(tmpdir) / "test_agent"
        sessions_dir = (agent_dir / "sessions")
        sessions_dir.mkdir(parents=True)

        # Create a compaction
        (sessions_dir / "session_👽[0].log").write_text("Test", encoding="utf-8")

        # Process it (creates checkpoint)
        slurper = create_slurper(str(agent_dir))
        list(slurper.slurp(resume=False))

        # Verify checkpoint exists
        checkpoint_file = agent_dir / ".checkpoints" / "slurper_checkpoint.json"
        assert checkpoint_file.exists()

        # Clear it
        slurper.clear_checkpoints()
        assert not checkpoint_file.exists()

        # Verify status shows no checkpoint
        status = slurper.get_checkpoint_status()
        assert status["status"] == "no_checkpoint"

    print("  ✓ Clear checkpoints passed")


def _write_jsonl(path: Path, events: list[dict]):
    with open(path, "w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")


def test_real_jsonl_discovered_and_parsed():
    """Real fix for Agent-Of/miller#3: a real Claude-Code-shaped JSONL file,
    named by session UUID (no 👽[N]/compaction_N/session_N in the filename),
    must be discovered and correctly segmented by its own compact_boundary
    events -- not by filename convention."""
    print("Test 9: Real JSONL discovery + compaction-boundary segmentation...")

    with tempfile.TemporaryDirectory() as tmpdir:
        agent_dir = Path(tmpdir) / "test_agent"
        agent_dir.mkdir()
        # Deliberately UUID-named, matching a real Claude Code session file --
        # this exact filename would have raised "No compaction files found"
        # against the pre-fix slurper.
        session_file = agent_dir / "6ff45d9a-8628-4005-8063-402692a24a94.jsonl"

        events = [
            {
                "type": "user", "uuid": "u1", "parentUuid": None,
                "sessionId": "sess", "entrypoint": "cli",
                "timestamp": "2026-08-17T10:00:00.000Z",
                "message": {"role": "user", "content": "Decision: use pytest for the test suite."},
            },
            {
                # A tool_use block whose JSON *input* contains signal-shaped
                # substrings ("Accomplishment:", "completed") that must NOT
                # be picked up as real signal -- this is the regression test
                # for the original bug (979 false accomplishments on real
                # data because raw JSON was substring-matched).
                "type": "assistant", "uuid": "u2", "parentUuid": "u1",
                "sessionId": "sess", "entrypoint": "cli",
                "timestamp": "2026-08-17T10:00:05.000Z",
                "message": {"role": "assistant", "content": [
                    {"type": "tool_use", "id": "t1", "name": "Bash",
                     "input": {"command": "echo done", "description": "Accomplishment: fake task completed"}},
                ]},
            },
            {
                "type": "assistant", "uuid": "u3", "parentUuid": "u2",
                "sessionId": "sess", "entrypoint": "claude-vscode",
                "timestamp": "2026-08-17T10:00:10.000Z",
                "message": {"role": "assistant", "content": [
                    {"type": "text", "text": "Learning: streaming JSON parsing works great.\nTODO: add a real test."},
                ]},
            },
            {
                "type": "system", "subtype": "compact_boundary",
                "uuid": "b1", "parentUuid": None, "logicalParentUuid": "u3",
                "sessionId": "sess", "entrypoint": "cli",
                "timestamp": "2026-08-17T10:05:00.000Z",
                "content": "Conversation compacted",
                "compactMetadata": {
                    "trigger": "auto", "preTokens": 5000, "postTokens": 500,
                    "durationMs": 1200, "cumulativeDroppedTokens": 4500,
                    "preservedMessages": {"anchorUuid": "u3", "uuids": ["u3"], "allUuids": ["u1", "u2", "u3"]},
                    "preservedSegment": {"headUuid": "u1", "anchorUuid": "u3", "tailUuid": "u3"},
                },
            },
            {
                "type": "user", "uuid": "u4", "parentUuid": None,
                "sessionId": "sess", "entrypoint": "cli",
                "timestamp": "2026-08-17T10:06:00.000Z",
                "message": {"role": "user", "content": "Accomplished: shipped the fix."},
            },
        ]
        _write_jsonl(session_file, events)

        slurper = create_slurper(str(agent_dir))
        chunks = list(slurper.slurp(resume=False))

        assert len(chunks) == 2, f"Expected 2 segments (1 boundary), got {len(chunks)}"

        first, second = chunks
        assert first.source_kind == "real_jsonl"
        assert first.event_count == 3, f"Expected 3 events before the boundary, got {first.event_count}"
        assert first.entrypoints == {"cli": 2, "claude-vscode": 1}, first.entrypoints
        assert first.boundary_trigger == "auto"
        assert first.tokens_pre == 5000 and first.tokens_post == 500
        assert first.start_time is not None and first.end_time is not None

        decision_texts = " ".join(d.decision for d in first.decisions)
        assert "pytest" in decision_texts, f"Real decision text not captured: {decision_texts}"

        learning_texts = " ".join(first.learnings)
        assert "streaming JSON parsing" in learning_texts, f"Real learning not captured: {learning_texts}"

        # The regression check: the tool_use input's "Accomplishment: fake
        # task completed" must never appear anywhere in the extracted
        # signal -- it's JSON structure, not prose.
        all_accomplishments = " ".join(first.key_accomplishments) + " ".join(second.key_accomplishments)
        assert "fake task" not in all_accomplishments, (
            f"Tool-call JSON leaked into signal extraction: {all_accomplishments}"
        )

        assert second.source_kind == "real_jsonl"
        assert second.boundary_trigger is None  # ended at EOF, not another boundary
        assert "shipped the fix" in " ".join(second.key_accomplishments)

    print("  ✓ Real JSONL discovery + segmentation passed")


def test_real_jsonl_pii_redaction():
    """PII redaction must work on real (json.loads-decoded) message text,
    where a Windows path appears with single backslashes -- the original
    LOCAL_PATH pattern only matched doubled backslashes and silently never
    fired on real content (Agent-Of/miller#3)."""
    print("Test 10: PII redaction on real decoded JSONL text...")

    with tempfile.TemporaryDirectory() as tmpdir:
        agent_dir = Path(tmpdir) / "test_agent"
        agent_dir.mkdir()
        session_file = agent_dir / "11111111-2222-3333-4444-555555555555.jsonl"

        real_path_text = r"Decision: write output to C:\Users\alice\project\out.txt"
        events = [
            {
                "type": "user", "uuid": "u1", "parentUuid": None,
                "sessionId": "sess", "entrypoint": "cli",
                "timestamp": "2026-08-17T10:00:00.000Z",
                "message": {"role": "user", "content": real_path_text},
            },
        ]
        _write_jsonl(session_file, events)

        slurper = create_slurper(str(agent_dir))
        chunks = list(slurper.slurp(resume=False))
        assert len(chunks) == 1
        decision_texts = " ".join(d.decision for d in chunks[0].decisions)
        assert "{LOCAL_PATH}" in decision_texts, f"Path was not redacted: {decision_texts}"
        assert "alice" not in decision_texts, f"Username leaked past redaction: {decision_texts}"

    print("  ✓ PII redaction on real content passed")


def test_noise_patterns_actually_applied():
    """NOISE_PATTERNS was defined but never referenced anywhere else in the
    module (Agent-Of/miller#3) -- filter_log() only ever ran the separate
    substring-keyword check. Verify the regex patterns are now wired in."""
    print("Test 11: NOISE_PATTERNS regex patterns are actually applied...")

    content = "Real signal line.\n<function_calls>\n<invoke>fake</invoke>\n</function_calls>\nMore signal."
    filtered = NoiseFilter.filter_log(content)
    assert "<invoke>fake</invoke>" not in filtered, f"Block-level noise pattern not applied: {filtered!r}"
    assert "Real signal line." in filtered
    assert "More signal." in filtered

    print("  ✓ NOISE_PATTERNS wiring passed")


def run_all_tests():
    """Run all tests."""
    print("\nAgent Slurper Test Suite")
    print("=" * 60)

    tests = [
        test_basic_slurping,
        test_multiple_compactions,
        test_checkpoint_persistence,
        test_noise_filtering,
        test_generator_pattern,
        test_chunk_summary,
        test_empty_directory,
        test_clear_checkpoints,
        test_real_jsonl_discovered_and_parsed,
        test_real_jsonl_pii_redaction,
        test_noise_patterns_actually_applied,
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"  ✗ {test_func.__name__} failed: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
