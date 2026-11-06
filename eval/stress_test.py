"""
Resilience & stress test for the LangGraph self-correction loop.

Validates reviewer interception, researcher re-routing, monotonic loop_count,
and clean termination at max_loops without infinite cycles.

Run: python -m eval.stress_test
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from typing import Any
from unittest.mock import patch

import app.agent.graph as agent_graph_module
from app.agent.graph import build_agent_graph
from app.tasks.tasks import build_initial_state


AMBIGUOUS_TOPIC = (
    "Obscure hypothetical market with no public 2026 benchmarks or verifiable citations"
)


async def _run_graph_with_reviewer(
    reviewer_impl,
    *,
    max_loops: int = 3,
    topic: str = AMBIGUOUS_TOPIC,
) -> tuple[dict[str, Any], list[int]]:
    job_id = str(uuid.uuid4())
    state = build_initial_state(job_id, topic)
    state["max_loops"] = max_loops

    loop_samples: list[int] = []
    final: dict[str, Any] = dict(state)

    with patch.object(agent_graph_module, "reviewer_node", reviewer_impl):
        graph = build_agent_graph()
        async for event in graph.astream(state, stream_mode="updates"):
            for _node, update in event.items():
                if "loop_count" in update:
                    loop_samples.append(int(update["loop_count"]))
                final = {**final, **update}

    return final, loop_samples


async def test_reviewer_rejects_then_recovers() -> None:
    """Reviewer fails first round, approves second — loop_count must increase then stabilize."""

    calls = 0

    async def reviewer(state):
        nonlocal calls
        calls += 1
        loop_count = state.get("loop_count", 0)
        if calls == 1:
            return {
                "status": "rejected",
                "reviewer_feedback": (
                    "Rejected: Missing 2026 data signals. Routing back to researcher."
                ),
                "loop_count": loop_count + 1,
                "review": {"approved": False, "confidence_score": 0.4, "issues": ["missing 2026"]},
                "telemetry": ["Reviewer: FAIL — routing back to Researcher"],
            }
        return {
            "status": "approved",
            "reviewer_feedback": "",
            "review": {"approved": True, "confidence_score": 0.9},
            "telemetry": ["Reviewer: PASS — routing to persist"],
        }

    final, loops = await _run_graph_with_reviewer(reviewer, max_loops=3)

    assert final.get("status") == "approved", f"expected approval, got {final.get('status')}"
    assert loops, "loop_count was never updated on rejection"
    assert loops == sorted(loops), f"loop_count not monotonic: {loops}"
    assert max(loops) >= 1, "expected at least one rejection loop"
    print("[PASS] Reviewer intercepts bad draft and graph recovers after re-research.")


async def test_max_loops_forces_finalize() -> None:
    """Always-reject reviewer must hit max_loops=3 and finalize without hanging."""

    async def always_reject(state):
        loop_count = state.get("loop_count", 0)
        return {
            "status": "rejected",
            "reviewer_feedback": "Rejected: Missing 2026 data signals.",
            "loop_count": loop_count + 1,
            "review": {"approved": False, "confidence_score": 0.2},
            "telemetry": ["Reviewer: FAIL — routing back to Researcher"],
        }

    final, loops = await _run_graph_with_reviewer(always_reject, max_loops=3)

    assert final.get("job_status") == "failed", f"expected failed job, got {final.get('job_status')}"
    assert final.get("status") == "rejected"
    assert loops, "expected loop_count updates"
    assert loops == sorted(loops), f"loop_count not monotonic: {loops}"
    assert max(loops) <= 3, f"loop_count exceeded cap: {loops}"
    assert final.get("final_payload"), "finalize node should persist payload"
    print("[PASS] Max loop cap reached; graph finalized cleanly (no infinite loop).")


async def test_ambiguous_topic_live_reviewer() -> None:
    """Optional live run: real reviewer may reject drafts missing 2026 timeline signals."""

    graph = build_agent_graph()
    job_id = str(uuid.uuid4())
    state = build_initial_state(job_id, AMBIGUOUS_TOPIC)
    state["max_loops"] = 3

    loop_samples: list[int] = []
    final: dict[str, Any] = dict(state)
    async for event in graph.astream(state, stream_mode="updates"):
        for node, update in event.items():
            if node == "reviewer" and "loop_count" in update:
                loop_samples.append(int(update["loop_count"]))
            final = {**final, **update}

    if loop_samples:
        assert loop_samples == sorted(loop_samples), f"non-monotonic loops: {loop_samples}"
    print(
        f"[INFO] Live ambiguous topic finished: verification={final.get('status')}, "
        f"job_status={final.get('job_status')}, loops={loop_samples or 'none'}"
    )


async def main() -> int:
    print("=== LangGraph resilience stress test ===\n")
    await test_reviewer_rejects_then_recovers()
    await test_max_loops_forces_finalize()
    await test_ambiguous_topic_live_reviewer()
    print("\n=== All stress checks passed ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
