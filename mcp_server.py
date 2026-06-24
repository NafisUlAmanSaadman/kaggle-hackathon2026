from __future__ import annotations

from typing import Any

from agents import GeoFormattingAgent, IngestionAgent, RoutingAgent, SecurityAgent
from schema import AgentState


def execute_workflow(raw_data: dict[str, Any]) -> AgentState:
    state = AgentState(raw_data=raw_data)

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

