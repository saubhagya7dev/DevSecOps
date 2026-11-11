# Architecture hardening — 11 November 2026

The application retains its local, single-user, standard-library design. These changes address the review's concrete lifecycle, storage, update, and evidence-policy defects without introducing a distributed service or replacing the frontend framework.

## Changes mapped to the review

| Finding | Implemented resolution |
| --- | --- |
| C1: recovery could invalidate another process's work | OS-backed exclusive ownership acquired before storage initialization by server, CLI review, maintenance and batch entry points. Server recovery follows successful port binding. Locks are released by the OS after process exit/crash. |
| W1: history pagination controlled lifecycle decisions | Indexed active queries scan all relevant jobs. Capacity check and job creation share a write transaction. History supports independent `limit`/`before` pagination. |
| W2: full JSON payload read/write amplification | Versioned migration separates job metadata, artifact payloads and report text; payload tables reference jobs with cascading deletes. Routine status, history, checkpoint and stage operations avoid payload reads. Artifact format versions are persisted. |
| W3: queue blocking and cancellation | Queued cancellation is immediate. On dequeue, jobs waiting more than 900 seconds fail before provider calls. A separate 900-second execution deadline is propagated into network requests; response reads check cancellation. Queue and stage timings are retained. One worker and the five-active-job ceiling remain deliberate local limits. |
| W4: full-job refreshes and stale responses | Small `/status` responses carry monotonic job/payload revisions. The frontend coalesces concurrent requests, fetches evidence only when needed, and rejects older responses. Local HTTP connections are capped at 16 with 10-second socket timeouts. |
| W5: concentrated responsibilities | `ReviewServices` injects workflow dependencies; `reporting.py` isolates Markdown presentation; `execution.py` isolates deadline/cancellation context; `job-updates.js` isolates refresh state from DOM rendering. Existing module imports remain compatible. |
| W6: migrations, retention and cache writes | Transactional migration with atomic pre-upgrade backup, future-schema rejection, explicit SQLite backup and terminal-history pruning. Cache temporary filenames are unique per write, including threads. |
| W7: classifications relied on prompt compliance | New reviews require structured prerequisite assessments. Unknown/incomplete prerequisites downgrade a concern; referenced contradictions reject it and preserve rejection reasons. Legacy reviews remain readable. |
| Configuration, diagnostics and DX | Explicit startup configuration with pure immutable settings parsing; safe error logs identify job/stage/exception type without request content; timing metrics; matching `0.1.8` package metadata; CI for offline regression tests. |

## Storage and upgrade behavior

Schema version 1 uses `jobs(id, data, status)`, `artifacts(job_id, key, schema_version, data)`, `reports(job_id, content)` and `events(seq, job_id, data)`. Status is indexed, and event replay keeps its original sequence IDs. Small stage dictionaries remain within job metadata; stage writes are atomic. New review artifacts use schema version 2 because they contain prerequisite assessments.

Stop any previously running version before upgrading. The first launch upgrades legacy history and retains `reviews.sqlite3.v0.bak` in the data directory. Failed migrations roll back. Downgrading requires restoring the pre-upgrade backup in a fresh directory while the application is stopped. Backups contain retained source/evidence and require the same access protection as history.

```powershell
python run.py --backup test-output/reviews-backup.sqlite3
python run.py --prune-before "2026-01-01T00:00:00+00:00" --confirm-prune
```

Backup refuses existing destinations and the live database/sidecar names. Retention never deletes active jobs; related reports, artifacts and events are removed with terminal investigations. No automatic retention policy removes user history.

The server, CLI and maintenance commands cannot operate concurrently on the same data directory. Batch verification uses its own output directory and takes an ownership lock there. Library integrations must call `config.configure()` before importing adapters and acquire `InstanceLock` before owning storage/recovery. Configuration changes require a restart.

## Verification

Local verification completed on Windows with Python 3.15:

- 140 Python tests passed, including HTTP integration and mocked provider workflows.
- 34 JavaScript tests passed, including revision ordering and concurrent refresh coordination.
- Python compilation and JavaScript syntax checks passed.
- An isolated subprocess ran the offline CLI, generated a report and evidence, backed up history, rejected unconfirmed pruning, and successfully performed explicitly confirmed terminal-history pruning. No hosted model/search requests occurred.
- Regression tests cover a second owner, port-bind failure, recovery beyond the latest 50 jobs, concurrent admission/stage writes, migration preservation/rollback, backup restoration readability, future-schema rejection, and prerequisite contradictions.
- A synthetic 100,000-character evidence fixture serialized to 100,475 bytes as a full job and 419 bytes as metadata: 99.58% fewer bytes for status. This is a payload-size comparison, not a production load or latency benchmark.

The CI workflow adds Windows/Linux and Python 3.11/3.13 coverage with Node 24. Action dependencies are pinned to public tag-resolved commit IDs, use read-only repository permissions and do not persist checkout credentials. CI execution requires pushing the commits; the remote matrix has not been run locally. Provider compatibility/availability and paid live analysis were not retested.

## Remaining boundaries and trade-offs

- This remains a loopback application for a trusted local user. Multi-user authentication, per-user authorization, distributed queues, leases and cross-host storage require a separate deployment design. They have not been added by exposing this server to a network.
- Bounded concurrency protects the current application, but does not claim 10× throughput. Measure the new stage/queue timings against actual workload and provider quotas before increasing workers. SQLite remains a single-host store; researcher pacing remains process-local.
- Cancellation is cooperative. DNS resolution and already-blocked socket operations can delay a checkpoint; there is no promise of forcefully terminating a thread at an exact deadline. A queued job's wait limit is evaluated when the worker reaches it.
- Citation and prerequisite checks verify structural policy, not semantic truth. Model interpretation and human verification remain necessary.
- The frontend retains its existing view composition and vanilla JavaScript; backend provider adapters remain together. Further splitting should follow actual feature ownership and change frequency. A directory-only rewrite or new framework would add migration cost without correcting the confirmed defects.
- Existing user README edits were preserved separately from these commits. Existing runtime history was not migrated or cleared during verification; tests used disposable directories.
