"""agents.py – Gemini-backed agents with deterministic fallbacks.

Improvements in this version
-----------------------------
* PII_PATTERNS[1] tightened – no longer matches warehouse/camp node IDs.
* GEMINI_MODEL validated at startup – warns if the value looks non-Gemini.
* _generate_json / _generate_text log a warning on parse failure so debugging
  a bad LLM response is no longer silent.
* IngestionAgent and RoutingAgent cross-reference LLM output IDs against the
  scenario before accepting them, preventing hallucinated node IDs from
  reaching the map or GeoJSON.
* RoutingAgent._fallback guards against non-numeric inventory values.
* redact_pii is no longer called inside each agent – a single pass now runs
  at the mcp_server level before any agent receives data.
* GeoFormattingAgent.build_geojson and build_report are public so callers
  can invoke them independently.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import re
from typing import Any

from schema import AgentState, Route

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv(*args: Any, **kwargs: Any) -> bool:
        return False

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover
    genai = None


load_dotenv()

logger = logging.getLogger(__name__)

# ── PII patterns ──────────────────────────────────────────────────────────────
# Pattern[0]: explicit "Refugee ID 1234" style references.
# Pattern[1]: tightened – requires 5+ digits to avoid matching node IDs like
#             WH-UKH-01 (2 digits) or CAMP-04 (2 digits).  The old \b[A-Z]{1,3}-?\d{4,}\b
#             would fire on anything with 4+ digits; this version requires 5+ to
#             reduce false positives on real node identifiers.
# Pattern[2]: email addresses.
# Pattern[3]: Bangladeshi mobile numbers (+88 prefix or bare 01x format).
PII_PATTERNS = [
    re.compile(r"\bRefugee\s+ID\s*[:#-]?\s*\d+\b", re.IGNORECASE),
    re.compile(r"\b[A-Z]{1,3}-?\d{5,}\b"),
    re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    re.compile(r"\b(?:\+?88)?01[3-9]\d{8}\b"),
]

# ── Gemini model name validation ──────────────────────────────────────────────
_GEMINI_PREFIX = "gemini"
_configured_model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
if not _configured_model.lower().startswith(_GEMINI_PREFIX):
    logger.warning(
        "GEMINI_MODEL is set to %r which does not look like a Gemini model name. "
        "Expected a value starting with 'gemini-'. The app will fall back to "
        "deterministic logic if the API call fails.",
        _configured_model,
    )


def redact_pii(value: Any) -> tuple[Any, bool]:
    """Recursively redact PII from strings, lists, and dicts.

    Returns the cleaned value and a boolean indicating whether any PII was found.
    """
    if isinstance(value, str):
        redacted = value
        found = False
        for pattern in PII_PATTERNS:
            redacted, count = pattern.subn("[REDACTED_PII]", redacted)
            found = found or count > 0
        return redacted, found

    if isinstance(value, list):
        changed = False
        items = []
        for item in value:
            redacted_item, item_changed = redact_pii(item)
            items.append(redacted_item)
            changed = changed or item_changed
        return items, changed

    if isinstance(value, dict):
        changed = False
        result = {}
        for key, item in value.items():
            redacted_item, item_changed = redact_pii(item)
            result[key] = redacted_item
            changed = changed or item_changed
        return result, changed

    return value, False


def _json_from_model_text(text: str) -> Any:
    """Extract JSON from a model response, stripping markdown fences if present."""
    cleaned = text.strip()
    fence_match = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL | re.IGNORECASE)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    return json.loads(cleaned)


# ── Base Gemini agent ─────────────────────────────────────────────────────────

class GeminiAgent:
    def __init__(self) -> None:
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

    def _model(self) -> Any | None:
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key or genai is None:
            return None
        genai.configure(api_key=api_key)
        return genai.GenerativeModel(self.model_name)

    def _generate_json(self, prompt: str) -> Any | None:
        """Call the model and parse JSON from the response.

        Returns None (and logs a warning) on any failure so callers can fall
        back to deterministic logic without crashing.
        """
        model = self._model()
        if model is None:
            return None
        try:
            response = model.generate_content(prompt)
            return _json_from_model_text(response.text)
        except json.JSONDecodeError as exc:
            logger.warning(
                "%s: failed to parse JSON from model response: %s",
                self.__class__.__name__,
                exc,
            )
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "%s: model call failed: %s",
                self.__class__.__name__,
                exc,
            )
            return None

    def _generate_text(self, prompt: str) -> str | None:
        """Call the model and return the raw text response.

        Returns None (and logs a warning) on any failure.
        """
        model = self._model()
        if model is None:
            return None
        try:
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "%s: model call failed: %s",
                self.__class__.__name__,
                exc,
            )
            return None


# ── Ingestion agent ───────────────────────────────────────────────────────────

class IngestionAgent(GeminiAgent):
    def run(self, raw_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Rank camp blocks by vulnerability + population demand.

        The LLM output is cross-referenced against the scenario's actual camp
        IDs – any hallucinated IDs are silently dropped and the fallback is used
        if no valid items remain.
        """
        valid_camp_ids = {
            camp["id"] for camp in raw_data.get("camp_blocks", [])
        }

        prompt = f"""
You are the Ingestion & Parser Agent for a humanitarian logistics MCP workflow.
Read the synthetic scenario JSON and return only a JSON array of camp priority objects.
Each object must contain: camp_id, camp_name, population, vulnerability_score,
priority_score, and reason. Rank highest priority first.

Scenario JSON:
{json.dumps(raw_data, indent=2)}
"""
        candidate = self._generate_json(prompt)
        if isinstance(candidate, list):
            normalized = []
            for item in candidate:
                if not isinstance(item, dict):
                    continue
                camp_id = item.get("camp_id")
                # Drop items whose camp_id doesn't exist in the scenario.
                if camp_id and camp_id in valid_camp_ids:
                    normalized.append(item)
                elif camp_id:
                    logger.warning(
                        "IngestionAgent: LLM returned unknown camp_id %r – dropping.",
                        camp_id,
                    )
            if normalized:
                return normalized

        return self._fallback(raw_data)

    def _fallback(self, raw_data: dict[str, Any]) -> list[dict[str, Any]]:
        camps = raw_data.get("camp_blocks", [])
        ranked = []
        for camp in camps:
            population = int(camp.get("population", 0))
            vulnerability = int(camp.get("vulnerability_score", 0))
            priority_score = round((vulnerability * 10) + (population / 2500), 2)
            ranked.append(
                {
                    "camp_id": camp.get("id"),
                    "camp_name": camp.get("name"),
                    "population": population,
                    "vulnerability_score": vulnerability,
                    "priority_score": priority_score,
                    "reason": "Ranked by vulnerability score with population as a demand tiebreaker.",
                }
            )
        return sorted(
            ranked,
            key=lambda item: (item["priority_score"], item["vulnerability_score"], item["population"]),
            reverse=True,
        )


