from __future__ import annotations

import json
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
