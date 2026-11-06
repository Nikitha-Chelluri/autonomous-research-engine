"""
Streamlit real-time telemetry dashboard for the research agent graph.

Run from repo root: streamlit run services/dashboard/app.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import streamlit as st

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.dashboard.config import API_BASE_URL
from services.dashboard.telemetry import (
    SSETelemetryClient,
    create_job,
    extract_rejection_events,
    fetch_job,
    parse_active_node,
    render_graph_path_html,
)

st.set_page_config(
    page_title="Agent Research Telemetry",
    page_icon="📡",
    layout="wide",
)

if "telemetry" not in st.session_state:
    st.session_state.telemetry = []
if "job_id" not in st.session_state:
    st.session_state.job_id = None
if "sse_client" not in st.session_state:
    st.session_state.sse_client = None
if "last_rejection" not in st.session_state:
    st.session_state.last_rejection = False


def _append_telemetry(line: str) -> None:
    if line and line not in st.session_state.telemetry:
        st.session_state.telemetry.append(line)
    lower = line.lower()
    if "fail" in lower or "routing back" in lower or "rejected" in lower:
        st.session_state.last_rejection = True
    if "pass" in lower and "reviewer" in lower:
        st.session_state.last_rejection = False


def _stop_sse() -> None:
    client = st.session_state.sse_client
    if client:
        client.stop()
    st.session_state.sse_client = None


st.title("Autonomous Research Engine — Live Telemetry")
st.caption(f"API: `{API_BASE_URL}`")

with st.sidebar:
    st.header("New research job")
    topic = st.text_input("Topic", value="Enterprise CRM competitive landscape 2026")
    entities_raw = st.text_input("Focus entities (comma-separated)", value="Salesforce, HubSpot")
    if st.button("Start job", type="primary"):
        _stop_sse()
        st.session_state.telemetry = []
        st.session_state.last_rejection = False
        entities = [e.strip() for e in entities_raw.split(",") if e.strip()]
        try:
            created = create_job(API_BASE_URL, topic, entities)
            st.session_state.job_id = created["id"]
            client = SSETelemetryClient(API_BASE_URL, created["id"], on_line=_append_telemetry)
            client.start()
            st.session_state.sse_client = client
            st.success(f"Job started: {created['id']}")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Failed to create job: {exc}")

    if st.session_state.job_id:
        st.divider()
        st.subheader("Job")
        st.code(str(st.session_state.job_id))

job_id = st.session_state.job_id
job = fetch_job(API_BASE_URL, job_id) if job_id else None

if job and job.get("status") in ("completed", "failed"):
    _stop_sse()
    if job.get("trace_log"):
        for line in job["trace_log"]:
            _append_telemetry(str(line))

tab_live, tab_report = st.tabs(["Live execution", "Final document hub"])

with tab_live:
    if not job_id:
        st.info("Start a job from the sidebar to watch the graph execute.")
    else:
        active = parse_active_node(st.session_state.telemetry)
        path_html = render_graph_path_html(active, st.session_state.last_rejection)
        st.markdown("### Active graph path")
        st.markdown(path_html, unsafe_allow_html=True)

        status = job.get("status", "running") if job else "running"
        st.metric("Job status", status)

        rejections = extract_rejection_events(st.session_state.telemetry, None)
        st.markdown("### Live correction console")
        if rejections:
            for event in rejections:
                st.error(event)
        else:
            st.success("No reviewer rejections yet — pipeline is progressing.")

        st.markdown("### Telemetry stream")
        console = st.container(height=320)
        with console:
            for line in st.session_state.telemetry[-200:]:
                st.text(line)

        if status not in ("completed", "failed"):
            time.sleep(1.5)
            st.rerun()

with tab_report:
    if not job_id or not job:
        st.info("Complete a job to view the final report.")
    else:
        payload = job.get("result_payload") or {}
        col_main, col_meta = st.columns([3, 1])

        with col_meta:
            st.subheader("Metadata")
            st.json(
                {
                    "sources_compiled": payload.get("sources_compiled", []),
                    "execution_time_seconds": payload.get("execution_time_seconds")
                    or job.get("execution_time_seconds"),
                    "confidence_score": payload.get("confidence_score") or job.get("confidence_score"),
                    "verification_status": payload.get("verification_status"),
                    "loop_count": payload.get("loop_count"),
                    "approved": payload.get("approved"),
                }
            )

        with col_main:
            st.subheader("Generated report")
            markdown_body = job.get("markdown_body") or payload.get("markdown_body") or ""
            if markdown_body:
                st.markdown(markdown_body)
                st.download_button(
                    "Download raw .md",
                    data=markdown_body,
                    file_name=f"research_{job_id}.md",
                    mime="text/markdown",
                )
            else:
                st.warning("No markdown body yet.")
