"""
Agent Compaction Slurper

A production-ready streaming tool for analyzing agent compaction histories.
Extracts high-signal content from agent session logs with checkpoint support.
"""

from slurper import AgentSlurper, create_slurper
from models import CompactionChunk, Decision, WorkProduct, ContinuityThread
from filters import NoiseFilter

__version__ = "1.0.0"
__author__ = "Victor/VIRGIL"

__all__ = [
    "AgentSlurper",
    "create_slurper",
    "CompactionChunk",
    "Decision",
    "WorkProduct",
    "ContinuityThread",
    "NoiseFilter",
]
