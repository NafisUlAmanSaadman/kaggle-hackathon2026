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

# ── Custom CSS Redesign Theme: "Storm & Sanctuary" ────────────────────────────
CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
  --font-display: 'Outfit', sans-serif;
  --font-body: 'Inter', sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
  
  --color-bg: #FAFAF9;
  --color-sidebar: #0F172A;
  --color-text-main: #1E293B;
  --color-accent-teal: #0D9488;
  --color-warning-amber: #D97706;
  --color-critical-rust: #B91C1C;
  --color-card-bg: #FFFFFF;
}

/* Global Font Override */
.main {
  background-color: var(--color-bg) !important;
  color: var(--color-text-main) !important;
  font-family: var(--font-body) !important;
}
h1, h2, h3, h4, h5, h6 {
  font-family: var(--font-display) !important;
  font-weight: 700 !important;
  color: #0F172A !important;
}

/* Sidebar Styles */
section[data-testid="stSidebar"] {
  background-color: var(--color-sidebar) !important;
  color: #F1F5F9 !important;
  border-right: 1px solid #334155 !important;
}
section[data-testid="stSidebar"] h1, 
section[data-testid="stSidebar"] h2, 
section[data-testid="stSidebar"] h3,
section[data-testid="stSidebar"] h4,
section[data-testid="stSidebar"] h5,
section[data-testid="stSidebar"] h6,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] label {
  color: #F1F5F9 !important;
  font-family: var(--font-display) !important;
}
section[data-testid="stSidebar"] div.stButton > button {
  background-color: #1E293B !important;
  color: #F1F5F9 !important;
  border: 1px solid #475569 !important;
  border-radius: 8px !important;
  font-family: var(--font-display) !important;
  font-weight: 500 !important;
  transition: all 0.2s ease !important;
  width: 100% !important;
}
section[data-testid="stSidebar"] div.stButton > button:hover {
  background-color: #0D9488 !important;
  color: #FFFFFF !important;
  border-color: #0D9488 !important;
  box-shadow: 0 4px 12px rgba(13, 148, 136, 0.3) !important;
}
section[data-testid="stSidebar"] div.stButton > button[kind="primary"] {
  background-color: #0D9488 !important;
  color: #FFFFFF !important;
  border: none !important;
  font-family: var(--font-display) !important;
  font-weight: 600 !important;
  border-radius: 8px !important;
  box-shadow: 0 4px 14px rgba(13, 148, 136, 0.4) !important;
  transition: all 0.3s ease !important;
}
section[data-testid="stSidebar"] div.stButton > button[kind="primary"]:hover {
  background-color: #0F766E !important;
  transform: translateY(-1px) !important;
  box-shadow: 0 6px 20px rgba(13, 148, 136, 0.5) !important;
}
/* ── File Uploader Dropzone ────────────────────────────────── */
section[data-testid="stSidebar"] div[data-testid="stFileUploader"] {
  background-color: #1E293B !important;
  border: 1px dashed #475569 !important;
  border-radius: 8px !important;
  padding: 16px !important;
}
section[data-testid="stSidebar"] div[data-testid="stFileUploader"] section {
  background-color: transparent !important;
  display: flex !important;
  flex-direction: column !important;
  align-items: center !important;
  justify-content: center !important;
}
/* Hide the broken Material Icon that renders literal "upload" text */
section[data-testid="stSidebar"] div[data-testid="stFileUploader"] button [data-testid="stIconMaterial"],
section[data-testid="stSidebar"] div[data-testid="stFileUploader"] button .material-icons,
section[data-testid="stSidebar"] div[data-testid="stFileUploader"] button .material-symbols-rounded,
section[data-testid="stSidebar"] div[data-testid="stFileUploader"] button span[aria-hidden="true"] {
  display: none !important;
  width: 0 !important;
  height: 0 !important;
  overflow: hidden !important;
  font-size: 0 !important;
}
/* Style the browse button cleanly */
section[data-testid="stSidebar"] div[data-testid="stFileUploader"] button {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  padding: 8px 20px !important;
  background-color: #334155 !important;
  color: #F1F5F9 !important;
  border: 1px solid #475569 !important;
  border-radius: 6px !important;
  font-family: var(--font-display) !important;
  font-size: 0.85rem !important;
  font-weight: 500 !important;
  cursor: pointer !important;
  transition: all 0.2s ease !important;
  margin-top: 4px !important;
  line-height: 1.4 !important;
  white-space: nowrap !important;
  gap: 0 !important;
}
section[data-testid="stSidebar"] div[data-testid="stFileUploader"] button:hover {
  background-color: #0D9488 !important;
  border-color: #0D9488 !important;
  color: #FFFFFF !important;
}
/* Prevent any inner text duplication */
section[data-testid="stSidebar"] div[data-testid="stFileUploader"] section > div {
  display: flex !important;
  flex-direction: column !important;
  align-items: center !important;
  justify-content: center !important;
  gap: 6px !important;
  overflow: hidden !important;
  text-align: center !important;
}
/* File-size label styling */
section[data-testid="stSidebar"] div[data-testid="stFileUploader"] section > div > span,
section[data-testid="stSidebar"] div[data-testid="stFileUploader"] small {
  display: block !important;
  white-space: nowrap !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
  max-width: 100% !important;
  font-size: 0.75rem !important;
  color: #94A3B8 !important;
}
section[data-testid="stSidebar"] hr {
  border-color: #334155 !important;
}

