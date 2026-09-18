from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import LLMDirectiveCandidate, OptimizationRequest


class ReferenceInterpreter:
    def __init__(self, candidates: list[LLMDirectiveCandidate]) -> None:
        self._candidates = candidates

    def interpret(self, _: OptimizationRequest) -> list[LLMDirectiveCandidate]:
        return self._candidates


class RepairingReferenceInterpreter(ReferenceInterpreter):
    def __init__(
        self, initial: list[LLMDirectiveCandidate], repaired: list[LLMDirectiveCandidate]
    ) -> None:
        super().__init__(initial)
        self._repaired = repaired
        self.repair_feedback: list[str] = []

    def repair(
        self, _: OptimizationRequest, validation_feedback: str
    ) -> list[LLMDirectiveCandidate]:
        self.repair_feedback.append(validation_feedback)
        return self._repaired


def _sample_case() -> dict:
    path = Path(__file__).parents[1] / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json"
    return json.loads(path.read_text(encoding="utf-8"))["cases"][0]


def test_health_and_public_sample_contract() -> None:
    case = _sample_case()
    candidates = [
        LLMDirectiveCandidate.model_validate(item)
        for item in case["expected_output"]["directive_interpretation"]
    ]
    app = create_app(Settings(), ReferenceInterpreter(candidates))
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    response = client.post("/optimize-energy", json=case["input"])
    assert response.status_code == 200
    data = response.json()
    assert data["scenario_id"] == case["input"]["scenario_id"]
    assert len(data["directive_interpretation"]) == len(case["input"]["operator_notes"])
    assert [entry["hour"] for entry in data["hourly_plan"]] == list(range(24))
    assert data["total_cost_bdt"] == case["expected_output"]["total_cost_bdt"]


def test_invalid_request_is_http_400() -> None:
    app = create_app(Settings(), ReferenceInterpreter([]))
    response = TestClient(app).post("/optimize-energy", json={"scenario_id": "missing everything"})
    assert response.status_code == 400
    assert response.json() == {"detail": "malformed or structurally invalid request"}


def test_semantic_validation_failure_gets_one_bounded_repair_attempt() -> None:
    case = _sample_case()
    expected = [
        LLMDirectiveCandidate.model_validate(item)
        for item in case["expected_output"]["directive_interpretation"]
    ]
    invalid = expected.copy()
    invalid[0] = invalid[0].model_copy(update={"applies": False})
    interpreter = RepairingReferenceInterpreter(invalid, expected)
    app = create_app(Settings(llm_semantic_retries=1), interpreter)

    response = TestClient(app).post("/optimize-energy", json=case["input"])

    assert response.status_code == 200
    assert len(interpreter.repair_feedback) == 1
    assert "applicable directives require applies=true" in interpreter.repair_feedback[0]


def test_semantic_repair_does_not_loop_when_the_repair_is_still_invalid() -> None:
    case = _sample_case()
    expected = [
        LLMDirectiveCandidate.model_validate(item)
        for item in case["expected_output"]["directive_interpretation"]
    ]
    invalid = expected.copy()
    invalid[0] = invalid[0].model_copy(update={"applies": False})
    interpreter = RepairingReferenceInterpreter(invalid, invalid)
    app = create_app(Settings(llm_semantic_retries=1), interpreter)

    response = TestClient(app).post("/optimize-energy", json=case["input"])

    assert response.status_code == 500
    assert response.json() == {"detail": "language-model output failed deterministic validation"}
    assert len(interpreter.repair_feedback) == 1


def test_openapi_documentation_has_descriptions_and_a_valid_request_example() -> None:
    app = create_app(Settings(), ReferenceInterpreter([]))
    document = TestClient(app).get("/openapi.json").json()

    assert "deterministically" in document["info"]["description"]
    assert document["paths"]["/health"]["get"]["operationId"] == "getHealth"
    optimize_operation = document["paths"]["/optimize-energy"]["post"]
    assert optimize_operation["operationId"] == "optimizeEnergy"
    assert optimize_operation["summary"] == "Interpret notes and optimize a 24-hour energy plan"
    example = optimize_operation["requestBody"]["content"]["application/json"]["examples"][
        "two_directives"
    ]["value"]
    assert len(example["hours"]) == 24
    assert example["hours"][0]["hour"] == 0
    assert example["hours"][-1]["hour"] == 23
    assert document["components"]["schemas"]["OptimizationRequest"]["properties"]["operator_notes"][
        "description"
    ]
