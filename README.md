# Pre-Monsoon Logistics Orchestrator

Kaggle Five Days of AI Agents capstone project for the Agents for Good track.

This Streamlit app simulates a multi-agent humanitarian logistics workflow for Rohingya refugee camp preparedness in Cox's Bazar. An MCP-style orchestrator coordinates ingestion, routing, security, and geo-formatting agents, then renders the route plan on a Folium map.

## Architecture

- `generate_scenario.py` builds synthetic warehouse, camp, route-edge, weather, and simulated PII data.
- `schema.py` defines strict Pydantic models for route and agent state handoffs.
- `agents.py` contains Gemini-backed agents with deterministic fallbacks for local demos.
- `mcp_server.py` coordinates the execution order and final state.
- `app.py` provides the Streamlit and Folium interface.

## Run Locally

```powershell
pip install -r requirements.txt
copy .env.example .env
streamlit run app.py
```

Add a Gemini API key to `.env` to enable live LLM calls. Without a key, the app still runs using deterministic fallback logic.

## Data Safety

The generated scenario intentionally includes simulated PII, such as a fake Refugee ID, so the Security Agent can demonstrate detection and redaction before the final payload is rendered.