/* Main Dashboard Header */
.app-header {
  margin-bottom: 2rem;
  padding-bottom: 1.5rem;
  border-bottom: 1px solid #E2E8F0;
  position: relative;
}
.radar-status {
  display: inline-flex;
  align-items: center;
  background-color: #F0FDFA;
  border: 1px solid #CCFBF1;
  color: #0D9488;
  font-family: var(--font-display);
  font-size: 0.75rem;
  font-weight: 700;
  padding: 4px 10px;
  border-radius: 20px;
  letter-spacing: 0.05em;
  margin-bottom: 0.75rem;
}
.pulse-dot {
  width: 8px;
  height: 8px;
  background-color: #0D9488;
  border-radius: 50%;
  margin-right: 6px;
  display: inline-block;
  box-shadow: 0 0 0 0 rgba(13, 148, 136, 0.4);
  animation: pulse 1.5s infinite;
}
@keyframes pulse {
  0% {
    transform: scale(0.95);
    box-shadow: 0 0 0 0 rgba(13, 148, 136, 0.7);
  }
  70% {
    transform: scale(1);
    box-shadow: 0 0 0 6px rgba(13, 148, 136, 0);
  }
  100% {
    transform: scale(0.95);
    box-shadow: 0 0 0 0 rgba(13, 148, 136, 0);
  }
}
.main-title {
  font-size: 2.5rem !important;
  font-weight: 800 !important;
  letter-spacing: -0.02em !important;
  margin: 0 0 0.5rem 0 !important;
  color: #FFFFFF !important;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.12);
}
.subtitle {
  font-size: 1.05rem !important;
  color: #CBD5E1 !important;
  margin: 0 !important;
  font-family: var(--font-body) !important;
}

/* Map Frame Style */
iframe {
  border-radius: 12px !important;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08) !important;
  border: 1px solid #E2E8F0 !important;
  margin-bottom: 24px !important;
}

/* Sidebar Custom Metrics */
.sidebar-metrics {
  background: #1E293B;
  border-radius: 8px;
  padding: 16px 18px;
  border: 1px solid #334155;
  margin-top: 16px;
}
.sidebar-metric-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid rgba(51, 65, 85, 0.6);
}
.sidebar-metric-row:last-child {
  border-bottom: none;
}
.sidebar-metric-row .label {
  font-size: 0.85rem;
  color: #94A3B8;
  line-height: 1.5;
}
.sidebar-metric-row .val {
  font-family: var(--font-display);
  font-weight: 700;
  font-size: 1.1rem;
  color: #F8FAFC;
  line-height: 1.5;
}

