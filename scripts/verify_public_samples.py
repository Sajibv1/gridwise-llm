"""Exercise a live GridWise endpoint against every provided public case."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Make the documented `python scripts/...` invocation work from a clean clone.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app.directives import compile_constraints
from app.models import DirectiveInterpretation, HourlyPlanEntry, OptimizationRequest
from app.replay import replay_plan


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/verify_public_samples.py http://localhost:8000")
        return 2
    base_url = sys.argv[1].rstrip("/")
    sample_path = Path(__file__).parents[1] / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json"
    cases = json.loads(sample_path.read_text(encoding="utf-8"))["cases"]
    failures: list[str] = []

    for case in cases:
        body = json.dumps(case["input"]).encode("utf-8")
        request = Request(
            f"{base_url}/optimize-energy",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=35) as response:
                if response.status != 200:
                    raise RuntimeError(f"HTTP {response.status}")
                returned = json.loads(response.read().decode("utf-8"))
            scenario = OptimizationRequest.model_validate(case["input"])
            directives = [
                DirectiveInterpretation.model_validate(item)
                for item in returned["directive_interpretation"]
            ]
            expected_directives = [
                DirectiveInterpretation.model_validate(item)
                for item in case["expected_output"]["directive_interpretation"]
            ]
            plan = [HourlyPlanEntry.model_validate(item) for item in returned["hourly_plan"]]
            assert [item.model_dump(exclude={"explanation"}) for item in directives] == [
                item.model_dump(exclude={"explanation"}) for item in expected_directives
            ]
            total_grid, total_cost, peak_grid = replay_plan(
                scenario, compile_constraints(scenario, expected_directives), plan
            )
            expected = case["expected_output"]
            assert abs(total_grid - returned["total_grid_kwh"]) <= 0.01
            assert abs(total_cost - returned["total_cost_bdt"]) <= 0.01
            assert abs(peak_grid - returned["peak_grid_kwh"]) <= 0.01
            assert abs(total_cost - expected["total_cost_bdt"]) <= 0.01
            print(f"PASS {case['id']} cost={total_cost:.2f}")
        except (AssertionError, HTTPError, URLError, RuntimeError, ValueError) as error:
            failures.append(f"FAIL {case['id']}: {error}")

    print(*failures, sep="\n")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