# ── Routing agent ─────────────────────────────────────────────────────────────

class RoutingAgent(GeminiAgent):
    def run(self, raw_data: dict[str, Any], prioritized_camps: list[dict[str, Any]]) -> list[Route]:
        """Assign warehouse inventory to camps via lowest-risk edges.

        LLM output is validated by Pydantic (Route model) and cross-referenced
        against the scenario's actual warehouse and camp IDs before acceptance.
        """
        valid_warehouse_ids = {wh["id"] for wh in raw_data.get("warehouses", [])}
        valid_camp_ids = {camp["id"] for camp in raw_data.get("camp_blocks", [])}

        prompt = f"""
You are the Logistics & Routing Agent for a pre-monsoon aid operation.
Create an optimal route plan using the ranked camps, warehouse inventories, road edges,
base travel times, and monsoon risk multipliers. Prioritize high-risk camps while avoiding
unreasonable concentration of all supplies in one camp.

Return only a JSON array matching this schema:
[{{"source": "WAREHOUSE_ID", "target": "CAMP_ID", "supplies_allocated": 1000, "risk_level": "low|medium|high|critical"}}]

Scenario JSON:
{json.dumps(raw_data, indent=2)}

Ranked camps:
{json.dumps(prioritized_camps, indent=2)}
"""
        candidate = self._generate_json(prompt)
        if isinstance(candidate, list):
            routes: list[Route] = []
            for item in candidate:
                try:
                    route = Route.model_validate(item)
                except Exception:
                    continue
                # Cross-reference source and target against the scenario.
                if route.source not in valid_warehouse_ids:
                    logger.warning(
                        "RoutingAgent: LLM returned unknown warehouse source %r – dropping.",
                        route.source,
                    )
                    continue
                if route.target not in valid_camp_ids:
                    logger.warning(
                        "RoutingAgent: LLM returned unknown camp target %r – dropping.",
                        route.target,
                    )
                    continue
                routes.append(route)
            if routes:
                return routes

        return self._fallback(raw_data, prioritized_camps)

    def _fallback(self, raw_data: dict[str, Any], prioritized_camps: list[dict[str, Any]]) -> list[Route]:
        # Deep-copy warehouse dicts so we can decrement inventory safely without
        # mutating the original raw_data that other parts of the pipeline still
        # hold a reference to.
        warehouses: dict[str, dict[str, Any]] = {
            item["id"]: copy.deepcopy(item) for item in raw_data.get("warehouses", [])
        }
        edges = raw_data.get("edges", [])
        camp_lookup = {item["id"]: item for item in raw_data.get("camp_blocks", [])}
        routes: list[Route] = []

        for priority in prioritized_camps:
            camp_id = priority.get("camp_id")
            camp = camp_lookup.get(camp_id)
            if not camp:
                continue

            possible_edges = [edge for edge in edges if edge.get("target") == camp_id]
            possible_edges.sort(
                key=lambda edge: edge["base_travel_time_mins"] * edge["monsoon_risk_multiplier"]
            )

            selected_edge = None
            for edge in possible_edges:
                warehouse = warehouses.get(edge.get("source"))
                if warehouse:
                    # Guard: inventory may arrive as a string in custom scenarios;
                    # coerce to int so arithmetic never throws TypeError.
                    try:
                        inv = int(warehouse.get("inventory", 0))
                    except (TypeError, ValueError):
                        inv = 0
                    warehouse["inventory"] = inv  # normalise in-place
                    if inv > 0:
                        selected_edge = edge
                        break

            if selected_edge is None:
                continue

            warehouse = warehouses[selected_edge["source"]]
            vulnerability = int(camp.get("vulnerability_score", 1))
            population = int(camp.get("population", 0))
            requested = max(250, int(population * (0.04 + vulnerability * 0.006)))
            allocated = min(requested, int(warehouse["inventory"]))
            warehouse["inventory"] = int(warehouse["inventory"]) - allocated

            routes.append(
                Route(
                    source=selected_edge["source"],
                    target=camp_id,
                    supplies_allocated=allocated,
                    risk_level=self._risk_level(
                        float(selected_edge["monsoon_risk_multiplier"]), vulnerability
                    ),
                )
            )

        return routes

    @staticmethod
    def _risk_level(multiplier: float, vulnerability: int) -> str:
        score = multiplier + (vulnerability / 20)
        if score >= 2.15:
            return "critical"
        if score >= 1.85:
            return "high"
        if score >= 1.55:
            return "medium"
        return "low"


