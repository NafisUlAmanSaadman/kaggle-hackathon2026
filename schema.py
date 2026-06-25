from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class Route(BaseModel):
    source: str
    target: str
    supplies_allocated: int = Field(ge=0)
    risk_level: str

    @field_validator("risk_level")
    @classmethod
    def normalize_risk_level(cls, value: str) -> str:
        normalized = value.strip().lower()
        allowed = {"low", "medium", "high", "critical"}
        if normalized not in allowed:
            raise ValueError(f"risk_level must be one of {sorted(allowed)}")
        return normalized


class AgentState(BaseModel):
    raw_data: dict[str, Any]
    prioritized_camps: list[dict[str, Any]] = Field(default_factory=list)
    final_routes: list[Route] = Field(default_factory=list)
    security_flag: bool = False
    security_logs: list[str] = Field(default_factory=list)
    markdown_report: str = ""
    geojson: dict[str, Any] = Field(default_factory=dict)


# ── Scenario input schema ─────────────────────────────────────────────────────
# Used to validate uploaded (and default) scenario JSON before it reaches any
# agent.  Fields beyond those listed here are allowed (extra="allow") so that
# custom scenarios can carry additional metadata without failing validation.

class WarehouseNode(BaseModel):
    model_config = {"extra": "allow"}

    id: str
    name: str
    lat: float
    lon: float
    inventory: int = Field(ge=0, description="Available supply kits.")


class CampNode(BaseModel):
    model_config = {"extra": "allow"}

    id: str
    name: str
    lat: float
    lon: float
    population: int = Field(ge=0)
    vulnerability_score: int = Field(ge=0, le=10)


class Edge(BaseModel):
    model_config = {"extra": "allow"}

    source: str = Field(description="Warehouse ID.")
    target: str = Field(description="Camp ID.")
    base_travel_time_mins: float = Field(gt=0)
    monsoon_risk_multiplier: float = Field(ge=1.0)


class WeatherAlert(BaseModel):
    model_config = {"extra": "allow"}

    type: str
    severity: str
    expected_window_hours: float = Field(gt=0)
    summary: str


class ScenarioInput(BaseModel):
    """Pydantic model for the full scenario JSON.

    Raises ``ValidationError`` (which callers convert to ``ValueError``) if
    required fields are missing or contain invalid values.
    """

    model_config = {"extra": "allow"}

    warehouses: list[WarehouseNode] = Field(min_length=1)
    camp_blocks: list[CampNode] = Field(min_length=1)
    edges: list[Edge] = Field(default_factory=list)
    weather_alerts: list[WeatherAlert] = Field(default_factory=list)

    # Optional metadata — present in the default scenario but not required.
    scenario_name: str = "Unnamed Scenario"
    region: str = ""
    generated_for: str = ""

    def to_raw_dict(self) -> dict[str, Any]:
        """Return a plain dict with lists serialised as plain dicts (no Pydantic wrappers)."""
        return self.model_dump()
