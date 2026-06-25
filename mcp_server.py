"""mcp_server.py – Orchestrator that chains all agents together.

Security checks (deterministic layer) run first. Any ValueError they raise
propagates up to the Streamlit UI for clean error display.
"""
from __future__ import annotations

import json
from typing import Any

from agents import GeoFormattingAgent, IngestionAgent, RoutingAgent, SecurityAgent
from schema import AgentState
from security import is_allowed_file, sanitize_json_text, validate_node_count


def execute_workflow(raw_data: dict[str, Any]) -> AgentState:
    """Run the full multi-agent pipeline on *raw_data*.

    Order:
        1. Deterministic security checks (security.py) – raises ValueError on failure.
        2. IngestionAgent  – ranks camps by vulnerability.
        3. RoutingAgent    – calculates supply routes.
        4. SecurityAgent   – scans for PII / equity violations.
        5. GeoFormattingAgent – builds the Markdown report and GeoJSON.
        6. SecurityAgent (second pass) – ensures the report is also clean.

    Raises:
        ValueError: if the security pre-processing layer rejects the input.
    """
    # ── 1. Deterministic security pre-processing ──────────────────────────────
    # Re-serialise to a plain string so sanitize_json_text can strip any
    # injected HTML tags before they reach the LLMs.
    raw_text = json.dumps(raw_data)
    clean_text = sanitize_json_text(raw_text)
    raw_data = json.loads(clean_text)

    # Node-count gate – raises ValueError if the scenario is out of bounds.
    validate_node_count(raw_data)

    # ── 2. Build initial state ────────────────────────────────────────────────
    state = AgentState(raw_data=raw_data)

    # ── 3. Agent chain ────────────────────────────────────────────────────────
    ingestion_agent = IngestionAgent()
    routing_agent = RoutingAgent()
    security_agent = SecurityAgent()
    geo_formatting_agent = GeoFormattingAgent()

    state.prioritized_camps = ingestion_agent.run(state.raw_data)
    state.final_routes = routing_agent.run(state.raw_data, state.prioritized_camps)

    state = security_agent.run(state)
    state.markdown_report, state.geojson = geo_formatting_agent.run(
        state.raw_data,
        state.final_routes,
        state.prioritized_camps,
        state.security_flag,
        state.security_logs,
    )
    state = security_agent.run(state)

    return state


def execute_workflow_from_upload(filename: str, raw_bytes: bytes) -> AgentState:
    """Validate, parse, and run the workflow for an uploaded file.

    Args:
        filename: Original filename from the uploader widget.
        raw_bytes: Raw bytes content of the uploaded file.

    Returns:
        Completed AgentState.

    Raises:
        ValueError: For any security or format violation.
    """
    if not is_allowed_file(filename):
        raise ValueError(
            f"Security Error: Only .json files are accepted. "
            f"Got '{filename}'."
        )

    try:
        raw_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            "Security Error: File could not be decoded as UTF-8 text."
        ) from exc

    try:
        raw_data: dict[str, Any] = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Security Error: Uploaded file is not valid JSON. {exc}"
        ) from exc

    if not isinstance(raw_data, dict):
        raise ValueError(
            "Security Error: JSON root must be an object (dict), not a list or primitive."
        )

    return execute_workflow(raw_data)
