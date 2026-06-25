"""tests/test_fallbacks.py – Unit tests for deterministic fallback logic.

Run with:
    pytest tests/test_fallbacks.py -v

These tests cover the paths that execute when no Gemini API key is present,
which is also the most critical code path for reliability in production.
"""
from __future__ import annotations

import pytest

from agents import (
    IngestionAgent,
    RoutingAgent,
    SecurityAgent,
    redact_pii,
)
from schema import AgentState, Route
from security import is_allowed_file, sanitize_json_text, validate_node_count


# ── Fixtures ──────────────────────────────────────────────────────────────────

MINIMAL_SCENARIO = {
    "warehouses": [
        {"id": "WH-01", "name": "Test Warehouse", "lat": 21.0, "lon": 92.0, "inventory": 1000},
    ],
    "camp_blocks": [
        {"id": "CAMP-01", "name": "Test Camp A", "lat": 21.1, "lon": 92.1,
         "population": 5000, "vulnerability_score": 7},
        {"id": "CAMP-02", "name": "Test Camp B", "lat": 21.2, "lon": 92.2,
         "population": 3000, "vulnerability_score": 4},
    ],
    "edges": [
        {"source": "WH-01", "target": "CAMP-01", "base_travel_time_mins": 20,
         "monsoon_risk_multiplier": 1.4},
        {"source": "WH-01", "target": "CAMP-02", "base_travel_time_mins": 30,
         "monsoon_risk_multiplier": 1.2},
    ],
    "weather_alerts": [],
}


# ── security.py ───────────────────────────────────────────────────────────────

class TestIsAllowedFile:
    def test_json_accepted(self):
        assert is_allowed_file("scenario.json") is True

    def test_json_uppercase_accepted(self):
        assert is_allowed_file("SCENARIO.JSON") is True

    def test_csv_rejected(self):
        assert is_allowed_file("data.csv") is False

    def test_no_extension_rejected(self):
        assert is_allowed_file("scenario") is False

    def test_path_traversal_json_accepted(self):
        # Extension check only; path content is irrelevant
        assert is_allowed_file("../../etc/passwd.json") is True


class TestSanitizeJsonText:
    def test_strips_script_tags(self):
        dirty = '{"name": "<script>alert(1)</script>test"}'
        clean = sanitize_json_text(dirty)
        assert "<script>" not in clean
        assert "test" in clean

    def test_collapses_whitespace(self):
        text = "hello   world"
        assert sanitize_json_text(text) == "hello world"

    def test_passthrough_clean_text(self):
        text = '{"key": "value"}'
        assert sanitize_json_text(text) == text


class TestValidateNodeCount:
    def test_valid_scenario_passes(self):
        validate_node_count(MINIMAL_SCENARIO)  # should not raise

    def test_no_warehouses_raises(self):
        with pytest.raises(ValueError, match="warehouse"):
            validate_node_count({"warehouses": [], "camp_blocks": [{"id": "C1"}]})

    def test_no_camps_raises(self):
        with pytest.raises(ValueError, match="camp"):
            validate_node_count({"warehouses": [{"id": "W1"}], "camp_blocks": []})

    def test_too_many_camps_raises(self):
        camps = [{"id": f"C{i}"} for i in range(31)]
        with pytest.raises(ValueError, match="Node count"):
            validate_node_count({"warehouses": [{"id": "W1"}], "camp_blocks": camps})


# ── agents.redact_pii ─────────────────────────────────────────────────────────

class TestRedactPii:
    def test_refugee_id_redacted(self):
        text = "Reported by: Refugee ID 9932"
        result, found = redact_pii(text)
        assert found is True
        assert "9932" not in result
        assert "[REDACTED_PII]" in result

    def test_email_redacted(self):
        text = "Contact: aid.worker@ngo.org"
        result, found = redact_pii(text)
        assert found is True
        assert "aid.worker@ngo.org" not in result

    def test_bangladeshi_phone_redacted(self):
        text = "Call: 01712345678"
        result, found = redact_pii(text)
        assert found is True

    def test_node_ids_not_redacted(self):
        # Warehouse and camp IDs must NOT be treated as PII
        text = "Route WH-UKH-01 to CAMP-08W"
        result, found = redact_pii(text)
        assert found is False
        assert "WH-UKH-01" in result
        assert "CAMP-08W" in result

    def test_clean_text_unchanged(self):
        text = "No PII here."
        result, found = redact_pii(text)
        assert found is False
        assert result == text

    def test_nested_dict_redacted(self):
        data = {"notes": "Refugee ID 1234", "name": "Camp A"}
        result, found = redact_pii(data)
        assert found is True
        assert "1234" not in result["notes"]
        assert result["name"] == "Camp A"


