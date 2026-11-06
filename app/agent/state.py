"""Re-export graph state types from the canonical schema module."""

from app.agents.state import (
    ResearchGraphState,
    ResearchState,
    ReviewResult,
    raw_sources_to_notes,
)

# ResearchGraphState extends ResearchState with orchestration fields (telemetry, job_id, …).
# LangGraph is compiled against ResearchGraphState while nodes use core ResearchState fields.

__all__ = [
    "ResearchGraphState",
    "ResearchState",
    "ReviewResult",
    "raw_sources_to_notes",
]
