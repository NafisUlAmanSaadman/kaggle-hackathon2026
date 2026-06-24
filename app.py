from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import folium
import streamlit as st
from dotenv import load_dotenv
from streamlit_folium import st_folium

from generate_scenario import DEFAULT_OUTPUT_PATH, generate_scenario
from mcp_server import execute_workflow
from schema import AgentState, Route


load_dotenv()

RISK_COLORS = {
    "low": "#218c74",
    "medium": "#f6b93b",
    "high": "#e55039",
    "critical": "#b71540",
}

FLOATING_MARKER_CSS = """
<style>
@keyframes route-float {
  0% { transform: translateY(0); opacity: 0.74; }
  50% { transform: translateY(-10px); opacity: 1; }
  100% { transform: translateY(0); opacity: 0.74; }
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


def load_scenario() -> dict[str, Any]:
    if not DEFAULT_OUTPUT_PATH.exists():
        return generate_scenario(DEFAULT_OUTPUT_PATH)
    return json.loads(DEFAULT_OUTPUT_PATH.read_text(encoding="utf-8"))


def node_lookup(raw_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        item["id"]: item
        for collection_name in ("warehouses", "camp_blocks")
        for item in raw_data.get(collection_name, [])
    }


def render_map(raw_data: dict[str, Any], routes: list[Route] | None = None) -> folium.Map:
    routes = routes or []
    m = folium.Map(location=[21.17, 92.15], zoom_start=11, tiles="CartoDB Positron")
    m.get_root().html.add_child(folium.Element(FLOATING_MARKER_CSS))

    for warehouse in raw_data.get("warehouses", []):
        folium.Marker(
            location=[warehouse["lat"], warehouse["lon"]],
            popup=f"{warehouse['name']}<br>Inventory: {warehouse['inventory']:,}",
            tooltip=warehouse["name"],
            icon=folium.Icon(color="blue", icon="home", prefix="fa"),
        ).add_to(m)

    for camp in raw_data.get("camp_blocks", []):
        vulnerability = int(camp.get("vulnerability_score", 0))
        color = "#b71540" if vulnerability >= 8 else "#e58e26" if vulnerability >= 6 else "#218c74"
        folium.CircleMarker(
            location=[camp["lat"], camp["lon"]],
            radius=7 + vulnerability,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.72,
            popup=f"{camp['name']}<br>Population: {camp['population']:,}<br>Vulnerability: {vulnerability}/10",
            tooltip=camp["name"],
        ).add_to(m)

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
            opacity=0.82,
            tooltip=(
                f"{route.source} to {route.target}: "
                f"{route.supplies_allocated:,} kits, {route.risk_level} risk"
            ),
        ).add_to(m)

        folium.Marker(
            location=[target["lat"], target["lon"]],
            icon=folium.DivIcon(
                html=(
                    f'<div class="route-float-marker" '
                    f'style="background:{color};"></div>'
                )
            ),
        ).add_to(m)

    return m


def restore_state(payload: dict[str, Any] | None) -> AgentState | None:
    if not payload:
        return None
    return AgentState.model_validate(payload)


def main() -> None:
    st.set_page_config(page_title="Pre-Monsoon Logistics Orchestrator", layout="wide")
    st.title("Pre-Monsoon Logistics Orchestrator")

    raw_data = load_scenario()
    state = restore_state(st.session_state.get("workflow_state"))

    with st.sidebar:
        st.header("MCP Control")
        st.caption(raw_data["scenario_name"])
        run_workflow = st.button("Run Logistics Orchestration", type="primary", use_container_width=True)
        regenerate = st.button("Regenerate Scenario", use_container_width=True)

        if regenerate:
            raw_data = generate_scenario(DEFAULT_OUTPUT_PATH)
            st.session_state.pop("workflow_state", None)
            state = None
            st.toast("Scenario regenerated.")

        st.divider()
        st.metric("Warehouses", len(raw_data.get("warehouses", [])))
        st.metric("Camp Blocks", len(raw_data.get("camp_blocks", [])))
        st.metric("Weather Alerts", len(raw_data.get("weather_alerts", [])))

    if run_workflow:
        with st.spinner("Coordinating ingestion, routing, security, and geo-formatting agents..."):
            state = execute_workflow(raw_data)
            st.session_state["workflow_state"] = state.model_dump()
        st.toast("Secure route plan finalized.")
        st.balloons()

    routes = state.final_routes if state else []
    map_view = render_map(raw_data if state is None else state.raw_data, routes)
    st_folium(map_view, width=None, height=560, returned_objects=[])

    if state:
        metric_cols = st.columns(4)
        total_supplies = sum(route.supplies_allocated for route in state.final_routes)
        metric_cols[0].metric("Routes", len(state.final_routes))
        metric_cols[1].metric("Supplies Allocated", f"{total_supplies:,}")
        metric_cols[2].metric("Security Flag", "Raised" if state.security_flag else "Clear")
        metric_cols[3].metric("GeoJSON Features", len(state.geojson.get("features", [])))

        if state.security_logs:
            with st.expander("Security and Equity Logs", expanded=state.security_flag):
                for log in state.security_logs:
                    st.write(log)

        st.markdown(state.markdown_report)

        with st.expander("Final Secure AgentState JSON"):
            st.json(state.model_dump())
    else:
        st.info("Run the logistics orchestration to generate secure routes and the NGO report.")


if __name__ == "__main__":
    main()

