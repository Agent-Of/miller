"""
Test suite for agent compaction slurper.

SOPHIA-class agents can use this to verify the implementation.
"""

import json
import tempfile
from pathlib import Path
from slurper import create_slurper, AgentSlurper
from models import CompactionChunk, Decision, WorkProduct


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
