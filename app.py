"""app.py – Streamlit UI for the Pre-Monsoon Logistics Orchestrator.

Features
--------
* File uploader: accepts a custom scenario JSON.
* Error handling: ValueError from the security / workflow layer is caught and
  displayed as st.error() – the app never crashes with a raw traceback.
* Map: Folium route map via streamlit-folium.
* render_map is cached with st.cache_data (keyed on scenario + routes hash) so
  it only rebuilds when data actually changes.
* Stale session state is cleared automatically when the uploaded file changes.
* Antigravity animation: floating 🚁 and 📦 emojis injected via st.markdown
  with custom CSS – no st.balloons().
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import folium
import streamlit as st
from dotenv import load_dotenv
from streamlit_folium import st_folium

from generate_scenario import DEFAULT_OUTPUT_PATH, generate_scenario
from mcp_server import execute_workflow, execute_workflow_from_upload
from schema import AgentState, Route


load_dotenv()

# ── Risk colour palette ───────────────────────────────────────────────────────
RISK_COLORS = {
    "low": "#27ae60",
    "medium": "#f39c12",
    "high": "#e74c3c",
    "critical": "#8e0e00",
}

# ── Floating route-marker CSS (injected into the Folium map) ──────────────────
FLOATING_MARKER_CSS = """
<style>
@keyframes route-float {
  0%   { transform: translateY(0);    opacity: 0.74; }
  50%  { transform: translateY(-10px); opacity: 1; }
  100% { transform: translateY(0);    opacity: 0.74; }
}
.route-float-marker {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 3px solid white;
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.24);
  animation: route-float 1.8s ease-in-out infinite;
}
</style>
"""

# ── Antigravity animation: floating drones & supply crates ───────────────────
ANTIGRAVITY_HTML = """
<style>
  @keyframes floatUp {
    0%   { transform: translateY(0)   scale(1);    opacity: 1; }
    80%  { transform: translateY(-88vh) scale(1.18); opacity: 0.9; }
    100% { transform: translateY(-100vh) scale(0.8); opacity: 0; }
  }
  @keyframes sway {
    0%,100% { margin-left: 0; }
    33%      { margin-left: 28px; }
    66%      { margin-left: -28px; }
  }
  .ag-container {
    position: fixed;
    top: 0; left: 0;
    width: 100vw; height: 0;
    pointer-events: none;
    z-index: 9999;
    overflow: visible;
  }
  .ag-emoji {
    position: absolute;
    bottom: -60px;
    font-size: 2.4rem;
    animation: floatUp var(--dur) ease-in var(--delay) 1 forwards,
               sway calc(var(--dur) * 0.6) ease-in-out var(--delay) infinite;
  }
</style>
<div class="ag-container" id="ag-anim">
  <span class="ag-emoji" style="left:8%;  --dur:3.8s; --delay:0.0s;">🚁</span>
  <span class="ag-emoji" style="left:18%; --dur:4.2s; --delay:0.3s;">📦</span>
  <span class="ag-emoji" style="left:30%; --dur:3.5s; --delay:0.6s;">🚁</span>
  <span class="ag-emoji" style="left:42%; --dur:4.8s; --delay:0.1s;">📦</span>
  <span class="ag-emoji" style="left:55%; --dur:3.9s; --delay:0.5s;">🚁</span>
  <span class="ag-emoji" style="left:65%; --dur:4.4s; --delay:0.2s;">📦</span>
  <span class="ag-emoji" style="left:76%; --dur:3.6s; --delay:0.8s;">🚁</span>
  <span class="ag-emoji" style="left:87%; --dur:4.1s; --delay:0.4s;">📦</span>
  <span class="ag-emoji" style="left:94%; --dur:3.7s; --delay:0.7s;">🚁</span>
</div>
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_default_scenario() -> dict[str, Any]:
    """Load the default scenario from disk, generating it if absent."""
    if not DEFAULT_OUTPUT_PATH.exists():
        return generate_scenario(DEFAULT_OUTPUT_PATH)
    return json.loads(DEFAULT_OUTPUT_PATH.read_text(encoding="utf-8"))


