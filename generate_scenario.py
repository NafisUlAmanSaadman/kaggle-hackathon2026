from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_OUTPUT_PATH = Path(__file__).with_name("scenario_data.json")


def build_scenario() -> dict[str, Any]:
    return {
        "scenario_name": "Cox's Bazar Pre-Monsoon Logistics Drill",
        "generated_for": "Kaggle Five Days of AI Agents Capstone",
        "region": "Cox's Bazar, Bangladesh",
        "warehouses": [
            {
                "id": "WH-UKH-01",
                "name": "Ukhia Central Warehouse",
                "lat": 21.1885,
                "lon": 92.1542,
                "inventory": 5200,
            },
            {
                "id": "WH-KTP-02",
                "name": "Kutupalong Forward Hub",
                "lat": 21.2136,
                "lon": 92.1324,
                "inventory": 4300,
            },
        ],
        "camp_blocks": [
            {
                "id": "CAMP-04",
                "name": "Camp 4 Block B",
                "lat": 21.2012,
                "lon": 92.1628,
                "population": 18400,
                "vulnerability_score": 8,
                "notes": "Low-lying shelters near drainage channels. Reported by: Refugee ID 9932",
            },
            {
                "id": "CAMP-08W",
                "name": "Camp 8W Block D",
                "lat": 21.1706,
                "lon": 92.1481,
                "population": 22900,
                "vulnerability_score": 9,
                "notes": "High landslide exposure and limited road redundancy.",
            },
            {
                "id": "CAMP-10",
                "name": "Camp 10 Block A",
                "lat": 21.1548,
                "lon": 92.1596,
                "population": 15600,
                "vulnerability_score": 6,
                "notes": "Bridge approach softens during heavy rainfall.",
            },
            {
                "id": "CAMP-13",
                "name": "Camp 13 Block C",
                "lat": 21.1352,
                "lon": 92.1392,
                "population": 20100,
                "vulnerability_score": 7,
                "notes": "Large child population and flood-prone access lanes.",
            },
            {
                "id": "CAMP-17",
                "name": "Camp 17 Block E",
                "lat": 21.1183,
                "lon": 92.1717,
                "population": 12800,
                "vulnerability_score": 5,
                "notes": "Secondary route available but longer.",
            },
        ],
        "edges": [
            {
                "source": "WH-UKH-01",
                "target": "CAMP-04",
                "base_travel_time_mins": 22,
                "monsoon_risk_multiplier": 1.35,
            },
            {
                "source": "WH-UKH-01",
                "target": "CAMP-08W",
                "base_travel_time_mins": 34,
                "monsoon_risk_multiplier": 1.75,
            },
            {
                "source": "WH-UKH-01",
                "target": "CAMP-10",
                "base_travel_time_mins": 38,
                "monsoon_risk_multiplier": 1.42,
            },
            {
                "source": "WH-UKH-01",
                "target": "CAMP-13",
                "base_travel_time_mins": 47,
                "monsoon_risk_multiplier": 1.55,
            },
            {
                "source": "WH-UKH-01",
                "target": "CAMP-17",
                "base_travel_time_mins": 52,
                "monsoon_risk_multiplier": 1.28,
            },
            {
                "source": "WH-KTP-02",
                "target": "CAMP-04",
                "base_travel_time_mins": 18,
                "monsoon_risk_multiplier": 1.22,
            },
            {
                "source": "WH-KTP-02",
                "target": "CAMP-08W",
                "base_travel_time_mins": 29,
                "monsoon_risk_multiplier": 1.68,
            },
            {
                "source": "WH-KTP-02",
                "target": "CAMP-10",
                "base_travel_time_mins": 36,
                "monsoon_risk_multiplier": 1.5,
            },
            {
                "source": "WH-KTP-02",
                "target": "CAMP-13",
                "base_travel_time_mins": 44,
                "monsoon_risk_multiplier": 1.62,
            },
            {
                "source": "WH-KTP-02",
                "target": "CAMP-17",
                "base_travel_time_mins": 57,
                "monsoon_risk_multiplier": 1.33,
            },
        ],
        "weather_alerts": [
            {
                "type": "heavy_rainfall",
                "severity": "orange",
                "expected_window_hours": 72,
                "summary": "Sustained pre-monsoon rainfall likely to reduce road reliability.",
            },
            {
                "type": "landslide_watch",
                "severity": "yellow",
                "expected_window_hours": 96,
                "summary": "Steep camp access paths may require smaller vehicle loads.",
            },
        ],
    }


def generate_scenario(output_path: str | Path = DEFAULT_OUTPUT_PATH) -> dict[str, Any]:
    scenario = build_scenario()
    path = Path(output_path)
    path.write_text(json.dumps(scenario, indent=2), encoding="utf-8")
    return scenario


if __name__ == "__main__":
    destination = DEFAULT_OUTPUT_PATH
    generate_scenario(destination)
    print(f"Wrote synthetic scenario to {destination}")

