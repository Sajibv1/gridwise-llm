# GridWise LLM Energy Optimizer

Public HTTP service for the BUP CSE Fest 2026 GridWise preliminary. It converts one to three natural-language operator
notes into validated constraints, then returns a least-cost, feasible 24-hour campus energy schedule.

## Architecture

```text
JSON request
  └─ Pydantic request validation
       └─ OpenAI Structured Outputs (interpret operator notes only)
            └─ deterministic directive guardrails
                 └─ SciPy/HiGHS linear optimizer
                      └─ independent deterministic schedule replay
                           └─ machine-checkable JSON response
```

The LLM is mandatory and is part of the operator-note interpretation path. It never chooses a schedule, calls tools, or
directly changes the optimizer. Its output is rejected unless deterministic code verifies note mapping, type, hour order,
numeric ranges, applies semantics, and the exact adjustment shape.

## Supported operator directives

| Type | Adjustment |
| --- | --- |
| `solar_reduction` | `{"hours": [...], "factor": 0..1}` |
| `minimum_battery_reserve` | `{"hours": [...], "minimum_energy_kwh": number}` |
| `no_charge_window` | `{"hours": [...]}` |
| `no_discharge_window` | `{"hours": [...]}` |
| `max_grid_window` | `{"hours": [...], "max_grid_kwh": number}` |
| `no_op` | `null` |

All time windows are start-inclusive and end-exclusive. A solar factor is the usable fraction remaining: an 80% reduction
means `factor: 0.2`.

## Local quickstart

Requires Python 3.12+ and an OpenAI API key for a model that supports strict JSON-schema output.

```bash
python3 -m pip install --user -r requirements.txt
cp .env.example .env
# Put the key only in .env; do not commit it.
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

In another terminal:

```bash
curl http://localhost:8000/health
python scripts/verify_public_samples.py http://localhost:8000
```

Expected health response:

```json
{"status":"ok"}
```

The public-case verifier posts all ten supplied cases, replays every returned plan, checks returned totals, and compares
cost with the published optimal reference. It does not rely on hard-coded phrases or schedules in production code.

## API

### `GET /health`

Returns HTTP 200 and `{"status":"ok"}` once the service process is running.

### `POST /optimize-energy`

Accepts exactly the challenge request shape: `scenario_id`, `operator_notes`, 24 `hours` entries, and `battery`. Returns
the required `directive_interpretation`, `hourly_plan`, `total_grid_kwh`, `total_cost_bdt`, `peak_grid_kwh`, and
`plan_summary` fields.

- Malformed or structurally invalid requests return HTTP 400.
- A feasible-shape but infeasible scenario returns HTTP 422.
- Provider, model-output, or internal replay failure returns controlled HTTP 500 without secrets, stack traces, prompts,
  or raw provider output.

## Optimizer and validity guarantees

The objective is `sum(grid_kwh[h] * tariff_bdt_per_kwh[h])`. The linear program enforces all 24 hourly energy equations,
effective solar, charge/discharge rate limits, reserve, capacity, no-charge/no-discharge periods, grid caps, and final
battery energy equal to starting energy. Before every response is returned, a second implementation recalculates every
rule and all aggregate values within the challenge’s 0.01 tolerance.

## Security and LLM guardrails

- Operator notes are untrusted quoted data; prompt-injection-like text is never followed as an instruction.
- The interpreter has no tools, file access, network actions, or secrets in its input.
- Strict JSON-schema output prevents free-form control data, and deterministic validation checks all remaining semantics.
- The service logs neither API keys nor operator-note contents by default.
- `OPENAI_API_KEY` is read from an environment variable or Azure secret reference only.

## Docker fallback image

Build and test the image locally:

```bash
docker build -t gridwise-llm:local .
docker run --rm -p 8000:8000 --env-file .env gridwise-llm:local
```

Publish a tested, immutable tagged image to Docker Hub or GitHub Container Registry before submission. Supply that exact
tag or digest in the submission form; do not use an untested `latest` tag as the fallback reference.

## Azure Container Apps deployment

The Azure resource group `gridwise-fest-rg` exists. Create a Container Apps environment in an Azure subscription region
that is also suitable for the selected LLM provider, then deploy from Azure Cloud Shell:

```bash
az containerapp env create --name gridwise-fest-id-env --resource-group gridwise-fest-rg --location indonesiacentral
ENVIRONMENT=gridwise-fest-id-env APP_NAME=gridwise-api-id \
  IMAGE=ghcr.io/OWNER/gridwise-llm:TAG bash deploy/azure-containerapp.sh
```

The script reads the API key without echoing it, writes it as an Azure Container Apps secret, starts one replica to avoid
cold-start risk during judging, permits two replicas, and prints the public HTTPS hostname. To update the image after a
fully successful regression test:

```bash
az containerapp update --name gridwise-api --resource-group gridwise-fest-rg --image ghcr.io/OWNER/gridwise-llm:NEW_TAG
```

## Tests and quality gate

```bash
pytest
```

The test suite verifies every provided public scenario, directive guardrails, prompt-injection-safe `no_op` handling,
optimizer cost, deterministic replay, `/health`, request rejection, and API output shape.

Every push and pull request also runs the same lint/test gate and a Docker `/health` smoke test through
`.github/workflows/quality.yml`.

## Continuous deployment (GitHub Actions to Azure)

The one-time Azure setup uses GitHub OIDC rather than an Azure password or client secret. In Azure Cloud Shell, run:

```bash
bash deploy/bootstrap-github-oidc.sh
```

It creates a Microsoft Entra application trusted only for this repository's `main` branch and assigns it Contributor
only on `gridwise-fest-rg`. Add the three printed identifiers as GitHub repository secrets, then the deploy job in
`.github/workflows/quality.yml` can publish the commit image and update `gridwise-api-id` only after the quality gate
passes.

Before submission, use [docs/submission-checklist.md](docs/submission-checklist.md). The required three-minute
architecture/solution video should follow [docs/video-outline.md](docs/video-outline.md).

## Known limitations

- A hosted LLM provider must be available, funded, and within quota during judging.
- The current provider adapter targets OpenAI Structured Outputs; the architecture deliberately isolates it in
  `app/interpreter.py` so a compatible provider can be substituted without changing safety checks or optimization logic.
- Public samples are regression tests, not a substitute for robust semantic handling of hidden paraphrases.
