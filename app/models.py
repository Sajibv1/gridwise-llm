from __future__ import annotations

from enum import Enum
from math import isfinite
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DirectiveType(str, Enum):
    SOLAR_REDUCTION = "solar_reduction"
    MINIMUM_BATTERY_RESERVE = "minimum_battery_reserve"
    NO_CHARGE_WINDOW = "no_charge_window"
    NO_DISCHARGE_WINDOW = "no_discharge_window"
    MAX_GRID_WINDOW = "max_grid_window"
    NO_OP = "no_op"


class BatteryAction(str, Enum):
    CHARGE = "charge"
    DISCHARGE = "discharge"
    IDLE = "idle"


class HoursAdjustment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hours: list[int]


class SolarReductionAdjustment(HoursAdjustment):
    factor: float


class MinimumBatteryReserveAdjustment(HoursAdjustment):
    minimum_energy_kwh: float


class MaxGridWindowAdjustment(HoursAdjustment):
    max_grid_kwh: float


DirectiveAdjustment = (
    SolarReductionAdjustment
    | MinimumBatteryReserveAdjustment
    | MaxGridWindowAdjustment
    | HoursAdjustment
)


class HourInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hour: int = Field(ge=0, le=23)
    demand_kwh: float = Field(ge=0)
    solar_kwh: float = Field(ge=0)
    tariff_bdt_per_kwh: float = Field(ge=0)

    @field_validator("demand_kwh", "solar_kwh", "tariff_bdt_per_kwh")
    @classmethod
    def finite_number(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("must be finite")
        return value


class BatteryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capacity_kwh: float = Field(gt=0)
    initial_energy_kwh: float = Field(ge=0)
    minimum_energy_kwh: float = Field(ge=0)
    max_charge_kwh_per_hour: float = Field(ge=0)
    max_discharge_kwh_per_hour: float = Field(ge=0)

    @field_validator(
        "capacity_kwh",
        "initial_energy_kwh",
        "minimum_energy_kwh",
        "max_charge_kwh_per_hour",
        "max_discharge_kwh_per_hour",
    )
    @classmethod
    def finite_number(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("must be finite")
        return value

    @model_validator(mode="after")
    def validate_bounds(self) -> BatteryInput:
        if self.initial_energy_kwh > self.capacity_kwh:
            raise ValueError("initial_energy_kwh cannot exceed capacity_kwh")
        if self.minimum_energy_kwh > self.capacity_kwh:
            raise ValueError("minimum_energy_kwh cannot exceed capacity_kwh")
        return self


class OptimizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(min_length=1, max_length=200)
    operator_notes: list[str] = Field(min_length=1, max_length=3)
    hours: list[HourInput] = Field(min_length=24, max_length=24)
    battery: BatteryInput

    @field_validator("scenario_id")
    @classmethod
    def non_blank_scenario_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("operator_notes")
    @classmethod
    def non_blank_notes(cls, notes: list[str]) -> list[str]:
        normalized = [note.strip() for note in notes]
        if any(not note for note in normalized):
            raise ValueError("operator_notes must contain non-empty strings")
        return normalized

    @model_validator(mode="after")
    def validate_24_hour_horizon(self) -> OptimizationRequest:
        observed = [entry.hour for entry in self.hours]
        if sorted(observed) != list(range(24)):
            raise ValueError("hours must contain each integer from 0 through 23 exactly once")
        self.hours.sort(key=lambda entry: entry.hour)
        return self


class LLMDirectiveCandidate(BaseModel):
    """The intentionally narrow schema accepted from the model provider."""

    model_config = ConfigDict(extra="forbid")

    note_index: int
    applies: bool
    directive_type: DirectiveType
    # Explicit object alternatives keep strict JSON-schema output closed to unknown keys.
    # The directive type-to-shape relation is still checked independently in directives.py.
    structured_adjustment: DirectiveAdjustment | None
    explanation: str = Field(min_length=1, max_length=500)


class LLMInterpretationBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    directives: list[LLMDirectiveCandidate] = Field(min_length=1, max_length=3)


class DirectiveInterpretation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note_index: int = Field(ge=0, le=2)
    applies: bool
    directive_type: DirectiveType
    structured_adjustment: dict[str, Any] | None
    explanation: str


class HourlyPlanEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hour: int = Field(ge=0, le=23)
    grid_kwh: float = Field(ge=0)
    solar_used_kwh: float = Field(ge=0)
    battery_action: BatteryAction
    battery_kwh: float = Field(ge=0)
    battery_energy_after_kwh: float = Field(ge=0)


class OptimizationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    directive_interpretation: list[DirectiveInterpretation]
    hourly_plan: list[HourlyPlanEntry] = Field(min_length=24, max_length=24)
    total_grid_kwh: float = Field(ge=0)
    total_cost_bdt: float = Field(ge=0)
    peak_grid_kwh: float = Field(ge=0)
    plan_summary: str


class ErrorResponse(BaseModel):
    detail: str
