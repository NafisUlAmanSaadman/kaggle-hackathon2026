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