/* Metrics Dashboard Grid */
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
  margin: 20px 0;
}
.metric-card {
  background: #FFFFFF;
  border: 1px solid #E2E8F0;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.01), 0 10px 15px -3px rgba(0, 0, 0, 0.02);
  transition: all 0.3s ease;
  position: relative;
  overflow: hidden;
}
.metric-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 12px 20px rgba(0, 0, 0, 0.05);
}
.metric-card::before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  width: 4px;
  height: 100%;
}
.metric-card.cyan-border::before { background-color: #38BDF8; }
.metric-card.teal-border::before { background-color: #0D9488; }
.metric-card.warning-border::before { background-color: #10B981; }
.metric-card.alert-border::before { background-color: #EF4444; }
.metric-card.aqua-border::before { background-color: #06B6D4; }

.metric-label {
  font-family: var(--font-display);
  font-size: 0.8rem;
  font-weight: 600;
  color: #64748B;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.metric-value {
  font-family: var(--font-display);
  font-size: 2rem;
  font-weight: 800;
  color: #0F172A;
  margin: 8px 0 4px 0;
  line-height: 1.1;
}
.metric-unit {
  font-size: 0.9rem;
  font-weight: 500;
  color: #64748B;
}
.metric-indicator {
  font-size: 0.75rem;
  color: #94A3B8;
}

/* Markdown Report Styling Wrapper */
.report-card {
  background: #FFFFFF;
  border: 1px solid #E2E8F0;
  border-radius: 12px;
  padding: 32px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.01), 0 20px 25px -5px rgba(0, 0, 0, 0.04);
  margin-top: 24px;
}
.report-card h3 {
  border-bottom: 2px solid #F1F5F9;
  padding-bottom: 12px;
  margin-top: 0;
  margin-bottom: 20px;
  color: #0F172A;
}

/* Security Logs Panel Styles */
.security-logs-wrapper {
  background-color: #FFFBEB;
  border: 1px solid #FDE68A;
  border-radius: 8px;
  padding: 16px;
  margin-top: 16px;
}
.security-logs-wrapper.violating {
  background-color: #FEF2F2;
  border: 1px solid #FCA5A5;
}
</style>
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

    m = folium.Map(location=[21.17, 92.15], zoom_start=11, tiles="CartoDB Dark_Matter")
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
    # Inject Custom Design System CSS
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    
    # Custom dashboard header
    st.markdown(
        """
        <div class="app-header">
          <div class="radar-status">
            <span class="pulse-dot"></span>
            ACTIVE ROUTING RADAR MONITOR
          </div>
          <h1 class="main-title">🛰️ Pre-Monsoon Logistics Orchestrator</h1>
          <p class="subtitle">A multi-agent AI system for humanitarian supply routing in Rohingya refugee camps · Cox's Bazar, Bangladesh</p>
        </div>
        """,
        unsafe_allow_html=True
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

        # ── Immediate upload preview ──────────────────────────────────────────
        # Parse the uploaded file right away (lightweight JSON-only, no agent
        # logic) so sidebar metrics and the map preview reflect the new file
        # the moment it is selected — before the user clicks Run.
        upload_preview: dict[str, Any] | None = None
        if uploaded_file is not None:
            try:
                upload_preview = json.loads(uploaded_file.getvalue().decode("utf-8"))
                if isinstance(upload_preview, dict):
                    # Update active_data so the map and metrics preview
                    # the uploaded scenario immediately.
                    active_data = upload_preview
                    st.session_state["active_raw_data"] = active_data
                    st.caption(
                        f"📄 **{uploaded_file.name}** loaded — "
                        f"{len(upload_preview.get('warehouses', []))} warehouse(s), "
                        f"{len(upload_preview.get('camp_blocks', []))} camp(s) detected."
                    )
                else:
                    st.warning("⚠️ Uploaded file is not a JSON object — metrics may be stale.")
                    upload_preview = None
            except (ValueError, UnicodeDecodeError):
                st.warning("⚠️ Could not preview file — it may not be valid JSON.")
                upload_preview = None

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

        # ── Quick metrics (always reflects the currently active scenario) ─────
        sidebar_metrics_html = f"""
        <div class="sidebar-metrics">
          <div class="sidebar-metric-row">
             <span class="label">🏢 Warehouses</span>
             <span class="val">{len(active_data.get("warehouses", []))}</span>
          </div>
          <div class="sidebar-metric-row">
             <span class="label">⛺ Camp Blocks</span>
             <span class="val">{len(active_data.get("camp_blocks", []))}</span>
          </div>
          <div class="sidebar-metric-row">
             <span class="label">⛈️ Weather Alerts</span>
             <span class="val">{len(active_data.get("weather_alerts", []))}</span>
          </div>
        </div>
        """
        st.markdown(sidebar_metrics_html, unsafe_allow_html=True)

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
        total_supplies = sum(r.supplies_allocated for r in state.final_routes)
        
        # Build custom metrics grid
        security_color_class = "alert-border" if state.security_flag else "warning-border"
        security_status = "⚠️ Raised" if state.security_flag else "✅ Clear"
        security_desc = "PII or equity alerts detected" if state.security_flag else "Compliance checks passed"
        
        metrics_html = f"""
        <div class="metrics-grid">
          <div class="metric-card cyan-border">
            <div class="metric-label">Routes Planned</div>
            <div class="metric-value">{len(state.final_routes)}</div>
            <div class="metric-indicator">Camp blocks routed</div>
          </div>
          <div class="metric-card teal-border">
            <div class="metric-label">Supplies Allocated</div>
            <div class="metric-value">{total_supplies:,} <span class="metric-unit">kits</span></div>
            <div class="metric-indicator">Distributed from inventory</div>
          </div>
          <div class="metric-card {security_color_class}">
            <div class="metric-label">Security Flag</div>
            <div class="metric-value">{security_status}</div>
            <div class="metric-indicator">{security_desc}</div>
          </div>
          <div class="metric-card aqua-border">
            <div class="metric-label">GeoJSON Features</div>
            <div class="metric-value">{len(state.geojson.get("features", []))}</div>
            <div class="metric-indicator">Mapped coordinates exported</div>
          </div>
        </div>
        """
        st.markdown(metrics_html, unsafe_allow_html=True)

        if state.security_logs:
            wrapper_class = "violating" if state.security_flag else ""
            with st.expander("🔐 Security & Equity Logs", expanded=state.security_flag):
                st.markdown(f'<div class="security-logs-wrapper {wrapper_class}">', unsafe_allow_html=True)
                for log in state.security_logs:
                    icon = "⚠️" if "violation" in log.lower() or "warning" in log.lower() else "ℹ️"
                    st.markdown(f'<div style="margin-bottom: 6px; font-family: var(--font-body); font-size: 0.9rem;">{icon} {log}</div>', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)

        st.divider()
        
        # Combine the report into a single styled container to ensure it renders inside the same div wrapper
        st.markdown(
            f'<div class="report-card">\n\n{state.markdown_report}\n\n</div>',
            unsafe_allow_html=True
        )

        with st.expander("📄 Final Secure AgentState JSON"):
            st.json(state.model_dump())
    else:
        st.info(
            "Upload a scenario JSON or use the default scenario, then click "
            "**▶ Run Logistics Orchestration** to generate secure routes and the NGO report."
        )


if __name__ == "__main__":
    main()