# ── IngestionAgent fallback ───────────────────────────────────────────────────

class TestIngestionAgentFallback:
    def setup_method(self):
        self.agent = IngestionAgent()

    def test_returns_list(self):
        result = self.agent._fallback(MINIMAL_SCENARIO)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_sorted_highest_vulnerability_first(self):
        result = self.agent._fallback(MINIMAL_SCENARIO)
        assert result[0]["camp_id"] == "CAMP-01"  # vulnerability 7 > 4

    def test_required_keys_present(self):
        result = self.agent._fallback(MINIMAL_SCENARIO)
        for item in result:
            for key in ("camp_id", "camp_name", "population", "vulnerability_score",
                        "priority_score", "reason"):
                assert key in item, f"Missing key: {key}"

    def test_priority_score_numeric(self):
        result = self.agent._fallback(MINIMAL_SCENARIO)
        for item in result:
            assert isinstance(item["priority_score"], (int, float))


# ── RoutingAgent fallback ─────────────────────────────────────────────────────

class TestRoutingAgentFallback:
    def setup_method(self):
        self.agent = RoutingAgent()
        self.ingestion = IngestionAgent()

    def test_returns_route_objects(self):
        camps = self.ingestion._fallback(MINIMAL_SCENARIO)
        routes = self.agent._fallback(MINIMAL_SCENARIO, camps)
        assert all(isinstance(r, Route) for r in routes)

    def test_sources_exist_in_scenario(self):
        valid_ids = {wh["id"] for wh in MINIMAL_SCENARIO["warehouses"]}
        camps = self.ingestion._fallback(MINIMAL_SCENARIO)
        routes = self.agent._fallback(MINIMAL_SCENARIO, camps)
        for r in routes:
            assert r.source in valid_ids

    def test_targets_exist_in_scenario(self):
        valid_ids = {c["id"] for c in MINIMAL_SCENARIO["camp_blocks"]}
        camps = self.ingestion._fallback(MINIMAL_SCENARIO)
        routes = self.agent._fallback(MINIMAL_SCENARIO, camps)
        for r in routes:
            assert r.target in valid_ids

    def test_supplies_non_negative(self):
        camps = self.ingestion._fallback(MINIMAL_SCENARIO)
        routes = self.agent._fallback(MINIMAL_SCENARIO, camps)
        for r in routes:
            assert r.supplies_allocated >= 0

    def test_inventory_does_not_go_negative(self):
        # Inventory should be fully consumed but never negative
        camps = self.ingestion._fallback(MINIMAL_SCENARIO)
        routes = self.agent._fallback(MINIMAL_SCENARIO, camps)
        total_allocated = sum(r.supplies_allocated for r in routes)
        total_inventory = sum(wh["inventory"] for wh in MINIMAL_SCENARIO["warehouses"])
        assert total_allocated <= total_inventory

    def test_string_inventory_handled(self):
        # Non-numeric inventory values should not crash the fallback
        scenario = {
            **MINIMAL_SCENARIO,
            "warehouses": [
                {"id": "WH-01", "name": "W", "lat": 21.0, "lon": 92.0, "inventory": "500"},
            ],
        }
        camps = self.ingestion._fallback(scenario)
        routes = self.agent._fallback(scenario, camps)
        assert isinstance(routes, list)


# ── SecurityAgent ─────────────────────────────────────────────────────────────

class TestSecurityAgent:
    def setup_method(self):
        self.agent = SecurityAgent()

    def _make_state(self, routes=None, logs=None):
        return AgentState(
            raw_data=MINIMAL_SCENARIO,
            final_routes=routes or [],
            security_logs=logs or [],
        )

    def test_no_routes_equity_log(self):
        state = self._make_state()
        result = self.agent.run(state)
        assert result.security_flag is True
        assert any("equity" in log.lower() for log in result.security_logs)

    def test_equity_violation_flagged(self):
        routes = [Route(source="WH-01", target="CAMP-01",
                        supplies_allocated=990, risk_level="high"),
                  Route(source="WH-01", target="CAMP-02",
                        supplies_allocated=10, risk_level="low")]
        state = self._make_state(routes=routes)
        result = self.agent.run(state)
        assert result.security_flag is True
        assert any("violation" in log.lower() for log in result.security_logs)

    def test_balanced_routes_no_flag(self):
        routes = [Route(source="WH-01", target="CAMP-01",
                        supplies_allocated=500, risk_level="medium"),
                  Route(source="WH-01", target="CAMP-02",
                        supplies_allocated=500, risk_level="low")]
        state = self._make_state(routes=routes)
        result = self.agent.run(state)
        assert result.security_flag is False
