# Three-minute solution-video outline

## 0:00–0:20 — challenge and contract

Show the deployed public endpoint and state that `POST /optimize-energy` receives a 24-hour scenario plus one to three
operator notes. State that the LLM interprets notes, but deterministic code controls every actionable constraint.

## 0:20–1:05 — architecture

Show this flow:

```text
request → Pydantic validation → OpenAI structured output → directive guardrails
        → linear optimizer → independent replay → exact JSON response
```

Explain that the model receives no tools and no secrets; notes are quoted untrusted data. Explain the six allowed
directive types and that unknown or malicious text becomes `no_op` only when the model classifies it so and the schema
passes validation.

## 1:05–1:55 — correctness

Walk through one public case. Show its parsed directive, effective solar/reserve/grid constraints, and the hourly plan.
Point out energy balance, rate limits, final battery neutrality, and recomputed totals. Run the public-case verifier.

## 1:55–2:30 — reliability and deployment

Show `/health`, the Docker image, Azure Container Apps configuration, secret reference (never the secret value), and a
real request. Explain the bounded LLM timeout/retry policy and safe failure path.

## 2:30–3:00 — engineering and repeatability

Show `pytest`, `README.md`, `requirements.txt`, and the Docker run command. State how a judge can clone, configure
environment variable names, run locally, use the fallback image, and execute public cases.

