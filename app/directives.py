from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Any

from pydantic import BaseModel

from app.models import (
    DirectiveInterpretation,
    DirectiveType,
    LLMDirectiveCandidate,
    OptimizationRequest,
)


class DirectiveValidationError(ValueError):
    """Raised when a model output is structurally plausible but semantically unsafe."""


@dataclass(frozen=True)
class EffectiveConstraints:
    """All operator directives reduced to deterministic, optimizer-ready constraints."""

    solar_factor: tuple[float, ...]
    minimum_reserve: tuple[float, ...]
    charge_forbidden: frozenset[int] = field(default_factory=frozenset)
    discharge_forbidden: frozenset[int] = field(default_factory=frozenset)
    max_grid: tuple[float | None, ...] = field(default_factory=lambda: (None,) * 24)


def _numeric(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DirectiveValidationError(f"{field_name} must be a finite number")
    number = float(value)
    if not isfinite(number):
        raise DirectiveValidationError(f"{field_name} must be finite")
    return number


def _hours(adjustment: dict[str, Any]) -> list[int]:
    values = adjustment.get("hours")
    if not isinstance(values, list) or not values:
        raise DirectiveValidationError("hours must be a non-empty array")
    if any(isinstance(hour, bool) or not isinstance(hour, int) for hour in values):
        raise DirectiveValidationError("hours must contain integers")
    if values != sorted(set(values)) or any(hour < 0 or hour > 23 for hour in values):
        raise DirectiveValidationError(
            "hours must be unique integers from 0 through 23 in ascending order"
        )
    return values


def _exact_keys(adjustment: dict[str, Any], expected: set[str]) -> None:
    if set(adjustment) != expected:
        raise DirectiveValidationError(
            f"structured_adjustment must contain exactly: {', '.join(sorted(expected))}"
        )


def _validate_candidate(
    candidate: LLMDirectiveCandidate, request: OptimizationRequest
) -> DirectiveInterpretation:
    if candidate.note_index < 0 or candidate.note_index >= len(request.operator_notes):
        raise DirectiveValidationError("note_index does not refer to an operator note")

    directive_type = candidate.directive_type
    adjustment = candidate.structured_adjustment
    if isinstance(adjustment, BaseModel):
        adjustment = adjustment.model_dump()

    if directive_type is DirectiveType.NO_OP:
        if candidate.applies or adjustment is not None:
            raise DirectiveValidationError(
                "no_op requires applies=false and structured_adjustment=null"
            )
        return DirectiveInterpretation(**candidate.model_dump())

    if not candidate.applies or not isinstance(adjustment, dict):
        raise DirectiveValidationError(
            "applicable directives require applies=true and an adjustment object"
        )

    normalized: dict[str, Any]
    if directive_type is DirectiveType.SOLAR_REDUCTION:
        _exact_keys(adjustment, {"hours", "factor"})
        factor = _numeric(adjustment["factor"], "factor")
        if not 0 <= factor <= 1:
            raise DirectiveValidationError("solar factor must be between 0 and 1")
        normalized = {"hours": _hours(adjustment), "factor": factor}
    elif directive_type is DirectiveType.MINIMUM_BATTERY_RESERVE:
        _exact_keys(adjustment, {"hours", "minimum_energy_kwh"})
        reserve = _numeric(adjustment["minimum_energy_kwh"], "minimum_energy_kwh")
        if not 0 <= reserve <= request.battery.capacity_kwh:
            raise DirectiveValidationError("battery reserve must be between 0 and capacity_kwh")
        normalized = {"hours": _hours(adjustment), "minimum_energy_kwh": reserve}
    elif directive_type in {DirectiveType.NO_CHARGE_WINDOW, DirectiveType.NO_DISCHARGE_WINDOW}:
        _exact_keys(adjustment, {"hours"})
        normalized = {"hours": _hours(adjustment)}
    elif directive_type is DirectiveType.MAX_GRID_WINDOW:
        _exact_keys(adjustment, {"hours", "max_grid_kwh"})
        grid_limit = _numeric(adjustment["max_grid_kwh"], "max_grid_kwh")
        if grid_limit < 0:
            raise DirectiveValidationError("max_grid_kwh must be non-negative")
        normalized = {"hours": _hours(adjustment), "max_grid_kwh": grid_limit}
    else:
        raise DirectiveValidationError("unsupported directive type")

    return DirectiveInterpretation(
        note_index=candidate.note_index,
        applies=True,
        directive_type=directive_type,
        structured_adjustment=normalized,
        explanation=candidate.explanation.strip(),
    )


def validate_interpretations(
    candidates: list[LLMDirectiveCandidate], request: OptimizationRequest
) -> list[DirectiveInterpretation]:
    """Validate all LLM output before it becomes an optimization constraint."""
    if len(candidates) != len(request.operator_notes):
        raise DirectiveValidationError(
            "the model must return exactly one directive for every operator note"
        )

    interpretations = [_validate_candidate(candidate, request) for candidate in candidates]
    indexes = [item.note_index for item in interpretations]
    if indexes != list(range(len(request.operator_notes))):
        raise DirectiveValidationError("directives must be returned once each in note_index order")
    return interpretations


def compile_constraints(
    request: OptimizationRequest, interpretations: list[DirectiveInterpretation]
) -> EffectiveConstraints:
    """Merge directives into one deterministic set of 24 hourly limits."""
    solar_factor = [1.0] * 24
    minimum_reserve = [request.battery.minimum_energy_kwh] * 24
    max_grid: list[float | None] = [None] * 24
    charge_forbidden: set[int] = set()
    discharge_forbidden: set[int] = set()

    for interpretation in interpretations:
        if not interpretation.applies:
            continue
        adjustment = interpretation.structured_adjustment or {}
        hours = adjustment["hours"]
        if interpretation.directive_type is DirectiveType.SOLAR_REDUCTION:
            for hour in hours:
                solar_factor[hour] = min(solar_factor[hour], adjustment["factor"])
        elif interpretation.directive_type is DirectiveType.MINIMUM_BATTERY_RESERVE:
            for hour in hours:
                minimum_reserve[hour] = max(minimum_reserve[hour], adjustment["minimum_energy_kwh"])
        elif interpretation.directive_type is DirectiveType.NO_CHARGE_WINDOW:
            charge_forbidden.update(hours)
        elif interpretation.directive_type is DirectiveType.NO_DISCHARGE_WINDOW:
            discharge_forbidden.update(hours)
        elif interpretation.directive_type is DirectiveType.MAX_GRID_WINDOW:
            for hour in hours:
                value = adjustment["max_grid_kwh"]
                max_grid[hour] = value if max_grid[hour] is None else min(max_grid[hour], value)

    return EffectiveConstraints(
        solar_factor=tuple(solar_factor),
        minimum_reserve=tuple(minimum_reserve),
        charge_forbidden=frozenset(charge_forbidden),
        discharge_forbidden=frozenset(discharge_forbidden),
        max_grid=tuple(max_grid),
    )
