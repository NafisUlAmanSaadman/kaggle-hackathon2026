# 🛰️ Pre-Monsoon Logistics Orchestrator

> **Kaggle Five Days of AI Agents — Capstone Project**
> *Track: Agents for Good*

A multi-agent AI system that uses Google Gemini to orchestrate humanitarian supply-chain routing in the Rohingya refugee camps of Cox's Bazar, Bangladesh — with built-in PII redaction, equity auditing, and a polished Streamlit dashboard.

---

## 📋 Table of Contents

- [The Problem](#-the-problem)
- [Our Solution](#-our-solution)
- [Multi-Agent Architecture](#-multi-agent-architecture)
- [Dual-Layer Security Design](#-dual-layer-security-design)
- [Data Pipeline & Workflow](#-data-pipeline--workflow)
- [Scenario Schema](#-scenario-schema)
- [UI & Visual Design — "Storm & Sanctuary"](#-ui--visual-design--storm--sanctuary)
- [Project Structure](#-project-structure)
- [Setup & Installation](#-setup--installation)
- [How to Use](#-how-to-use)
- [Testing & Verification](#-testing--verification)
- [Dependencies](#-dependencies)
- [Ethical Considerations](#-ethical-considerations)
- [License](#-license)

---

## 🌍 The Problem

The Rohingya refugee crisis in Cox's Bazar, Bangladesh, is one of the world's largest humanitarian emergencies. Over **one million displaced people** live in densely packed camps across 30+ geographically dispersed blocks. Each year, the **pre-monsoon window (April–June)** represents the last opportunity for NGOs and aid agencies to pre-position critical supplies — food, medicine, shelter materials — before roads become impassable due to landslides, flooding, and extreme rainfall.

### Why is this hard?

| Challenge | Impact |
|---|---|
| **Limited warehouse inventory** | Total supply kits are finite and must be allocated equitably |
| **30+ camp blocks** with varying populations (5 k–23 k) and vulnerability scores (1–10) | Prioritization requires multi-factor ranking |
| **Monsoon risk multipliers** on every road edge | Some routes double in travel time; others become impassable |
| **Data sensitivity** | Refugee IDs, contact numbers, and worker emails must never appear in reports |
| **Narrow time window** | Coordinators need actionable plans fast — not raw data dumps |

Manual allocation is slow, error-prone, and risks concentrating all supplies in whichever camp the loudest advocacy reaches first. This project demonstrates how **AI agents can assist logistics coordinators** with data-driven, equity-aware route planning, while maintaining strict data-safety standards.

---

## 💡 Our Solution

We built a **four-agent MCP (Model Context Protocol) orchestration pipeline** that:

1. **Ingests and prioritizes** camp blocks by a composite vulnerability + demand score.
2. **Routes supplies** from warehouses to camps along lowest-risk monsoon edges.
3. **Audits the plan** for PII leakage and equity violations (no camp should hoard ≥90 % of supplies).
4. **Formats the output** as an empathetic NGO Markdown report and a standards-compliant GeoJSON FeatureCollection.

Every agent is backed by **Google Gemini** for intelligent reasoning, with a **deterministic fallback** that activates when no API key is available — meaning the app is fully functional offline.

---

## 🏗️ Multi-Agent Architecture

```
 ┌───────────────────────────────────────────────────────────────────────┐
 │                        MCP Orchestrator                               │
 │                       (mcp_server.py)                                 │
 │                                                                       │
 │   ┌───────────────┐   ┌───────────────┐   ┌────────────────────────┐ │
 │   │  SECURITY     │   │  INGESTION    │   │      ROUTING           │ │
 │   │  Pre-check    │──▶│    Agent      │──▶│      Agent             │ │
 │   │(security.py)  │   │ (Gemini LLM)  │   │   (Gemini LLM)        │ │
 │   │               │   │               │   │                        │ │
 │   │ • File gate   │   │ Ranks camps   │   │ Allocates inventory    │ │
 │   │ • HTML strip  │   │ by vuln.      │   │ via lowest-risk        │ │
 │   │ • Node count  │   │ score &       │   │ monsoon edges          │ │
 │   │ • Schema val. │   │ population    │   │                        │ │
 │   └───────────────┘   └───────────────┘   └──────────┬─────────────┘ │
 │                                                       │               │
 │                                                       ▼               │
 │   ┌────────────────────────┐    ┌───────────────────────────────────┐ │
 │   │   GEO-FORMATTING       │◀───│       SECURITY AGENT              │ │
 │   │       Agent             │    │       (LLM Bouncer)               │ │
 │   │   (Gemini LLM)         │    │                                   │ │
 │   │                        │    │ • PII detection & redaction       │ │
 │   │ Empathetic Markdown    │    │ • Equity violation checks         │ │
 │   │ report + GeoJSON       │    │ • Runs twice (pre + post report)  │ │
 │   └────────────────────────┘    └───────────────────────────────────┘ │
 └───────────────────────────────────────────────────────────────────────┘
```

### Agent Roles

| # | Agent | Module | Technology | Responsibility |
|---|---|---|---|---|
| 1 | **IngestionAgent** | `agents.py` | Gemini LLM + deterministic fallback | Parses scenario JSON, ranks camp blocks by composite `priority_score = (vulnerability × 10) + (population / 2500)`. Cross-references LLM-returned IDs against the scenario to drop hallucinated entries. |
| 2 | **RoutingAgent** | `agents.py` | Gemini LLM + deterministic fallback | Assigns warehouse inventory to camps via lowest effective-travel-time edges (`base_time × monsoon_multiplier`). Validates every route through Pydantic's `Route` model and cross-checks source/target IDs. |
| 3 | **SecurityAgent** | `agents.py` | Regex + rule-based logic | Scans the full serialized `AgentState` for PII (Refugee IDs, emails, Bangladeshi phone numbers). Redacts matches with `[REDACTED_PII]`. Runs an equity audit: warns at ≥65 % concentration, flags violations at ≥90 %. Executes **twice** — once after routing, once after report generation. |
| 4 | **GeoFormattingAgent** | `agents.py` | Gemini LLM + deterministic fallback | Generates a concise, empathetic Markdown report for NGO field workers. Builds a GeoJSON `FeatureCollection` of `LineString` features (warehouse → camp) with supply and risk metadata. Applies a final PII safety-net redaction on the raw LLM response text. |

### Anti-Hallucination Safeguards

Both the IngestionAgent and RoutingAgent validate LLM outputs against the scenario's actual node IDs before accepting them. If the LLM invents a warehouse or camp that doesn't exist, the entry is silently dropped and logged. If no valid entries survive, the system falls back to deterministic logic — ensuring the pipeline **never crashes or propagates hallucinated data**.

---

## 🔒 Dual-Layer Security Design

### Layer 1 — Deterministic Pre-Processing (`security.py`)

Runs **before any LLM call**, using only pure Python logic:

| Check | Function | What it does |
|---|---|---|
| File-type gate | `is_allowed_file(filename)` | Rejects any upload that is not `.json` (case-insensitive) |
| Sanitization | `sanitize_json_text(raw_text)` | Strips HTML/script tags via regex; collapses excessive whitespace to prevent prompt injection |
| Node-count validation | `validate_node_count(data_dict)` | Requires ≥1 warehouse, 1–30 camp blocks; raises `ValueError` on violation |
| Schema validation | `ScenarioInput` (Pydantic v2) | Full structural validation: lat/lon types, non-negative inventory, vulnerability 0–10, travel times > 0, etc. |

All failures raise a clean `ValueError` that the Streamlit UI catches and displays via `st.error()` — **no raw Python traceback ever reaches the user.**

### Layer 2 — LLM Security Agent (`SecurityAgent`)

Runs **twice** in the pipeline (after routing and after the report):

| Capability | Details |
|---|---|
| **PII Detection** | 4 regex patterns: explicit Refugee IDs, 5+ digit alphanumeric codes, email addresses, Bangladeshi mobile numbers (`+88` / `01x` format) |
| **PII Redaction** | All matched strings replaced with `[REDACTED_PII]` in the full serialized state |
| **Equity Auditing** | Flags routes where a single camp receives ≥65 % (warning) or ≥90 % (violation) of total allocated supplies |

### Centralized PII Redaction

PII redaction runs **once** at the orchestrator level (`mcp_server.py`) before any agent receives the data. Individual agents no longer need to call `redact_pii` — they operate on already-clean data. A final safety net in the GeoFormattingAgent re-scans the raw LLM response text.

---

## 🔄 Data Pipeline & Workflow

```
Upload / Default JSON
        │
        ▼
 ┌──────────────────────┐
 │  1. Deterministic     │   security.py
 │     Security Checks   │   (file gate, HTML strip, node count)
 └──────────┬───────────┘
            ▼
 ┌──────────────────────┐
 │  2. Pydantic Schema   │   schema.py → ScenarioInput
 │     Validation        │
 └──────────┬───────────┘
            ▼
 ┌──────────────────────┐
 │  3. PII Redaction     │   agents.redact_pii()
 │     (single pass)     │
 └──────────┬───────────┘
            ▼
 ┌──────────────────────┐
 │  4. IngestionAgent    │   Ranks camps by vulnerability + population
 └──────────┬───────────┘
            ▼
 ┌──────────────────────┐
 │  5. RoutingAgent      │   Allocates supplies via lowest-risk edges
 └──────────┬───────────┘
            ▼
 ┌──────────────────────┐
 │  6. SecurityAgent     │   PII scan + equity audit (pass 1)
 │     (1st pass)        │
 └──────────┬───────────┘
            ▼
 ┌──────────────────────┐
 │  7. GeoFormatting     │   Markdown report + GeoJSON
 │     Agent             │
 └──────────┬───────────┘
            ▼
 ┌──────────────────────┐
 │  8. SecurityAgent     │   Final PII + equity sweep (pass 2)
 │     (2nd pass)        │
 └──────────┬───────────┘
            ▼
      AgentState returned
      to Streamlit UI
```

---

## 📐 Scenario Schema

The system accepts scenario JSON validated by `ScenarioInput` (Pydantic v2). Key entities:

| Entity | Required Fields | Constraints |
|---|---|---|
| **Warehouse** | `id`, `name`, `lat`, `lon`, `inventory` | `inventory ≥ 0` |
| **Camp Block** | `id`, `name`, `lat`, `lon`, `population`, `vulnerability_score` | `population ≥ 0`, `vulnerability_score ∈ [0, 10]` |
| **Edge** | `source`, `target`, `base_travel_time_mins`, `monsoon_risk_multiplier` | `travel_time > 0`, `multiplier ≥ 1.0` |
| **Weather Alert** | `type`, `severity`, `expected_window_hours`, `summary` | `window_hours > 0` |

The default scenario (`scenario_data.json`) models the Cox's Bazar region with **2 warehouses, 5 camp blocks, 10 road edges, and 2 weather alerts**.

---

## 🎨 UI & Visual Design — "Storm & Sanctuary"

The Streamlit interface uses a custom CSS design system called **"Storm & Sanctuary"**, engineered for operational clarity in high-stakes humanitarian contexts.

| Design Element | Implementation |
|---|---|
| **Premium Typography** | *Outfit* (display headers, 800wt), *Inter* (body), *JetBrains Mono* (code/data) via Google Fonts |
| **Telemetry Header** | Pulsing teal dot (`@keyframes pulse`) signals active operational status |
| **Glassmorphic Sidebar** | Dark `#0F172A` control panel with dashed file-upload zone, teal primary buttons with hover transforms |
| **Metrics Dashboard** | CSS Grid of cards with left-accent borders (cyan/teal/green/red), hover lift animations, and formatted numeric values |
| **Interactive Folium Map** | CartoDB Positron tiles, colour-coded routes (green → dark red by risk), animated floating dot markers at destinations |
| **Antigravity Animation** | Floating 🚁 and 📦 emojis via CSS `@keyframes floatUp` + `sway` — triggered on successful orchestration (replaces `st.balloons()`) |
| **Report Cards** | White cards with subtle box shadows and bordered section headers |
| **Security Logs** | Amber/red background panels that expand automatically when violations are detected |

---

## 📂 Project Structure

```
├── .env.example             # Template for environment variables
├── .gitignore               # Standard Python + Streamlit exclusions
├── LICENSE                  # MIT License
├── README.md                # This file (project report / writeup)
├── requirements.txt         # Pinned Python dependencies
│
├── generate_scenario.py     # Builds the default Cox's Bazar scenario JSON
├── scenario_data.json       # Generated default scenario (2 WHs, 5 camps)
├── schema.py                # Pydantic v2 models: Route, AgentState, ScenarioInput
├── security.py              # Deterministic pre-processing: file gate, sanitize, validate
├── agents.py                # Gemini-backed agents with deterministic fallbacks
├── mcp_server.py            # MCP orchestrator — chains all agents in sequence
├── app.py                   # Streamlit UI: dashboard, Folium map, custom CSS
│
└── tests/
    ├── conftest.py          # Adds project root to sys.path for pytest
    └── test_fallbacks.py    # 22 unit tests covering all fallback + security logic
```

---

## 🚀 Setup & Installation

### Prerequisites

- **Python 3.10+**
- A **Google Gemini API key** (optional — the app runs fully offline with deterministic fallbacks)

### Steps

```bash
# 1. Clone the repository
git clone <repo-url>
cd <repo-directory>

# 2. Create and activate a virtual environment (recommended)
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env        # Linux / macOS
copy .env.example .env      # Windows
# Open .env and replace 'your_gemini_api_key_here' with your actual key

# 5. Run the application
streamlit run app.py
```

The app will open at **`http://localhost:8501`**.

### Running Without a Gemini API Key

The app works **fully offline** using deterministic fallback logic in each agent. All security layers, the Folium map, the metrics dashboard, and the Streamlit UI function identically — only the LLM-generated narrative will be replaced by a structured template report.

---

## 🗺️ How to Use

1. **Upload a custom scenario** — use the sidebar file uploader to load your own `.json` file (must match the `ScenarioInput` schema), or use the built-in Cox's Bazar default.
2. **Click ▶ Run Logistics Orchestration** — the MCP orchestrator runs the full 8-step agent pipeline.
3. **View the interactive map** — Folium renders colour-coded routes: **green** (low risk) → **amber** (medium) → **red** (high) → **dark red** (critical). Animated floating markers pulse at camp destinations.
4. **Review the metrics dashboard** — see routes planned, total kits allocated, security flag status, and GeoJSON feature count at a glance.
5. **Read the NGO report** — the GeoFormattingAgent's Markdown report appears in a styled card, written in an empathetic, operational tone.
6. **Inspect Security & Equity Logs** — expand the collapsible panel to review all PII findings, redaction actions, and equity audit results.
7. **Export the full AgentState** — the raw JSON state is available in a collapsible viewer for debugging or downstream integration.

---

## 🧪 Testing & Verification

The project includes **22 unit tests** covering all deterministic fallback paths, security checks, and edge cases.

```bash
# Run the full test suite
pytest tests/test_fallbacks.py -v

# Run with coverage (requires pytest-cov)
pytest tests/test_fallbacks.py -v --cov=. --cov-report=term-missing
```

### Test Coverage Areas

| Module | Tests | What's Covered |
|---|---|---|
| `security.py` | 7 | File-type gating, HTML stripping, whitespace collapsing, node-count validation (pass, no warehouses, no camps, too many camps) |
| `agents.redact_pii` | 6 | Refugee ID, email, phone redaction, node-ID preservation, nested dict handling, clean-text passthrough |
| `IngestionAgent` | 4 | List return, vulnerability-first sorting, required keys, numeric priority scores |
| `RoutingAgent` | 5 | Route object types, valid source/target IDs, non-negative supplies, inventory bounds, string-inventory edge case |
| `SecurityAgent` | 3 | Empty-route equity logging, equity violation detection, balanced-route clearance |

---

## 🧑‍💻 Dependencies

| Package | Version | Purpose |
|---|---|---|
| `streamlit` | ≥1.32.0 | Web UI framework with custom CSS injection |
| `folium` | 0.16.0 | Interactive Leaflet maps with animated markers |
| `streamlit-folium` | 0.19.0 | Embeds Folium maps inside Streamlit |
| `pydantic` | ≥2.6.4 | Data validation, schema enforcement, serialization |
| `google-generativeai` | 0.8.6 | Google Gemini LLM integration |
| `python-dotenv` | 1.0.1 | Loads `.env` API keys at startup |

---

## ⚖️ Ethical Considerations

- **No real PII is used.** All scenario data is entirely synthetic. Any simulated Refugee IDs exist solely to demonstrate the SecurityAgent's detection and redaction capabilities at runtime.
- **Equity auditing** is enforced at the system level — AI-generated routes that concentrate ≥90 % of supplies in a single camp are flagged as violations, and concentrations ≥65 % trigger warnings.
- **Human-in-the-loop:** This tool is designed to *assist* logistics coordinators, not replace them. All route plans require human review and confirmation before dispatch.
- **Transparency:** The full `AgentState` JSON — including all security logs, equity audit results, and redaction actions — is available for inspection in the UI.
- **Offline-first resilience:** The deterministic fallback design ensures the tool remains operational even without internet connectivity or API access — critical for field deployment in low-resource settings.

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

Copyright © 2026 Nafis Ul Aman Saadman

---

*Built for the Kaggle Five Days of AI Agents Capstone · June 2026*
