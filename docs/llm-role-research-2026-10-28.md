# LLM research for DevSecOps's three roles

Research date: **28 October 2026**. Scope: fast models with currently documented free API access or downloadable weights, matched to the actual implementation.

**Constraint update — 29 October 2026:** The user's computer is older and has no GPU; local model inference is excluded. Use hosted APIs so inference runs on provider hardware. For the current larger prompts, prioritize Gemini 3.8 Flash for all three separate roles with Tavily for source discovery. The Groq lineup below is a hosted alternative, conditional on fitting its free token allowances. The local-model section is retained as background only and is not a recommendation for this machine. The local Python application and browser will still consume ordinary CPU/RAM for fetching, validation, storage, and display.

This is a documentation-based selection, not a measured bake-off. No provider credentials, inference calls, or local model installations were used. Speeds below are provider claims; account access, quotas, queueing, and end-to-end latency still need validation. No application configuration was changed.

## Recommended choices

| Role | Preferred open-weight candidate | Free hosted route | Important condition |
| --- | --- | --- | --- |
| Repository Analyst | **Qwen3.8-27B** | Groq: `qwen/qwen3.8-27b` | Use compact evidence batches; the free token allowance cannot accommodate the current maximum repository prompt in one request. |
| Incident Researcher | **GPT-OSS-20B plus a separate search API** | Groq: `openai/gpt-oss-20b`; Tavily for discovery | Search supplies URLs; the LLM extracts mechanisms from independently fetched pages. Batch source text to fit the allowance. |
| Security Reviewer | **GPT-OSS-120B** | Groq: `openai/gpt-oss-120b` | Pass relevant passages and observations, rather than all six complete source documents. Start with medium reasoning. |

These are my engineering recommendations for a compact, free prototype. They are not proven winners on this project's security tasks. Groq lists approximately **450 tokens/s for Qwen3.8-27B, 1,000 for GPT-OSS-20B, and 500 for GPT-OSS-120B**. [Groq model catalog](https://console.groq.com/docs/models).

**For the current larger inputs, the most practical hosted candidate to evaluate first is Gemini 3.8 Flash plus Tavily across all three roles**, using separate role prompts. It has a 1,048,576-token input allowance and structured output support. This avoids making evidence compaction a prerequisite, although account throughput quotas still apply. [Gemini model specification](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash).

Google lists free text input/output for Gemini 3.8 Flash, but Google Search grounding is unavailable on its free API tier. Free Gemini data is listed as usable for product improvement. Thus free model access does not include free integrated search for new Gemini projects. [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing).

## What the code actually requires

The project currently uses one `OPENAI_MODEL`, defaulting to `gpt-4.1`, for every role. `ModelClient.call()` posts directly to OpenAI's Responses API. There is no provider adapter or per-role model routing.

| Role | Actual task | Selection criteria |
| --- | --- | --- |
| Repository Analyst | Read numbered files; map components, technologies, defenses, and unknowns; produce at most 16 observations, 8 technologies, 6 components, and 4 research questions. | Code comprehension, exact contiguous quotations and line ranges, uncertainty discipline, schema adherence, sufficient input budget. |
| Incident Researcher | Discover primary-source reports, fetch eligible pages, then extract up to 6 incident records with verbatim 40–800-character passages and separate incident/publication dates. | Reliable retrieval integration, faithful extraction, mechanism/prerequisite understanding, supported dates, valid source IDs. |
| Security Reviewer | Compare attack prerequisites with repository observations; preserve counterevidence and missing context; produce up to 8 findings; optionally request one follow-up. | Conditional reasoning, restraint against unsupported findings, cross-document evidence matching, correct classifications and IDs. |

Code examined: `devsecops/agents.py`, `config.py`, `contracts.py`, `pipeline.py`, and the README. All contracts require every property and reject additional properties. The current flow normally makes four model calls when incidents exist: analyst, discovery, extraction, reviewer. One follow-up and repeated review can bring it to six.

The input ceiling matters more than parameter count:

