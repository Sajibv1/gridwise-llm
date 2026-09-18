from __future__ import annotations

from math import isfinite

from app.directives import EffectiveConstraints
from app.models import BatteryAction, HourlyPlanEntry, OptimizationRequest


class ReplayValidationError(ValueError):
    """Raised when a generated schedule fails independent deterministic replay."""


TOLERANCE = 0.01


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise ReplayValidationError(message)


def _close(left: float, right: float) -> bool:
    return abs(left - right) <= TOLERANCE


def replay_plan(
    request: OptimizationRequest,
    constraints: EffectiveConstraints,
    hourly_plan: list[HourlyPlanEntry],
) -> tuple[float, float, float]:
    """Recalculate every judge-relevant rule from the returned plan."""
    _assert(len(hourly_plan) == 24, "hourly_plan must have exactly 24 entries")
    _assert(
        [entry.hour for entry in hourly_plan] == list(range(24)),
        "hourly_plan must be ordered 0 through 23",
    )

    previous_energy = request.battery.initial_energy_kwh
    total_grid = 0.0
    total_cost = 0.0
    peak_grid = 0.0

    for hour, plan in enumerate(hourly_plan):
        scenario = request.hours[hour]
        values = [
            plan.grid_kwh,
            plan.solar_used_kwh,
            plan.battery_kwh,
            plan.battery_energy_after_kwh,
        ]
        _assert(
            all(isfinite(value) and value >= -TOLERANCE for value in values),
            "plan values must be finite and non-negative",
        )

        charge = plan.battery_kwh if plan.battery_action is BatteryAction.CHARGE else 0.0
        discharge = plan.battery_kwh if plan.battery_action is BatteryAction.DISCHARGE else 0.0
        if plan.battery_action is BatteryAction.IDLE:
            _assert(
                abs(plan.battery_kwh) <= TOLERANCE,
                f"hour {hour}: idle action requires zero battery_kwh",
            )
        _assert(
            charge <= request.battery.max_charge_kwh_per_hour + TOLERANCE,
            f"hour {hour}: charge rate exceeded",
        )
        _assert(
            discharge <= request.battery.max_discharge_kwh_per_hour + TOLERANCE,
            f"hour {hour}: discharge rate exceeded",
        )
        _assert(
            hour not in constraints.charge_forbidden or charge <= TOLERANCE,
            f"hour {hour}: charge forbidden",
        )
        _assert(
            hour not in constraints.discharge_forbidden or discharge <= TOLERANCE,
            f"hour {hour}: discharge forbidden",
        )

        effective_solar = scenario.solar_kwh * constraints.solar_factor[hour]
        _assert(
            plan.solar_used_kwh <= effective_solar + TOLERANCE,
            f"hour {hour}: solar exceeds effective availability",
        )
        grid_cap = constraints.max_grid[hour]
        _assert(
            grid_cap is None or plan.grid_kwh <= grid_cap + TOLERANCE,
            f"hour {hour}: grid cap exceeded",
        )

        expected_energy = previous_energy + charge - discharge
        _assert(
            _close(plan.battery_energy_after_kwh, expected_energy),
            f"hour {hour}: invalid battery transition",
        )
        _assert(
            plan.battery_energy_after_kwh >= constraints.minimum_reserve[hour] - TOLERANCE,
            f"hour {hour}: reserve violated",
        )
        _assert(
            plan.battery_energy_after_kwh <= request.battery.capacity_kwh + TOLERANCE,
            f"hour {hour}: capacity exceeded",
        )
        supplied = plan.grid_kwh + plan.solar_used_kwh + discharge
        consumed = scenario.demand_kwh + charge
        _assert(_close(supplied, consumed), f"hour {hour}: energy balance violated")

        previous_energy = plan.battery_energy_after_kwh
        total_grid += plan.grid_kwh
        total_cost += plan.grid_kwh * scenario.tariff_bdt_per_kwh
        peak_grid = max(peak_grid, plan.grid_kwh)

    _assert(
        _close(previous_energy, request.battery.initial_energy_kwh),
        "end-of-day battery neutrality violated",
    )
    return round(total_grid, 6), round(total_cost, 6), round(peak_grid, 6)
