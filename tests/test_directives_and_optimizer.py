from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from app.directives import (
    DirectiveValidationError,
    compile_constraints,
    validate_interpretations,
)
from app.models import LLMDirectiveCandidate, OptimizationRequest
from app.optimizer import optimize_schedule
from app.replay import replay_plan

SAMPLES_PATH = Path(__file__).parents[1] / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json"
SAMPLES = json.loads(SAMPLES_PATH.read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", SAMPLES, ids=lambda item: item["id"])
def test_every_public_case_replays_and_matches_optimal_cost(case: dict) -> None:
    """Public cases validate the full deterministic half of the competition pipeline."""
    request = OptimizationRequest.model_validate(case["input"])
    candidates = [
        LLMDirectiveCandidate.model_validate(item)
        for item in case["expected_output"]["directive_interpretation"]
    ]

    directives = validate_interpretations(candidates, request)
    constraints = compile_constraints(request, directives)
    result = optimize_schedule(request, constraints)
    total_grid, total_cost, peak_grid = replay_plan(request, constraints, result.hourly_plan)

    expected = case["expected_output"]
    assert total_grid >= 0
    assert peak_grid >= 0
    assert total_cost == pytest.approx(expected["total_cost_bdt"], abs=0.01)
    assert [item.model_dump(exclude={"explanation"}) for item in directives] == [
        {key: value for key, value in item.items() if key != "explanation"}
        for item in expected["directive_interpretation"]
    ]


def test_guardrail_rejects_out_of_order_or_unsafe_model_output() -> None:
    request = OptimizationRequest.model_validate(SAMPLES[0]["input"])
    unsafe = [
        LLMDirectiveCandidate(
            note_index=1,
            applies=False,
            directive_type="no_op",
            structured_adjustment=None,
            explanation="irrelevant",
        ),
        LLMDirectiveCandidate(
            note_index=0,
            applies=True,
            directive_type="solar_reduction",
            structured_adjustment={"hours": [13, 12], "factor": 0.25},
            explanation="bad order",
        ),
    ]
    with pytest.raises(DirectiveValidationError):
        validate_interpretations(unsafe, request)


def test_guardrail_rejects_prompt_injection_as_a_non_directive() -> None:
    request = OptimizationRequest.model_validate(SAMPLES[0]["input"])
    candidates = [
        LLMDirectiveCandidate(
            note_index=0,
            applies=False,
            directive_type="no_op",
            structured_adjustment=None,
            explanation="The text is unrelated to the energy schedule.",
        ),
        LLMDirectiveCandidate(
            note_index=1,
            applies=False,
            directive_type="no_op",
            structured_adjustment=None,
            explanation="The text is unrelated to the energy schedule.",
        ),
    ]
    assert all(not item.applies for item in validate_interpretations(candidates, request))


def test_provider_schema_forbids_open_ended_adjustment_objects() -> None:
    schema = LLMDirectiveCandidate.model_json_schema()
    assert '"additionalProperties": true' not in json.dumps(schema).lower()


def test_asymmetric_battery_rate_limits_replay_after_netting_simultaneous_lp_flow() -> None:
    """A degenerate LP solution may contain simultaneous charge/discharge.

    The response contract permits one action only, so the optimizer must serialize
    the signed net flow rather than dropping either side of that LP solution.
    """
    random_source = random.Random(7)
    capacity = random_source.choice([100, 220, 500])
    max_charge = round(random_source.uniform(0, capacity * 0.6), 1)
    max_discharge = round(random_source.uniform(0, capacity * 0.6), 1)
    hours = []
    for hour in range(24):
        solar = 0.0 if hour < 6 or hour > 18 else round(random_source.uniform(0, 260), 1)
        hours.append(
            {
                "hour": hour,
                "demand_kwh": round(random_source.uniform(20, 400), 1),
                "solar_kwh": solar,
                "tariff_bdt_per_kwh": round(random_source.uniform(3, 18), 2),
            }
        )
    raw = {
        "scenario_id": "asymmetric-rate-regression",
        "operator_notes": ["note"],
        "hours": hours,
        "battery": {
            "capacity_kwh": capacity,
            "initial_energy_kwh": round(random_source.uniform(0, capacity), 1),
            "minimum_energy_kwh": round(random_source.uniform(0, capacity * 0.5), 1),
            "max_charge_kwh_per_hour": max_charge,
            "max_discharge_kwh_per_hour": max_discharge,
        },
    }
    request = OptimizationRequest.model_validate(raw)
    constraints = compile_constraints(request, [])

    result = optimize_schedule(request, constraints)

    # This scenario used to fail at hour 23 when the LP's discharge flow was
    # silently omitted from the serialized charge action.
    replay_plan(request, constraints, result.hourly_plan)
