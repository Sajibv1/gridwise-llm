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

    hours: list[int] = Field(
        description="Affected 24-hour clock indices, in ascending order. Windows are start-inclusive and end-exclusive."
    )


class SolarReductionAdjustment(HoursAdjustment):
    factor: float = Field(
        description="Usable solar fraction remaining after the reduction. For example, an 80% reduction is 0.2."
    )


class MinimumBatteryReserveAdjustment(HoursAdjustment):
    minimum_energy_kwh: float = Field(
        description="Minimum battery energy that must remain after each affected hour, in kWh."
    )


class MaxGridWindowAdjustment(HoursAdjustment):
    max_grid_kwh: float = Field(
        description="Maximum permitted grid energy in each affected hour, in kWh."
    )


DirectiveAdjustment = (
    SolarReductionAdjustment
    | MinimumBatteryReserveAdjustment
    | MaxGridWindowAdjustment
    | HoursAdjustment
)


class HourInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hour: int = Field(ge=0, le=23, description="Hour index on a 24-hour clock, from 0 through 23.")
    demand_kwh: float = Field(ge=0, description="Campus energy demand for this hour, in kWh.")
    solar_kwh: float = Field(
        ge=0, description="Forecast solar generation before operator-note adjustments, in kWh."
    )
    tariff_bdt_per_kwh: float = Field(
        ge=0, description="Grid tariff for this hour, in BDT per kWh."
    )

    @field_validator("demand_kwh", "solar_kwh", "tariff_bdt_per_kwh")
    @classmethod
    def finite_number(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("must be finite")
        return value


class BatteryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capacity_kwh: float = Field(gt=0, description="Usable battery capacity, in kWh.")
    initial_energy_kwh: float = Field(ge=0, description="Battery energy at hour 0, in kWh.")
    minimum_energy_kwh: float = Field(
        ge=0, description="Baseline battery reserve required at all hours, in kWh."
    )
    max_charge_kwh_per_hour: float = Field(
        ge=0, description="Maximum grid/solar energy that may charge the battery per hour, in kWh."
    )
    max_discharge_kwh_per_hour: float = Field(
        ge=0, description="Maximum energy the battery may supply per hour, in kWh."
    )

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

    scenario_id: str = Field(
        min_length=1,
        max_length=200,
        description="Caller-defined identifier echoed unchanged in the response.",
    )
    operator_notes: list[str] = Field(
        min_length=1,
        max_length=3,
        description="One to three untrusted natural-language notes for LLM interpretation. Unrelated notes become no_op.",
    )
    hours: list[HourInput] = Field(
        min_length=24,
        max_length=24,
        description="Exactly one entry for every hour 0 through 23; order is normalized by the service.",
    )
    battery: BatteryInput = Field(
        description="Physical battery limits and starting energy for the 24-hour horizon."
    )

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

    note_index: int = Field(ge=0, le=2, description="Zero-based index into operator_notes.")
    applies: bool = Field(description="Whether this note produced a valid operational directive.")
    directive_type: DirectiveType = Field(
        description="The only allowed directive category identified by the LLM."
    )
    structured_adjustment: dict[str, Any] | None = Field(
        description="Validated directive parameters. It is null only for no_op."
    )
    explanation: str = Field(
        description="Brief safe explanation of the interpretation; not used by the optimizer."
    )


class HourlyPlanEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hour: int = Field(ge=0, le=23, description="Hour index on the 24-hour clock.")
    grid_kwh: float = Field(ge=0, description="Grid energy drawn during this hour, in kWh.")
    solar_used_kwh: float = Field(
        ge=0, description="Effective solar energy used during this hour, in kWh."
    )
    battery_action: BatteryAction = Field(
        description="Whether the battery charges, discharges, or remains idle."
    )
    battery_kwh: float = Field(
        ge=0, description="Energy charged to or discharged from the battery, in kWh."
    )
    battery_energy_after_kwh: float = Field(
        ge=0, description="Battery state of charge after this hour, in kWh."
    )


class OptimizationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(description="Echo of the request scenario_id.")
    directive_interpretation: list[DirectiveInterpretation] = Field(
        description="Exactly one validated interpretation entry for each submitted operator note, in note_index order."
    )
    hourly_plan: list[HourlyPlanEntry] = Field(
        min_length=24,
        max_length=24,
        description="Feasible least-cost 24-hour plan, independently replay-validated before return.",
    )
    total_grid_kwh: float = Field(ge=0, description="Total 24-hour grid energy drawn, in kWh.")
    total_cost_bdt: float = Field(ge=0, description="Total 24-hour grid cost, in BDT.")
    peak_grid_kwh: float = Field(ge=0, description="Largest single-hour grid draw, in kWh.")
    plan_summary: str = Field(
        description="Human-readable summary; machine validation should use the structured fields."
    )


class ErrorResponse(BaseModel):
    detail: str = Field(
        description="Safe, client-visible error explanation. Provider internals and secrets are never returned."
    )
