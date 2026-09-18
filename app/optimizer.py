from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog

from app.directives import EffectiveConstraints
from app.models import BatteryAction, HourlyPlanEntry, OptimizationRequest


class OptimizationError(RuntimeError):
    """Raised for infeasible or unexpected linear-program results."""


@dataclass(frozen=True)
class OptimizationResult:
    hourly_plan: list[HourlyPlanEntry]
    total_grid_kwh: float
    total_cost_bdt: float
    peak_grid_kwh: float


HORIZON = 24
EPSILON = 1e-7


def _index(block: int, hour: int) -> int:
    return block * HORIZON + hour


GRID, SOLAR, CHARGE, DISCHARGE, ENERGY = range(5)
VARIABLES = HORIZON * 5


def _rounded(value: float) -> float:
    return round(0.0 if abs(value) < EPSILON else float(value), 6)


def optimize_schedule(
    request: OptimizationRequest, constraints: EffectiveConstraints
) -> OptimizationResult:
    """Solve the 24-hour linear program without trusting any LLM-derived math."""
    costs = np.zeros(VARIABLES)
    for hour, entry in enumerate(request.hours):
        costs[_index(GRID, hour)] = entry.tariff_bdt_per_kwh

    equalities: list[np.ndarray] = []
    equality_rhs: list[float] = []
    inequalities: list[np.ndarray] = []
    inequality_rhs: list[float] = []
    bounds: list[tuple[float | None, float | None]] = [(0.0, None)] * VARIABLES

    for hour, entry in enumerate(request.hours):
        # grid + solar + discharge = demand + charge
        balance = np.zeros(VARIABLES)
        balance[_index(GRID, hour)] = 1.0
        balance[_index(SOLAR, hour)] = 1.0
        balance[_index(CHARGE, hour)] = -1.0
        balance[_index(DISCHARGE, hour)] = 1.0
        equalities.append(balance)
        equality_rhs.append(entry.demand_kwh)

        # E[h] = E[h-1] + charge[h] - discharge[h]
        transition = np.zeros(VARIABLES)
        transition[_index(ENERGY, hour)] = 1.0
        transition[_index(CHARGE, hour)] = -1.0
        transition[_index(DISCHARGE, hour)] = 1.0
        if hour == 0:
            equality_rhs.append(request.battery.initial_energy_kwh)
        else:
            transition[_index(ENERGY, hour - 1)] = -1.0
            equality_rhs.append(0.0)
        equalities.append(transition)

        effective_solar = entry.solar_kwh * constraints.solar_factor[hour]
        grid_max = constraints.max_grid[hour]
        bounds[_index(GRID, hour)] = (0.0, grid_max)
        bounds[_index(SOLAR, hour)] = (0.0, effective_solar)
        bounds[_index(CHARGE, hour)] = (
            0.0,
            0.0
            if hour in constraints.charge_forbidden
            else request.battery.max_charge_kwh_per_hour,
        )
        bounds[_index(DISCHARGE, hour)] = (
            0.0,
            0.0
            if hour in constraints.discharge_forbidden
            else request.battery.max_discharge_kwh_per_hour,
        )
        bounds[_index(ENERGY, hour)] = (
            constraints.minimum_reserve[hour],
            request.battery.capacity_kwh,
        )

    # The start energy is borrowed across the day, not consumed for free.
    neutrality = np.zeros(VARIABLES)
    neutrality[_index(ENERGY, HORIZON - 1)] = 1.0
    equalities.append(neutrality)
    equality_rhs.append(request.battery.initial_energy_kwh)

    result = linprog(
        c=costs,
        A_ub=np.vstack(inequalities) if inequalities else None,
        b_ub=np.array(inequality_rhs) if inequality_rhs else None,
        A_eq=np.vstack(equalities),
        b_eq=np.array(equality_rhs),
        bounds=bounds,
        method="highs",
        options={"presolve": True},
    )
    if not result.success or result.x is None:
        message = "the scenario cannot be scheduled within the declared constraints"
        raise OptimizationError(message)

    plan: list[HourlyPlanEntry] = []
    for hour in range(HORIZON):
        # Charge and discharge are separate non-negative LP variables.  They have a
        # cost-neutral simultaneous-flow direction, so a valid HiGHS solution may
        # contain both even though the public API represents exactly one battery
        # action per hour.  Emit their signed net: it preserves every balance,
        # state transition, directive, rate limit, and the objective value.
        net_battery = float(result.x[_index(CHARGE, hour)]) - float(
            result.x[_index(DISCHARGE, hour)]
        )
        battery_kwh = _rounded(abs(net_battery))
        if net_battery > EPSILON:
            action = BatteryAction.CHARGE
        elif net_battery < -EPSILON:
            action = BatteryAction.DISCHARGE
        else:
            action, battery_kwh = BatteryAction.IDLE, 0.0
        plan.append(
            HourlyPlanEntry(
                hour=hour,
                grid_kwh=_rounded(result.x[_index(GRID, hour)]),
                solar_used_kwh=_rounded(result.x[_index(SOLAR, hour)]),
                battery_action=action,
                battery_kwh=battery_kwh,
                battery_energy_after_kwh=_rounded(result.x[_index(ENERGY, hour)]),
            )
        )

    total_grid = _rounded(sum(item.grid_kwh for item in plan))
    total_cost = _rounded(
        sum(item.grid_kwh * request.hours[item.hour].tariff_bdt_per_kwh for item in plan)
    )
    peak_grid = _rounded(max(item.grid_kwh for item in plan))
    return OptimizationResult(plan, total_grid, total_cost, peak_grid)
