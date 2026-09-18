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
