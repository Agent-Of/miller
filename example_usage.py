"""
Simple example of using the agent slurper.

This shows the basic API for iterating through compaction chunks.
"""

from slurper import create_slurper


def main():
    """Example usage of the slurper."""

    # Create a slurper for an agent's session logs
    slurper = create_slurper("/path/to/agent/logs")

    # Optional: Check checkpoint status
    status = slurper.get_checkpoint_status()
    print(f"Checkpoint status: {status}")

    # Iterate through compactions
    for chunk in slurper.slurp(resume=True):
        print(f"\n{chunk.compaction_label}")
        print("=" * 60)

        # Access high-signal content
        print(f"Summary: {chunk.session_summary}")
        print(f"Raw log size: {chunk.raw_log_length} bytes")

        if chunk.key_accomplishments:
            print("\nAccomplishments:")
            for acc in chunk.key_accomplishments:
                print(f"  - {acc}")

        if chunk.decisions:
            print("\nDecisions:")
            for dec in chunk.decisions:
                print(f"  - {dec.decision}")

        if chunk.learnings:
            print("\nLearnings:")
            for learn in chunk.learnings:
                print(f"  - {learn}")

        if chunk.continuity_threads:
            print("\nOpen Threads:")
            for thread in chunk.continuity_threads:
                print(f"  - {thread.description} [{thread.status}]")

        # Or use the built-in summary
        print("\n" + chunk.summary())


if __name__ == "__main__":
    main()