def node_lookup(raw_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return a flat id→node dict covering both warehouses and camps."""
    return {
        item["id"]: item
        for collection_name in ("warehouses", "camp_blocks")
        for item in raw_data.get(collection_name, [])
    }


def _map_cache_key(raw_data: dict[str, Any], routes: list[Route]) -> str:
    """Stable hash key for the render_map cache.

    Uses a SHA-1 of the serialised raw_data + route list so the map only
    rebuilds when the underlying data actually changes.
    """
    payload = json.dumps(
        {"raw_data": raw_data, "routes": [r.model_dump() for r in routes]},
        sort_keys=True,
    )
    return hashlib.sha1(payload.encode()).hexdigest()


@st.cache_data(show_spinner=False)
def render_map(cache_key: str, raw_data: dict[str, Any], routes_json: str) -> folium.Map:
    """Build a Folium map showing warehouses, camps, and (optionally) routes.

    ``cache_key`` is a content-hash that busts the cache whenever ``raw_data``
    or ``routes`` change.  ``routes_json`` carries the serialised routes so
    Streamlit can hash the arguments correctly (Pydantic models are not
    directly hashable by st.cache_data).
    """
    routes: list[Route] = [Route.model_validate(r) for r in json.loads(routes_json)]

    m = folium.Map(location=[21.17, 92.15], zoom_start=11, tiles="CartoDB Positron")
    m.get_root().html.add_child(folium.Element(FLOATING_MARKER_CSS))

    # Warehouses
    for warehouse in raw_data.get("warehouses", []):
        folium.Marker(
            location=[warehouse["lat"], warehouse["lon"]],
            popup=f"{warehouse['name']}<br>Inventory: {warehouse['inventory']:,}",
            tooltip=warehouse["name"],
            icon=folium.Icon(color="blue", icon="home", prefix="fa"),
        ).add_to(m)

    # Camp blocks
    for camp in raw_data.get("camp_blocks", []):
        vulnerability = int(camp.get("vulnerability_score", 0))
        color = "#8e0e00" if vulnerability >= 8 else "#e58e26" if vulnerability >= 6 else "#27ae60"
        folium.CircleMarker(
            location=[camp["lat"], camp["lon"]],
            radius=7 + vulnerability,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.72,
            popup=(
                f"{camp['name']}<br>"
                f"Population: {camp['population']:,}<br>"
                f"Vulnerability: {vulnerability}/10"
            ),
            tooltip=camp["name"],
        ).add_to(m)

    # Routes
    nodes = node_lookup(raw_data)
    for route in routes:
        source = nodes.get(route.source)
        target = nodes.get(route.target)
        if not source or not target:
            continue

        color = RISK_COLORS.get(route.risk_level, "#4a69bd")
        line = [[source["lat"], source["lon"]], [target["lat"], target["lon"]]]
        folium.PolyLine(
            line,
            color=color,
            weight=5,
            opacity=0.85,
            tooltip=(
                f"{route.source} → {route.target}: "
                f"{route.supplies_allocated:,} kits · {route.risk_level} risk"
            ),
        ).add_to(m)

        # Animated dot at the destination
        folium.Marker(
            location=[target["lat"], target["lon"]],
            icon=folium.DivIcon(
                html=f'<div class="route-float-marker" style="background:{color};"></div>'
            ),
        ).add_to(m)

    return m


def restore_state(payload: dict[str, Any] | None) -> AgentState | None:
    """Rehydrate an AgentState from session_state, if available."""
    if not payload:
        return None
    return AgentState.model_validate(payload)


# ── Main app ──────────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(
        page_title="Pre-Monsoon Logistics Orchestrator",
        page_icon="🚁",
        layout="wide",
    )
    st.title("🛰️ Pre-Monsoon Logistics Orchestrator")
    st.caption(
        "A multi-agent AI system for humanitarian supply routing in Rohingya refugee camps · "
        "Cox's Bazar, Bangladesh"
    )

    # ── Session state ─────────────────────────────────────────────────────────
    state: AgentState | None = restore_state(st.session_state.get("workflow_state"))
    # active_data tracks which raw_data is currently shown on the map
    active_data: dict[str, Any] = st.session_state.get(
        "active_raw_data", load_default_scenario()
    )

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.header("⚙️ MCP Control Panel")
        st.divider()

        # ── File uploader ─────────────────────────────────────────────────────
        st.subheader("📂 Upload Scenario")
        uploaded_file = st.file_uploader(
            "Upload a custom scenario JSON",
            type=["json"],
            help="Must be a valid JSON file matching the scenario schema.",
        )

        # Detect file change: if a new file is loaded, clear stale workflow
        # state so the map and metrics always reflect the current scenario.
        current_upload_name = uploaded_file.name if uploaded_file is not None else None
        previous_upload_name = st.session_state.get("last_uploaded_filename")
        if current_upload_name != previous_upload_name:
            st.session_state["last_uploaded_filename"] = current_upload_name
            st.session_state.pop("workflow_state", None)
            state = None

        st.divider()

        # ── Default scenario controls ─────────────────────────────────────────
        st.subheader("🔄 Default Scenario")
        regenerate = st.button("Regenerate Default Scenario", use_container_width=True)
        if regenerate:
            active_data = generate_scenario(DEFAULT_OUTPUT_PATH)
            st.session_state["active_raw_data"] = active_data
            st.session_state.pop("workflow_state", None)
            st.session_state.pop("last_uploaded_filename", None)
            state = None
            st.toast("Default scenario regenerated.")

        st.divider()

        # ── Run button ────────────────────────────────────────────────────────
        run_workflow = st.button(
            "▶ Run Logistics Orchestration",
            type="primary",
            use_container_width=True,
        )

        st.divider()

        # ── Quick metrics ─────────────────────────────────────────────────────
        st.metric("Warehouses", len(active_data.get("warehouses", [])))
        st.metric("Camp Blocks", len(active_data.get("camp_blocks", [])))
        st.metric("Weather Alerts", len(active_data.get("weather_alerts", [])))

    # ── Workflow execution ────────────────────────────────────────────────────
    if run_workflow:
        with st.spinner("🔄 Coordinating agents: ingestion → routing → security → geo-formatting…"):
            try:
                if uploaded_file is not None:
                    # ── Uploaded file path ─────────────────────────────────────
                    new_state = execute_workflow_from_upload(
                        uploaded_file.name,
                        uploaded_file.read(),
                    )
                    # After successful parse, mirror the raw_data so map updates
                    active_data = new_state.raw_data
                    st.session_state["active_raw_data"] = active_data
                else:
                    # ── Default scenario path ──────────────────────────────────
                    new_state = execute_workflow(active_data)

                state = new_state
                st.session_state["workflow_state"] = state.model_dump()
                st.toast("✅ Secure route plan finalized.")

                # ── Antigravity animation (no st.balloons!) ────────────────────
                st.markdown(ANTIGRAVITY_HTML, unsafe_allow_html=True)

            except ValueError as e:
                st.error(f"🚫 {e}")
                state = restore_state(st.session_state.get("workflow_state"))

    # ── Map ───────────────────────────────────────────────────────────────────
    routes = state.final_routes if state else []
    map_data = active_data if state is None else state.raw_data
    # Build a stable cache key from the current data so the map only
    # rebuilds when something actually changed.
    cache_key = _map_cache_key(map_data, routes)
    routes_json = json.dumps([r.model_dump() for r in routes])
    map_view = render_map(cache_key, map_data, routes_json)
    st_folium(map_view, width=None, height=560, returned_objects=[])

    # ── Results ───────────────────────────────────────────────────────────────
    if state:
        st.divider()
        metric_cols = st.columns(4)
        total_supplies = sum(r.supplies_allocated for r in state.final_routes)
        metric_cols[0].metric("Routes Planned", len(state.final_routes))
        metric_cols[1].metric("Supplies Allocated", f"{total_supplies:,} kits")
        metric_cols[2].metric(
            "Security Flag", "⚠️ Raised" if state.security_flag else "✅ Clear"
        )
        metric_cols[3].metric(
            "GeoJSON Features", len(state.geojson.get("features", []))
        )

        if state.security_logs:
            with st.expander("🔐 Security & Equity Logs", expanded=state.security_flag):
                for log in state.security_logs:
                    icon = "⚠️" if "violation" in log.lower() or "warning" in log.lower() else "ℹ️"
                    st.write(f"{icon} {log}")

        st.divider()
        st.markdown(state.markdown_report)

        with st.expander("📄 Final Secure AgentState JSON"):
            st.json(state.model_dump())
    else:
        st.info(
            "Upload a scenario JSON or use the default scenario, then click "
            "**▶ Run Logistics Orchestration** to generate secure routes and the NGO report."
        )


if __name__ == "__main__":
    main()
