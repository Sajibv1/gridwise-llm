# GridWise submission checklist

## Before the event deadline

- [ ] Create the event repository after question reveal and keep it private.
- [ ] Add `OPENAI_API_KEY` only as a deployment secret; verify `.env` is ignored.
- [ ] Run `pytest` and `python scripts/verify_public_samples.py http://localhost:8000`.
- [ ] Test `GET /health` and `POST /optimize-energy` from an external network.
- [ ] Publish a tagged Docker image, record its immutable tag/digest, and test its pull/run path.
- [ ] Deploy the public Azure Container App and preserve its public HTTPS URL.
- [ ] Record model/provider, model name, timeout/retry policy, dependency versions, and known limitations in README.
- [ ] Make the required three-minute video using `docs/video-outline.md`.

## During judging

- [ ] Keep the endpoint reachable and Container App at one minimum replica.
- [ ] Monitor LLM quota, provider status, p95 latency, and application logs for controlled failures only.
- [ ] Do not change endpoint names, schema, provider key, or Docker tag without retesting all public cases.

## After the deadline

- [ ] Make the repository public only when the official rule permits it.
- [ ] Keep the fallback image and video reachable through the judging window.