# ── Security agent ────────────────────────────────────────────────────────────

class SecurityAgent:
    def run(self, state: AgentState) -> AgentState:
        payload = state.model_dump()
        redacted_payload, found_pii = redact_pii(payload)
        logs = list(dict.fromkeys(redacted_payload.get("security_logs", [])))

        if found_pii:
            logs.append("PII detected and redacted from the final state payload.")

        equity_logs = self._equity_logs(state.final_routes)
        logs.extend(log for log in equity_logs if log not in logs)

        redacted_payload["security_flag"] = bool(found_pii or equity_logs or state.security_flag)
        redacted_payload["security_logs"] = logs
        return AgentState.model_validate(redacted_payload)

    @staticmethod
    def _equity_logs(routes: list[Route]) -> list[str]:
        if not routes:
            return ["No routes were generated, so equity checks could not be completed."]

        total_supplies = sum(route.supplies_allocated for route in routes)
        if total_supplies <= 0:
            return ["Generated routes allocate zero supplies, which violates the equity check."]

        logs = []
        for route in routes:
            share = route.supplies_allocated / total_supplies
            if share >= 0.9:
                logs.append(
                    f"Equity violation: {route.target} receives {share:.0%} of all allocated supplies."
                )
            elif share >= 0.65:
                logs.append(
                    f"Equity warning: {route.target} receives {share:.0%} of all allocated supplies."
                )
        return logs