- Repository text can reach **100,000 characters**, before JSON escaping, line numbers, the tree, instructions, and schema.
- Six sources at **18,000 characters each** can contribute **108,000 characters** to extraction and review inputs.
- A rough estimate at four characters/token gives 25,000 repository tokens or 27,000 source tokens before overhead. Code and JSON tokenization vary; these are planning estimates, not tokenizer measurements.
- Each call allows 6,500 output tokens; the job budget is 900 seconds and six model calls.

Splitting prompts into multiple LLM calls therefore also requires revisiting the call budget. Quietly truncating files or passages would reduce coverage and must be surfaced.

## Role-by-role reasoning

### Repository Analyst: Qwen3.8-27B

Qwen3.8-27B is my first open-weight candidate because this role is primarily repository understanding and precise extraction. Its publisher reports repository and software-engineering evaluations, flexible thinking control, a native 262,144-token context, and Apache 2.0 licensing. The model card reports SWE-bench Pro 61.7 and NL2Repo-Bench 42.3, but describes its own harness and benchmark adjustments. These scores justify shortlisting, not a claim of security-audit accuracy. [Qwen model card](https://huggingface.co/Qwen/Qwen3.8-27B).

Use low reasoning or non-thinking mode where the serving provider supports it, then measure whether exact quotations and version interpretation remain reliable. Mapping supplied code does not automatically benefit from long reasoning traces.

Groq explicitly lists strict JSON Schema support for this model and both recommended GPT-OSS models. Its structured-output mode currently cannot be combined with tool use or streaming; discovery and extraction should remain separate. The project's existing two-step research stage already fits that separation. [Groq structured outputs](https://console.groq.com/docs/structured-outputs).

**Alternative:** Gemini 3.8 Flash for full repository snapshots and fewer moving pieces. Use low thinking for the initial comparison. Prefer it over forcing a large prompt through a small free token allowance.

### Incident Researcher: GPT-OSS-20B with Tavily

Here the decisive capability is evidence acquisition. No model's stored knowledge can establish which incidents were published in the requested recent window.

GPT-OSS-20B is a suitable speed-oriented candidate for query planning and extraction from supplied text. OpenAI describes it as a low-latency open-weight model with 21B total and 3.6B active parameters. It should still be compared against Qwen3.8-27B or Gemini on difficult mechanism extraction. [Official OpenAI documentation](https://developers.openai.com/api/docs/models/gpt-oss-20b).

**Search choice:** Tavily offers **1,000 recurring free credits/month without a credit card**. Basic search costs one credit; advanced search costs two. At three basic searches per review, the search allowance alone covers about **333 reviews/month**, before retries or other credit-consuming operations. Model quotas will impose separate limits. [Tavily pricing](https://docs.tavily.com/documentation/api-credits).

Tavily supports `include_domains` with a restrictive mode. Use the project's existing seven-domain primary-source allowlist, disable automatic parameter selection when budgeting fixed-cost basic searches, and retain search response URLs as provenance. Search results remain candidates until the backend fetches and validates the underlying page. [Tavily Search API](https://docs.tavily.com/documentation/api-reference/endpoint/search).

Suggested sequence:

1. Derive at most three mechanism-focused searches from the analyst's research questions; deterministic query templates can avoid an extra model call.
2. Search the allowed domains and save returned metadata.
3. Fetch and redact pages through the project's bounded HTTPS reader.
4. Ask the extraction LLM for `INCIDENTS` JSON using only those pages.
5. Validate quotes, dates, source IDs, and incident/advisory distinctions as today.

**Gemini 2.5 Flash caveat:** its pricing page still lists free search grounding, but Google's current availability policy restricts 2.5 models to prior active users. It is a conditional option for an existing eligible account, not the default recommendation for a new setup. [Google availability/deprecation policy](https://ai.google.dev/gemini-api/docs/deprecations).

**Open-source search alternative:** self-hosted SearXNG can provide discovery without a paid search subscription. It requires running a service; upstream search availability and blocking still affect results. It does not replace the extraction LLM. [SearXNG documentation](https://docs.searxng.org/).

### Security Reviewer: GPT-OSS-120B

GPT-OSS-120B is my first compact-input reviewer candidate because its role requires multi-step prerequisite comparisons, explicit uncertainty, and disciplined use of evidence. OpenAI documents a 131,072-token context and configurable reasoning. Its training knowledge is not a substitute for retrieved incident sources. [Official OpenAI documentation](https://developers.openai.com/api/docs/models/gpt-oss-120b).

Start with medium reasoning and compare against Qwen3.8-27B and Gemini 3.8 Flash on the same saved handoffs. Choose the model that best rejects weak matches and acknowledges existing controls, even if another model generates more findings or has a higher coding benchmark.

For a free Groq route, construct a compact review packet containing the incident mechanism, prerequisites, validated source passage, relevant observations, existing defenses, and explicit unknowns. Preserve IDs and provenance. Include the original evidence required to evaluate counterevidence; a summary that removes defenses can bias the reviewer.

**Quality challenger:** Nemotron 3 Ultra has a confirmed free OpenRouter endpoint, `nvidia/nemotron-3-ultra-550b-a55b:free`. It provides a large context and tool calling, but its endpoint explicitly does **not** support `response_format`; JSON is not enforced. That is a material disadvantage for the current strict-contract pipeline. Evaluate it only with local validation and a bounded failure policy. [Endpoint details](https://openrouter.ai/nvidia/nemotron-3-ultra-550b-a55b:free).

## What “free” means in practice

| Route | Verified offer or constraint | Decision |
| --- | --- | --- |
| Groq | Recommended three models each show 30 RPM, 1,000 RPD, 8,000 TPM, and 200,000 TPD on the free-plan table; exact account limits may differ. | Strong speed-oriented prototype route with smaller requests. A 25K-token request cannot be assumed to fit an 8K TPM allowance merely because context is 131K. |
| Google Gemini Developer API | Free model tokens are listed for 3.8 Flash; account/model/project quotas remain separate. | First hosted candidate for current larger prompts; pair with separate search. |
| OpenRouter | Free models: 20 RPM and 50 requests/day; 1,000/day after at least $10 of credit purchases. | Useful evaluation/fallback pool. The larger allowance is not a zero-spend offer. |
| Hugging Face Inference Providers | Current pricing lists **no included inference credits for free accounts**. | Use the Hub for discovery and weights; do not budget hosted inference as free. |
| Cerebras | Current pricing advertises a $5 starting credit and pay-as-you-go. | Trial option, not a verified recurring free backbone. |
| Mistral | Free mode has included usage subject to the account's Limits page. | Secondary candidate only after checking model access and actual quota. |

Sources: [Groq free quotas](https://console.groq.com/docs/rate-limits), [Gemini quotas](https://ai.google.dev/gemini-api/docs/rate-limits), [OpenRouter pricing](https://openrouter.ai/pricing), [HF pricing](https://huggingface.co/docs/inference-providers/pricing), [Cerebras pricing](https://www.cerebras.ai/pricing), [Mistral usage policy](https://docs.mistral.ai/admin/billing-usage/usage-limits).

The roles' input and output consumption must fit provider accounting, including reasoning and retries where applicable. Advertised generation speed excludes prompt prefill, search, fetches, queueing, rate-limit waits, and validation. It does not predict this application's completion time.

I checked OpenRouter's live model catalog rather than relying on old free-model lists. Do not assume `qwen/qwen3-coder:free`, `qwen/qwen3.8-27b:free`, or `openai/gpt-oss-120b:free` is available merely because a search result or model-shaped URL exists; I did not establish those exact free routes in the current catalog. Poolside Laguna S/XS 2.1 free routes do appear, but the catalog gives an **October 31, 2026 expiration**, making them poor defaults. [Live catalog](https://openrouter.ai/api/v1/models).

## Local, downloadable alternatives

Local weights avoid a per-token API bill, but use owned hardware, memory, storage, and electricity. No GPU/RAM details were supplied, so these are conditional candidates, not promises of local speed.

| Hardware situation | Candidate | Best use |
| --- | --- | --- |
| Modest GPU or CPU offload | Qwen3.5-9B, quantized | Analyst/extraction prototype; evaluate reviewer accuracy carefully. |
| More memory and a suitable GPU | Qwen3.8-27B, quantized | Primary local analyst; also compare as local reviewer. |
| Around 16 GB available for a model deployment | GPT-OSS-20B, native quantized distribution | Fast local extraction/reasoning candidate; long-context runtime memory needs additional headroom. |
| Larger workstation | Qwen3-Coder-30B-A3B-Instruct | Repository specialist with 3.3B active parameters and non-thinking output. |
| Substantially larger workstation | Qwen3-Coder-Next | 80B total/3B active coding candidate; active parameters do not determine weight storage. |

Qwen3.5-9B and Qwen3-Coder-30B-A3B have native 262,144-token context in their cards; actually allocating that context requires memory beyond weights. At a theoretical four bits per weight, 9B is about 4.5 GB, 27B about 13.5 GB, 30B about 15 GB, and 80B about 40 GB **before** metadata, non-quantized tensors, caches, and runtime overhead. These are weight-only arithmetic estimates, not VRAM requirements.

Sources: [Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B), [Qwen3-Coder-30B-A3B](https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct), [Qwen3-Coder-Next](https://huggingface.co/Qwen/Qwen3-Coder-Next), [GPT-OSS deployment guide](https://developers.openai.com/cookbook/articles/gpt-oss/run-transformers).

Nemotron 3 Ultra's BF16 model card lists multi-GPU server requirements and OpenMDW-1.1 licensing. It is not a typical laptop deployment. Do not assume all downloadable models share Apache 2.0 terms. [NVIDIA model card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16).

No Hugging Face MCP was exposed in this session. Official publisher model cards on the Hub were inspected directly; an MCP connection is not necessary to assess weights, licensing, or model claims.

## Required integration work, if these choices are adopted

Changing `OPENAI_MODEL` alone will not connect these providers. A concrete implementation needs:

1. Per-role provider/model settings and provider-specific credentials, held server-side.
2. A transport adapter translating instructions, strict schemas, output text, token usage, errors, and completion status. Prefer documented Chat Completions schema support for Groq unless Responses parity is separately checked.
3. A search adapter replacing the hard-coded OpenAI `web_search` call and source-metadata parser. Keep candidate URLs tied to actual search responses.
4. Token-aware request sizing, bounded backoff, cancellation, and explicit quota failures. Coordinate retries/chunk calls with the existing six-call and 900-second limits.
5. Preserve all current quote, line, source-ID, date, and evidence checks. Schema-valid JSON does not prove a security conclusion is true.
6. Persist provider and model per call; the current single `validation.model` value cannot accurately describe a mixed-model run.

For the simplest free implementation: evaluate **Gemini 3.8 Flash for all roles plus Tavily**. For the speed-oriented open-weight implementation: evaluate **Qwen3.8-27B → GPT-OSS-20B + Tavily → GPT-OSS-120B**, with explicit input compaction. For local operation: evaluate **Qwen3.8-27B**, adding the smaller extractor only if switching models improves measured throughput.

## How to establish the actual winners

Run a small controlled evaluation before selecting production defaults. Use identical repository snapshots and saved source documents so retrieval variability does not distort the model comparison. Include authentication, uploads/path traversal, outbound requests, CI/CD/supply chain, and examples with effective defenses already present.

Measure:

- First-attempt contract validity and accepted exact quotations.
- Correct technology/version interpretation and coverage limitations.
- Correct incident mechanisms, prerequisites, dates, and source passages.
- Unsupported-concern rate, missed defenses, and appropriate abstention.
- Invalid IDs and false Supported concern classifications.
- Median/p95 stage latency, total tokens, retries, quota failures, and completed reviews/day.

Include adversarial source text, loose dependency version ranges, irrelevant incidents sharing the same framework, and insufficient evidence. Require human review of findings to measure semantic accuracy; the existing validators establish reference integrity. The project's synthetic demo is a useful contract fixture, but cannot establish real-world security performance.

This research supports a shortlist and an integration decision. A project-specific quality or latency ranking remains unmeasured.
