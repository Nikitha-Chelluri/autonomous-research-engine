from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable
from typing import Any

import httpx

NODE_PATTERN = re.compile(
    r"Entering Node:\s*(Researcher|Writer\s*/\s*Editor|Quality Reviewer|Finalize)",
    re.IGNORECASE,
)


def parse_active_node(telemetry_lines: list[str]) -> str | None:
    for line in reversed(telemetry_lines):
        match = NODE_PATTERN.search(line)
        if match:
            name = match.group(1).lower()
            if "writer" in name:
                return "writer"
            if "reviewer" in name or "quality" in name:
                return "reviewer"
            if "finalize" in name:
                return "finalize"
            return "researcher"
    return None


def extract_rejection_events(telemetry_lines: list[str], reviewer_feedback: str | None) -> list[str]:
    events: list[str] = []
    for line in telemetry_lines:
        lower = line.lower()
        if "fail" in lower or "rejected" in lower or "routing back" in lower or "quality control" in lower:
            events.append(line)
    if reviewer_feedback:
        for part in reviewer_feedback.split("\n"):
            part = part.strip()
            if part:
                events.append(part if part.startswith("-") else f"- {part}")
    return events


def render_graph_path_html(active: str | None, last_rejection: bool) -> str:
    nodes = [
        ("researcher", "RESEARCHER"),
        ("writer", "WRITER"),
        ("reviewer", "REVIEWER"),
    ]
    parts: list[str] = []
    for idx, (key, label) in enumerate(nodes):
        is_active = active == key
        color = "#e74c3c" if last_rejection and key == "reviewer" else "#2ecc71" if is_active else "#95a5a6"
        weight = "700" if is_active else "400"
        parts.append(
            f'<span style="color:{color};font-weight:{weight}">[{label}]</span>'
        )
        if idx < len(nodes) - 1:
            parts.append('<span style="color:#7f8c8d"> ──► </span>')
    return "".join(parts)


class SSETelemetryClient:
    """Background SSE reader; drains lines into a shared list."""

    def __init__(self, api_base: str, job_id: str, on_line: Callable[[str], None] | None = None) -> None:
        self._api_base = api_base.rstrip("/")
        self._job_id = job_id
        self._on_line = on_line
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        url = f"{self._api_base}/research/jobs/{self._job_id}/stream"
        try:
            with httpx.Client(timeout=None) as client:
                with client.stream("GET", url) as response:
                    event_type = "message"
                    data_buf: list[str] = []
                    for raw in response.iter_lines():
                        if self._stop.is_set():
                            break
                        if raw is None:
                            continue
                        line = raw.strip() if isinstance(raw, str) else raw.decode().strip()
                        if not line:
                            if data_buf:
                                payload = "\n".join(data_buf)
                                self._emit(event_type, payload)
                                data_buf = []
                            continue
                        if line.startswith("event:"):
                            event_type = line.split(":", 1)[1].strip()
                        elif line.startswith("data:"):
                            data_buf.append(line.split(":", 1)[1].strip())
        except Exception:
            pass

    def _emit(self, event_type: str, data: str) -> None:
        if event_type == "node" and self._on_line:
            self._on_line(f"Node update: {data}")
            return
        if event_type == "telemetry" and self._on_line:
            self._on_line(data)
            return
        try:
            payload = json.loads(data)
            for line in payload.get("telemetry", []):
                if self._on_line:
                    self._on_line(str(line))
        except json.JSONDecodeError:
            if self._on_line:
                self._on_line(data)


def fetch_job(api_base: str, job_id: str) -> dict[str, Any] | None:
    try:
        response = httpx.get(f"{api_base}/research/jobs/{job_id}", timeout=15.0)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError:
        return None


def create_job(api_base: str, topic: str, focus_entities: list[str]) -> dict[str, Any]:
    response = httpx.post(
        f"{api_base}/research/jobs",
        json={
            "topic": topic,
            "report_type": "competitive_intelligence",
            "focus_entities": focus_entities,
        },
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()
