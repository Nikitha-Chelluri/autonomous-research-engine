"""
Full-stack integration test: API -> Celery -> LangGraph -> Postgres.

Prerequisites:
  docker compose up -d
  uvicorn app.main:app --port 8010
  celery -A app.tasks.celery_app worker --loglevel=warning -P solo

Run: python -m eval.full_stack_test
"""

from __future__ import annotations

import os
import sys
import time

import httpx

API_BASE = os.getenv("RESEARCH_API_URL", "http://localhost:8010").rstrip("/")
POLL_SECONDS = 120
POLL_INTERVAL = 2.0


def main() -> int:
    print(f"=== Full stack test against {API_BASE} ===\n")

    with httpx.Client(timeout=30.0) as client:
        health = client.get(f"{API_BASE}/health")
        if health.status_code != 200:
            print(f"FAIL: /health -> {health.status_code}")
            return 1
        print(f"OK: /health -> {health.json()}")

        create = client.post(
            f"{API_BASE}/research/jobs",
            json={
                "topic": "Full stack test: CRM competitive landscape 2026",
                "report_type": "competitive_intelligence",
                "focus_entities": ["Salesforce", "HubSpot"],
            },
        )
        if create.status_code != 200:
            print(f"FAIL: POST /research/jobs -> {create.status_code}\n{create.text}")
            return 1

        job = create.json()
        job_id = job["id"]
        print(f"OK: job created {job_id} (celery={job.get('celery_task_id')})")

        deadline = time.time() + POLL_SECONDS
        last_status = None
        detail: dict = {}

        while time.time() < deadline:
            resp = client.get(f"{API_BASE}/research/jobs/{job_id}")
            if resp.status_code != 200:
                print(f"FAIL: GET job -> {resp.status_code}")
                return 1
            detail = resp.json()
            status = detail.get("status")
            if status != last_status:
                print(f"  status -> {status}")
                last_status = status
            if status in ("completed", "failed"):
                break
            time.sleep(POLL_INTERVAL)
        else:
            print(f"FAIL: timed out after {POLL_SECONDS}s (last status={last_status})")
            return 1

        print(f"\nFinal status: {detail.get('status')}")
        if detail.get("error_message"):
            print(f"Error: {detail['error_message']}")

        payload = detail.get("result_payload") or {}
        markdown = detail.get("markdown_body") or payload.get("markdown_body") or ""
        trace = detail.get("trace_log") or []

        checks = [
            ("trace_log present", len(trace) > 0),
            ("markdown_body present", len(markdown) > 100),
            ("result_payload present", bool(payload)),
            ("sources_compiled", bool(payload.get("sources_compiled"))),
        ]

        print("\nAssertions:")
        failed = False
        for name, ok in checks:
            mark = "OK" if ok else "FAIL"
            print(f"  [{mark}] {name}")
            failed = failed or not ok

        if detail.get("status") not in ("completed", "failed"):
            print("  [FAIL] job reached terminal state")
            failed = True

        if failed:
            return 1

        print("\n=== Full stack test PASSED ===")
        print(f"  confidence_score: {detail.get('confidence_score')}")
        print(f"  execution_time_seconds: {detail.get('execution_time_seconds')}")
        print(f"  verification: {payload.get('verification_status')}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
