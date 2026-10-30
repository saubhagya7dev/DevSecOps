# Gemini HTTP 503 during repository analysis

Gemini's model-metadata endpoint being reachable does not establish inference availability. Likewise, a tiny successful inference request does not establish that a full repository snapshot will work.

The client now retries HTTP 503 once, within the existing two-attempt per-request and three-retry per-job ceilings. A numeric `Retry-After` up to 60 seconds is honored; when absent, a randomized 1–3 second wait is used. Longer reset windows are not ignored. Waiting checks cancellation and the overall job deadline. No authentication failures, invalid requests, exhausted daily quotas, or oversized requests are blindly retried.

If both attempts fail, the error identifies provider unavailability rather than implying that credentials or repository code are necessarily wrong. The inspected repository artifact remains saved. No successful profile is invented and no incident/reviewer work proceeds without a validated profile. The configured model remains unchanged.

For persistent failures, retry later or explicitly choose another supported Analyst model in `.env` using `ANALYST_MODEL`, then restart `python run.py`. This is a user configuration choice, not an automatic fallback. Larger requests and tiny controls should be tested separately before concluding that a model is usable for this application.

The retry policy follows [Google's Gemini troubleshooting guidance](https://ai.google.dev/gemini-api/docs/troubleshooting). Retries cannot guarantee recovery from provider-side outages or capacity problems.

## Observed diagnostic results

On the configured Gemini 3.6 Flash model, a tiny full-schema control succeeded, while a saved 30,789-character repository snapshot and an 8,252-character reduced view both received 503 on both attempts. A reduced-view probe with a smaller output allowance returned an incomplete or invalid handoff, not an accepted profile. A tiny control on the originally requested Gemini 3.8 model timed out. No model configuration was changed.

These samples do not prove that input size caused the errors, and no production context reduction was introduced without a successful validation. Full Analyst reliability remains unverified. The fix addresses immediate-stop retry behavior, not provider-side capacity.
