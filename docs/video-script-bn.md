# GridWise 3-minute video script — বাংলা

**Team:** Infinity Loop SEU  
**Target duration:** 2:50 (শেষে 10 সেকেন্ড নিরাপদ buffer রাখুন)  
**ভিডিওর লক্ষ্য:** বড় দাবি না করে live deployment, LLM-to-optimizer flow, deterministic correctness, এবং reproduction evidence দেখানো।

## রেকর্ড করার আগে

- 1920×1080 resolution এবং বড় zoom ব্যবহার করুন; terminal font অন্তত 20–24 px রাখুন।
- API key, Azure subscription/tenant ID, secret value, `.env` file, বা terminal history কখনও দেখাবেন না।
- আগেই browser tab খুলে রাখুন: live `/docs`, GitHub Actions-এর সবুজ run, Azure Container App Overview, README।
- একটি terminal-এ public verifier এবং semantic verifier চালানোর command প্রস্তুত রাখুন।
- 24 ঘণ্টার বড় JSON বা পুরো code file scroll করবেন না; শুধু দরকারি অংশ zoom করে দেখাবেন।

## 0:00–0:12 — পরিচয় ও live API

**স্ক্রিনে দেখান:**

1. পরিষ্কার title slide: `GridWise LLM Energy Optimizer` এবং `Infinity Loop SEU`।
2. সঙ্গে সঙ্গে live Swagger URL খুলুন: `https://gridwise-api-id.yellowocean-23e36385.indonesiacentral.azurecontainerapps.io/docs`

**বলুন:**

> আসসালামু আলাইকুম। আমরা Infinity Loop SEU। এটি আমাদের GridWise LLM Energy Optimizer। এটি একটি live FastAPI service, যেখানে `GET /health` এবং `POST /optimize-energy` endpoint public ভাবে চালু আছে।

## 0:12–0:32 — সমস্যার input ও output contract

**স্ক্রিনে দেখান:**

1. Swagger-এর `POST /optimize-energy` section।
2. Request example-এ শুধু `operator_notes`, battery fields, এবং একটি–দুটি hourly item zoom করে দেখান।
3. Response example-এ `directive_interpretation`, `hourly_plan`, `total_cost_bdt` highlight করুন।

**বলুন:**

> প্রতিটি request-এ ২৪ ঘণ্টার demand, solar, tariff, battery limit এবং এক থেকে তিনটি operator note থাকে। আমাদের output প্রতিটি note-এর structured interpretation, ২৪ ঘণ্টার feasible plan, এবং recalculated cost দেয়।

## 0:32–0:57 — architecture

**স্ক্রিনে দেখান:**

একটি simple diagram, পূর্ণ screen-এ:

```text
Request → Pydantic validation → GPT-5.4 mini structured output
        → deterministic directive guardrails → HiGHS LP optimizer
        → independent replay validation → JSON response
```

**বলুন:**

> LLM শুধু natural-language operator note-কে নির্দিষ্ট directive-এ ব্যাখ্যা করে। এরপর Pydantic schema এবং deterministic guardrails সেটি validate করে। LLM কখনও cost, battery calculation বা final schedule তৈরি করে না। Solver schedule তৈরি করার পরে আমরা আলাদা replay দিয়ে প্রতিটি rule আবার যাচাই করি।

## 0:57–1:22 — note থেকে validated directive

**স্ক্রিনে দেখান:**

1. একটি sample note: `Solar will be reduced by 80% from noon until 2 PM.`
2. তার পাশে response-এর relevant directive:

```json
{"directive_type":"solar_reduction","hours":[12,13],"factor":0.2}
```

3. `no_op` injection/paraphrase test-এর একটি PASS line।

**বলুন:**

> যেমন, ৮০ শতাংশ solar reduction মানে usable solar factor ০.২, এবং noon থেকে 2 PM হলে hour 12 ও 13। Time range start-inclusive, end-exclusive। অপ্রাসঙ্গিক বা prompt-injection text কোনো tool বা system instruction হিসেবে নেওয়া হয় না; সেটি validated `no_op` হয়।

## 1:22–1:47 — optimization correctness

**স্ক্রিনে দেখান:**

