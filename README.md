# 🛰️ Pre-Monsoon Logistics Orchestrator v2.0

> **Kaggle Five Days of AI Agents — Capstone Project (Agents for Good)**  
> A multi-agent AI system for humanitarian supply-chain orchestration in the Rohingya refugee camps of Cox's Bazar, Bangladesh.

---

## 🌍 The Problem

The Rohingya refugee crisis in Cox's Bazar, Bangladesh, is one of the world's largest humanitarian emergencies, with over one million displaced people living in densely packed camps. Every year, the pre-monsoon window (April–June) is the last opportunity for NGOs and aid agencies to pre-position critical supplies — food, medicine, and shelter materials — before roads become impassable due to landslides, flooding, and extreme rainfall.

**The challenge:** Allocating limited warehouse inventory across 30+ geographically dispersed camp blocks, each with different population sizes, vulnerability scores, and road-risk profiles — all under a narrow, rapidly closing time window.

This project demonstrates how AI agents can assist logistics coordinators with data-driven, equity-aware route planning, while maintaining strict data-safety standards.

---

## 🏗️ Multi-Agent Architecture

```
 ┌─────────────────────────────────────────────────────────────────────┐
 │                        MCP Orchestrator                             │
 │                       (mcp_server.py)                               │
 │                                                                     │
 │  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐  │
 │  │  SECURITY    │    │  INGESTION   │    │      ROUTING         │  │
 │  │  Pre-check   │───▶│    Agent     │───▶│      Agent           │  │
 │  │ (security.py)│    │ (Gemini LLM) │    │   (Gemini LLM)       │  │
 │  │              │    │              │    │                      │  │
 │  │ • File type  │    │ Ranks camps  │    │ Calculates routes    │  │
 │  │ • HTML strip │    │ by vuln.     │    │ avoiding high-risk   │  │
 │  │ • Node count │    │ score &      │    │ monsoon paths        │  │
 │  └──────────────┘    │ population   │    └──────────┬───────────┘  │
 │                      └──────────────┘               │              │
 │                                                     ▼              │
 │  ┌──────────────────────┐      ┌──────────────────────────────┐    │
 │  │    GEO-FORMATTING    │◀─────│       SECURITY AGENT         │    │
 │  │        Agent         │      │       (LLM Bouncer)           │    │
 │  │    (Gemini LLM)      │      │                              │    │
 │  │                      │      │ • PII detection & redaction  │    │
 │  │ Empathetic Markdown  │      │ • Equity violation checks    │    │
 │  │ report + GeoJSON     │      │ • Runs twice (pre + post)    │    │
 │  └──────────────────────┘      └──────────────────────────────┘    │
 └─────────────────────────────────────────────────────────────────────┘
```

### Agent Roles

| Agent | Technology | Responsibility |
|---|---|---|
| **IngestionAgent** | Gemini LLM + deterministic fallback | Parses the scenario JSON, ranks camp blocks by `vulnerability_score` and population demand |
| **RoutingAgent** | Gemini LLM + deterministic fallback | Assigns warehouse inventory to camps via lowest-risk edges; outputs `Route` objects |
| **SecurityAgent** | Regex + PII patterns | Scans the full `AgentState` for Refugee IDs, emails, phone numbers; runs equity checks (no camp should receive ≥90% of supplies) |
| **GeoFormattingAgent** | Gemini LLM + deterministic fallback | Writes a concise, empathetic Markdown NGO report and builds a GeoJSON FeatureCollection |

---

## 🔒 Dual-Layer Security

### Layer 1 — Deterministic Pre-Processing (`security.py`)
Runs **before any LLM call**, using only pure Python logic:

| Check | Function | What it does |
|---|---|---|
| File-type gate | `is_allowed_file(filename)` | Rejects any upload that is not a `.json` file |
| Sanitisation | `sanitize_json_text(raw_text)` | Strips HTML/script tags and collapses excessive whitespace to prevent prompt injection |
| Node-count validation | `validate_node_count(data_dict)` | Ensures ≥1 warehouse and 1–30 camp blocks; raises `ValueError` on violation |

All failures raise a clean `ValueError` that the UI catches and displays as `st.error()` — no raw Python traceback ever reaches the user.

### Layer 2 — LLM Security Agent (`SecurityAgent` in `agents.py`)
Runs **twice** in the pipeline (after routing, and after the report is written):

- **PII Detection**: Regex patterns for Refugee IDs, email addresses, and Bangladeshi phone numbers.
- **PII Redaction**: Matched strings are replaced with `[REDACTED_PII]` in the full state payload.
- **Equity Auditing**: Flags routes where a single camp receives ≥65% of total allocated supplies (warning) or ≥90% (violation).

---

## 📂 File Structure

```
humanitarian-ai-capstone/
├── .env                    # API keys (not committed)
├── .env.example            # Template for environment setup
├── requirements.txt        # Pinned Python dependencies
├── README.md               # This file
│
├── generate_scenario.py    # Synthetic Cox's Bazar scenario builder
├── schema.py               # Pydantic models: Route, AgentState
├── security.py             # ★ NEW: Deterministic pre-processing layer
├── agents.py               # Gemini-backed agents with fallback logic
├── mcp_server.py           # MCP orchestrator — chains all agents
└── app.py                  # Streamlit UI with Folium map
```

---

## 🚀 Installation & Running

### Prerequisites
- Python 3.10+
- A Google Gemini API key (optional — the app runs with deterministic fallbacks without one)

### Steps

```powershell
# 1. Clone the repository
git clone <repo-url>
cd humanitarian-ai-capstone

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
copy .env.example .env
# Edit .env and add your GEMINI_API_KEY

# 4. Run the app
streamlit run app.py
```

The app will open at `http://localhost:8501`.

### Without a Gemini API Key
The app works fully offline using deterministic fallback logic in each agent. All security layers, the Folium map, and the Streamlit UI function identically — only the LLM-generated narrative will be replaced by a structured template report.

---

## 🗺️ How to Use

1. **Upload a custom scenario** — use the sidebar file uploader to load your own `.json` scenario (must match the schema), or use the built-in default.
2. **Click ▶ Run Logistics Orchestration** — the MCP orchestrator runs the full agent chain.
3. **View results** — the Folium map updates with colour-coded routes (green = low risk → dark red = critical), and the NGO Markdown report appears below.
4. **Inspect logs** — expand the **Security & Equity Logs** panel to review all PII findings and equity audit results.

---

## 🧑‍💻 Dependencies

| Package | Version | Purpose |
|---|---|---|
| `streamlit` | 1.32.0 | Web UI framework |
| `folium` | 0.16.0 | Interactive Leaflet maps |
| `streamlit-folium` | 0.19.0 | Embeds Folium inside Streamlit |
| `pydantic` | 2.6.4 | Data validation & schema enforcement |
| `google-generativeai` | 0.4.1 | Gemini LLM integration |
| `python-dotenv` | 1.0.1 | Loads `.env` API keys |

---

## ⚖️ Ethical Considerations

- **No real PII is used.** The scenario data is entirely synthetic. The simulated Refugee ID in the default scenario exists solely to demonstrate the Security Agent's detection and redaction capabilities.
- **Equity auditing** ensures AI-generated routes do not concentrate all supplies in a single camp at the expense of others.
- **Human-in-the-loop:** This tool is designed to *assist* logistics coordinators, not replace them. All route plans require human review and confirmation before dispatch.

---

*Built for the Kaggle Five Days of AI Agents Capstone · June 2026*
