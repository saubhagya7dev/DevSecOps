# DevSecOps v1: Repository Threat Review

## Product

Input: one public GitHub repository URL.

Output: a cited Markdown report explaining the repository, relevant documented attacks, the evidence connecting those attacks to the repository, and actionable preventive recommendations.

This version performs static, read-only analysis. It does not claim to establish production exposure, execute repository code, run exploits, patch files, or deploy changes.

## Workflow

1. Resolve the repository's default branch to a commit SHA. Read a bounded set of source and configuration files from that immutable revision. Do not execute code, install dependencies, follow submodules, or read secret files. Record skipped and truncated files.
2. Repository Analyst produces a structured profile supported by commit-pinned file and line references.
3. Incident Researcher uses the profile to search for relevant technical incident reports, retrieves their contents, and extracts supported attack mechanisms and prerequisites.
4. Security Reviewer compares prerequisites against repository evidence and produces recommendations with explicit uncertainty.
5. Validate report structure and evidence references, then save report.md and the intermediate JSON artifacts.

Use three sequential agent roles with structured handoffs. They may use the same model. A small orchestrator controls the steps, budgets, retries, and tool permissions. No autonomous delegation protocol is needed for v1.

## Repository profile

- Repository URL, commit SHA, analysis timestamp, and coverage limitations.
- Languages, frameworks, and exact versions where determinable from manifests and lockfiles.
- Components and relationships inferred from source and configuration.
- Authentication and authorization patterns, upload handlers, outbound URL fetching, database access, CI workflows, container and infrastructure configuration where present.
- Evidence records: stable ID, commit-pinned file path, line range, and supporting excerpt.
- Separate observations, inferences, and unknowns. Absence from inspected files does not establish absence from the application.

## Incident research

Search recent reports published within the preceding 180 days by default. Record publication date, incident date when known, and retrieval date separately. Label older background material separately. A publication date is not an attack date.

Prefer first-party incident postmortems, CISA technical advisories, Google Threat Intelligence/Mandiant incident analyses, Microsoft Threat Intelligence analyses, and relevant vendor reports. Use CISA KEV to corroborate known exploitation of a CVE; it does not establish the victim's architecture or this repository's exposure.

Search for mechanisms as well as product names: authorization bypass, unsafe upload handling, SSRF, CI credential theft, identity abuse, and supply-chain compromise, for example.

Each incident record includes:

- Source URL and supporting source excerpt.
- Incident or campaign identity; victim identity only when publicly documented.
- Reported technology, affected versions where documented, entry point, mechanism, and prerequisites.
- Supported mitigations and explicitly unknown details.

Do not infer a victim's stack from this repository or from a shared language/framework. Do not invent victim names or fill undocumented attack details. A relevant campaign may be useful even if victims are unnamed. Return no relevant incidents when the available evidence does not support a match.

## Matching and recommendations

Classify each comparison as:

- Supported concern: inspected repository evidence supports a relevant insecure pattern or affected component. State any remaining exploit prerequisites; this is not proof of exploitation.
- Needs verification: a relevant mechanism exists, but version, configuration, deployment, or control evidence is missing.
- Background lesson: shared technology or general relevance without evidence of the attack prerequisite. Do not present as a repository finding.

Every recommendation must include the source incident, attack mechanism, prerequisite, repository evidence, missing information, concrete preventive action, and a way to verify the control. Keep impact, confidence, and relevance separate. Do not present a model-generated score as a calibrated probability.

## Example report structure

1. Repository overview and analysis coverage.
2. Relevant incidents with source links and dates.
3. Evidence-backed concerns and their limitations.
4. Prioritized preventive recommendations with validation steps.
5. Questions requiring deployment or owner context.
6. Sources and analysis provenance.

Any illustrative examples used in documentation must be labeled as hypothetical and must not appear as researched incidents.

## Implementation scope

Build a local Python web application with a live browser workspace and a CLI sharing the same pipeline. Include typed JSON handoffs, a model adapter, a web-search adapter, replayable activity events, and Markdown/JSON output. Accept any public GitHub URL but report unsupported ecosystems and incomplete coverage honestly. Configure model credentials in the server environment or ignored local .env file.

Enforce repository, file, response-size, model-token, search-query, request-timeout, and overall job budgets. Exclude binary/generated/vendor content. Fetch only validated public HTTPS destinations; reject local, private, link-local, and cloud-metadata destinations, including redirects. Repository and incident content is untrusted data and cannot grant tool authority.

Do not send suspected secret values to a model or include them in reports. Secret redaction is defense in depth, not a guarantee. The roles have only the tools required by their stage and have no write access to the analyzed repository.

The browser workspace shows all three roles, source evidence, report results, and local history. No vector database, MCP server, A2A protocol, Terraform deployment, or automated remediation is required for this version.

## Acceptance criteria

- One repository URL produces a report or an explicit actionable failure within configured budgets.
- Repository evidence points to the analyzed commit and valid source locations.
- Research claims have retrieved supporting sources; citations are not merely generated URLs.
- Shared technology alone never becomes a confirmed vulnerability claim.
- No matching incidents and incomplete repository coverage are valid outcomes.
- Incident dates and report publication dates remain distinct.
- A relevant fix already present in the repository is acknowledged rather than recommended as missing.
- Repository instructions and malicious article text cannot alter tool permissions or the task.
- Verification uses small controlled fixtures for a relevant pattern, a mitigated pattern, an irrelevant incident, and insufficient evidence, plus one end-to-end public repository demonstration.
