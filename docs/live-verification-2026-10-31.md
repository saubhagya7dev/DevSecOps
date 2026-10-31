# Live integration verification — 2026-10-31

Four public repositories were run sequentially through the final static, read-only pipeline. Each final run made one actual hosted call per role: Gemini `gemini-3.5-flash-lite`, Groq `qwen/qwen3.8-27b`, and Groq `openai/gpt-oss-120b`. No model response was mocked or replayed in this final run. Target code was never executed.

Tavily was exercised live during preceding discovery/retest runs. The final run reused eligible search metadata from the local cache; page and structured-source cache hits are recorded separately. This is not a claim that every connector made a fresh network request in every final run.

| Repository | Pinned commit | Live roles completed | Research estimate including output | Final status | Accepted findings |
| --- | --- | --- | --- | --- | --- |
| Vision--Document_Intelligence_RAG_pipeline | `69291e73282d` | 3/3 | 911 / 1,000 | partial | 0 |
| ISA--Object_Detection_HUD_for_Rescue_Operations | `b02182ad50e9` | 3/3 | 890 / 1,000 | completed | 0 |
| SwarmSim | `1efc4da25727` | 3/3 | 886 / 1,000 | partial | 0 |
| DevSecOps | `2882026d0ed9` | 3/3 | 908 / 1,000 | completed | 0 |

All twelve final role requests succeeded with no HTTP 429/503 retries and no local token-fit rejection. RAG and SwarmSim remained **partial** because two repository citations each failed exact verification and were removed. ISA and DevSecOps completed without validation warnings. An accepted external source record is not an applicable incident, confirmed vulnerability, or evidence of target compromise.

## What was fixed

- The previous full extraction schema/instructions could not fit the configured 1,000-token allowance. Low-quota mode now uses deterministic search planning plus a compact source-interpretation contract with a 192-token output reserve. The configured allowance was not increased.
- Python supplies the source identity and the exact passage actually sent to Qwen; full-contract expansion and quote validation remain mandatory. Unknown dates and victims stay unknown.
- A broader bounded third discovery query can run after empty eligible results; search/extraction cache versions invalidate the incompatible earlier requests.
- Reviewer context retains complete accepted quotations (up to 800 characters), and instructions require rejecting contradicted or debunked vulnerability claims. A separate live recheck of the previously misleading SQLite report returned zero findings and explicitly rejected its disputed CVEs.

## Remaining quality limits

API access is working; incident relevance is not established by these tests. All four final reviews returned zero accepted findings. RAG retrieved a PHP advisory despite its Python/FastAPI stack, ISA retrieved SMB ransomware material, and SwarmSim retrieved macOS backdoor background. These are weak matches. The low-quota mode interprets only one selected passage per batch and leaves dates/victims unknown. Source-category interpretation can also be wrong: Qwen labeled the PHP advisory as an observed attack despite the limited excerpt. Citation validation verifies retained text and identifiers, not semantic truth.

The final runs therefore establish that all roles can execute within this account configuration. They do **not** establish useful coverage, reliable incident classification, or absence of security risks. Do not force recommendations merely to produce nonempty output.

## Reproduce

Run from the project directory with configured server-side credentials. This command consumes hosted API quota, uses the production pipeline and its normal caches, and writes status, role usage, coverage, JSON artifacts, Markdown reports, and SQLite events under the ignored output directory. A partial/failed run gives a nonzero exit code.

```powershell
python tools/verify_repositories.py --live --output test-output/recheck `
  https://github.com/saubhagya7dev/Vision--Document_Intelligence_RAG_pipeline `
  https://github.com/saubhagya7dev/ISA--Object_Detection_HUD_for_Rescue_Operations `
  https://github.com/saubhagya7dev/SwarmSim `
  https://github.com/saubhagya7dev/DevSecOps
```

Final-run artifacts for this session: `test-output/four-repository-final/summary.json`, one `.json` and `.md` per repository, and `reviews.sqlite3`. The separate disputed-advisory recheck is `test-output/contradicted-advisory-live.json`. Runtime artifacts remain local and ignored by Git.

Offline verification: **97 tests pass** (`python -m unittest discover -q`). Restart `python run.py` and start a new analysis to load the changed code; existing saved job errors are historical artifacts and are not rewritten.
