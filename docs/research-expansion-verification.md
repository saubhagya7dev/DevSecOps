# Broader discovery and repository review — 11 November 2026

## Baseline and changes

Commit `fa1683f` records version **0.1.9** before implementation. Later commits add six-request recent/historical/guidance discovery, more eligible primary publishers, visible query coverage, and a Security Reviewer that remains active without incident evidence.

Low-quota queries now diversify technologies rather than requiring multiple stacks in the same report. README badge URLs do not imply SSRF. A background/advisory result cannot stop historical searches, and the second extraction selects previously unsubmitted pages. Researcher token allowances, six page-fetch attempts, two extraction calls, and the six-call model ceiling remain bounded.

Repository improvement findings require valid code citations, concrete actions, and safe verification steps. They cannot carry incident IDs or claim attack prerequisites. Other classifications still require external evidence. Empty or failed hosted reviews can receive explicitly local verification suggestions; no accepted direct code observations yields questions instead of invented citations.

## Regression verification

- **161 Python tests passed**, including broadened queries, source eligibility, historical discovery after background-only evidence, explicit search failures, code-only review, scope/citation rejection, partial results, and bounded structured-generation retry.
- **46 JavaScript tests passed**, including recommendations remaining visible after incident failure and escaped reviewer text.
- Python compilation, frontend syntax, and Git whitespace checks passed.

```sh
python -m unittest discover -q
node --test tests/test_*.cjs
node --check web/app.js
```

These are local regression results, not a relevance benchmark or proof that recommendations are correct.

## Live verification and limits

Target: `saubhagya7dev/SwarmSim`, commit `1efc4da25727998157ea9abfa63b4f004ea237c3`.

1. A fresh end-to-end CLI run read the public repository but Gemini returned HTTP 503 on both allowed attempts. It stopped before research; this was not counted as successful end-to-end verification.
2. To isolate discovery/review, a previously saved public snapshot/profile was loaded read-only and its eight code observations revalidated against the retained files. Real Tavily/Groq requests then exercised the changed stages. No synthetic incident was substituted.
3. The first pass exposed an overbroad query trigger from README URLs and a structured-output HTTP 400. The Reviewer nevertheless produced four repository-only suggestions and a partial report. The query trigger and schema-mode handling were corrected.
4. The corrected pass issued six distinct query plans: two recent, three historical, and one guidance. One query used cached metadata, so five Tavily requests were made. Six pages were retrieved and two extractions accepted an advisory/background record and an observed attack record from [Mandiant's 3CX supply-chain investigation](https://cloud.google.com/blog/topics/threat-intelligence/3cx-software-supply-chain-compromise). This establishes acquired external evidence, not a connection to SwarmSim.
5. The Reviewer initially encountered a generation failure. A reviewer-only check reused the acquired evidence and recovered on its single allowed retry. A bounded follow-up then succeeded, but re-review exhausted the current token-per-minute allowance. The prior assessment/report survived, the unresolved question remained visible, and the run stayed partial. One recommendation with an incomplete evidence chain was rejected locally.

Local receipts are retained in ignored `test-output/research-expansion-verification/`: `initial-result.json`, `result.json`, and `reviewer-retry-result.json`, with corresponding Markdown reports. These snapshots are for local inspection and are not bundled as product examples.

Groq structured-generation failures retain only a fixed safe error code. Known generation errors can retry once within shared budgets; generic HTTP 400 errors do not retry. Provider response bodies and failed generated text are not exposed. See [Groq's structured-output documentation](https://console.groq.com/docs/structured-outputs).

New investigations use the updated behavior after restarting the local server. Existing saved investigations are not rewritten. Broader search can use more search credits and still cannot guarantee a relevant incident for every repository.