# ── Geo-formatting agent ──────────────────────────────────────────────────────

class GeoFormattingAgent(GeminiAgent):
    def run(
        self,
        raw_data: dict[str, Any],
        routes: list[Route],
        prioritized_camps: list[dict[str, Any]],
        security_flag: bool,
        security_logs: list[str],
    ) -> tuple[str, dict[str, Any]]:
        """Build the Markdown report and GeoJSON FeatureCollection.

        Both helpers are exposed as public methods so callers can invoke them
        independently (e.g. for testing).
        """
        geojson = self.build_geojson(raw_data, routes)
        report = self.build_report(raw_data, routes, prioritized_camps, security_flag, security_logs)
        return report, geojson

    def build_report(
        self,
        raw_data: dict[str, Any],
        routes: list[Route],
        prioritized_camps: list[dict[str, Any]],
        security_flag: bool,
        security_logs: list[str],
    ) -> str:
        """Generate the NGO Markdown report via Gemini, with a deterministic fallback."""
        # redact_pii is called here only on the report-specific payload that is
        # sent to the LLM – the main pipeline redaction already happened upstream.
        safe_payload, _ = redact_pii(
            {
                "scenario": raw_data.get("scenario_name"),
                "routes": [route.model_dump() for route in routes],
                "prioritized_camps": prioritized_camps,
                "security_flag": security_flag,
                "security_logs": security_logs,
            }
        )
        prompt = f"""
You are the Geo-Formatting Agent. Write a concise Markdown report for NGO logistics workers.
Use an empathetic, operational tone. Do not include personally identifiable information.
Mention security/equity checks when relevant.

Secure workflow payload:
{json.dumps(safe_payload, indent=2)}
"""
        generated = self._generate_text(prompt)
        if generated:
            redacted_report, _ = redact_pii(generated)
            return redacted_report

        return self._fallback_report(routes, prioritized_camps, security_flag)

    def build_geojson(self, raw_data: dict[str, Any], routes: list[Route]) -> dict[str, Any]:
        """Build a GeoJSON FeatureCollection from routes.

        Routes whose source or target IDs don't match any node in the scenario
        are silently skipped (they should have been filtered by RoutingAgent).
        """
        nodes = {
            item["id"]: item
            for collection_name in ("warehouses", "camp_blocks")
            for item in raw_data.get(collection_name, [])
        }
        features = []
        for route in routes:
            source = nodes.get(route.source)
            target = nodes.get(route.target)
            if not source or not target:
                logger.warning(
                    "GeoFormattingAgent: route %s→%s references unknown node(s) – skipping.",
                    route.source,
                    route.target,
                )
                continue
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "source": route.source,
                        "target": route.target,
                        "supplies_allocated": route.supplies_allocated,
                        "risk_level": route.risk_level,
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [
                            [source["lon"], source["lat"]],
                            [target["lon"], target["lat"]],
                        ],
                    },
                }
            )
        return {"type": "FeatureCollection", "features": features}

    # ── private ───────────────────────────────────────────────────────────────

    @staticmethod
    def _fallback_report(
        routes: list[Route],
        prioritized_camps: list[dict[str, Any]],
        security_flag: bool,
    ) -> str:
        route_lines = [
            f"- {r.source} to {r.target}: {r.supplies_allocated:,} kits, "
            f"{r.risk_level} monsoon routing risk."
            for r in routes
        ]
        top_camp = prioritized_camps[0]["camp_name"] if prioritized_camps else "the highest-risk camp"
        security_note = (
            "Security review flagged and redacted sensitive identifiers before final output."
            if security_flag
            else "Security review found no sensitive identifiers in the final output."
        )
        return "\n".join(
            [
                "### Logistics Orchestration Report",
                "",
                f"The workflow prioritizes {top_camp} while preserving coverage across all camp blocks.",
                security_note,
                "",
                "**Recommended Routes**",
                *route_lines,
                "",
                "**Operational Note**",
                "Pre-monsoon multipliers increase travel uncertainty, so teams should confirm "
                "road access before dispatch and keep a reserve vehicle available for rerouting.",
            ]
        )