1. `app/optimizer.py`-এর ছোট zoomed section: charge/discharge net-flow comment।
2. `app/replay.py`-এর battery transition অথবা energy-balance checks-এর ছোট section।
3. Response-এর 2–3 relevant plan rows এবং total cost।

**বলুন:**

> Optimization অংশে আমরা linear programming ব্যবহার করেছি। প্রতিটি hour-এ energy balance, effective solar, charge ও discharge rate, reserve, grid cap এবং end-of-day battery neutrality enforce করা হয়। Solver-এর output response দেওয়ার আগে independently replay করা হয়। এছাড়া asymmetric charge-discharge limits-এর ক্ষেত্রে simultaneous LP flow-কে signed net action হিসেবে serialize করেছি, যাতে returned plan সবসময় single-action contract মেনে চলে।

## 1:47–2:07 — বাস্তব test evidence

**স্ক্রিনে দেখান:**

Terminal full screen-এ, আগে থেকে চালানো বা এখন চালানো output:

```bash
pytest -q
python scripts/verify_public_samples.py https://gridwise-api-id.yellowocean-23e36385.indonesiacentral.azurecontainerapps.io
python scripts/verify_semantic_paraphrases.py https://gridwise-api-id.yellowocean-23e36385.indonesiacentral.azurecontainerapps.io
```

`19 passed`, `PASS SAMPLE-01` থেকে `PASS SAMPLE-10`, এবং পাঁচটি semantic `PASS` line পরিষ্কার দেখা যায় এমনভাবে দেখান।

**বলুন:**

> আমরা unit tests, সব ১০টি public sample case, এবং আলাদা paraphrase ও injection cases live endpoint-এ চালিয়েছি। এগুলো interpretation, cost optimality, replay validity এবং security behavior যাচাই করে।

## 2:07–2:29 — deployment, CI/CD, reliability

**স্ক্রিনে দেখান:**

1. Browser-এ GitHub Actions-এর green workflow run; jobs: test, Docker health, publish-and-deploy।
2. Azure Container App Overview-এ app status এবং public FQDN; secret **value নয়**, শুধু secret reference থাকলে সেটি দেখান।
3. `/health`-এ `{"status":"ok"}` response।

**বলুন:**

> Main branch-এ push হলে CI lint, format check, tests এবং Docker health check চালায়। এরপর immutable container image Azure Container Apps-এ deploy হয় এবং public health endpoint যাচাই করে। OpenAI key শুধু Azure secret reference হিসেবে ব্যবহৃত হয়েছে; কোনো key source code বা image-এ নেই। আমরা ৭ সেকেন্ড per-model-call timeout, zero SDK transport retry, এবং সর্বোচ্চ এক semantic repair ব্যবহার করেছি যাতে ৩০ সেকেন্ড API limit-এর জন্য margin থাকে।

## 2:29–2:46 — reproducibility ও fallback

**স্ক্রিনে দেখান:**

1. README-এর Quick Start section।
2. Docker fallback image-এর exact digest এবং `docker run` command।
3. README-এর environment-variable names; কোনো value নয়।

**বলুন:**

> Azure endpoint unavailable হলেও judge README-এর exact immutable Docker image pull করে একই service চালাতে পারবেন। README-তে setup command, required environment-variable names, OpenAI model, solver dependency, sample request এবং verification command দেওয়া আছে।

## 2:46–2:50 — closing

**স্ক্রিনে দেখান:**

Title card:

```text
Infinity Loop SEU
GridWise LLM Energy Optimizer
Live API: …/ • Docs: …/docs
```

**বলুন:**

> ধন্যবাদ। এটি ছিল Infinity Loop SEU-এর GridWise LLM Energy Optimizer—LLM interpretation, deterministic safety checks এবং replay-validated optimization-এর একটি deployable solution।

## শেষ checklist

- ভিডিওটি 3:00-এর আগে শেষ হয়েছে কিনা দেখুন।
- Live URL এবং `/docs` একবার স্পষ্টভাবে দেখা গেছে কিনা দেখুন।
- LLM → guardrail → optimizer → replay flow ব্যাখ্যা হয়েছে কিনা দেখুন।
- Test evidence, deployment, Docker fallback, এবং README reproduction path দেখানো হয়েছে কিনা দেখুন।
- কোনো secret বা sensitive Azure identifier visible নেই কিনা আবার পরীক্ষা করুন।
