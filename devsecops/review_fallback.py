"""Explicit local verification suggestions when hosted review cannot supply findings."""
import re

CHECKS = [
    (r'url|request|http|fetch|proxy', 'Check outbound request boundaries',
     'Trace callers of the cited request behavior. Confirm destination allowlists, redirect validation, private-network restrictions, and timeouts before changing existing controls.',
     'Review the cited code and caller tests for rejected private destinations, redirects, and timeouts; run any tests only in a separately authorized environment.'),
    (r'auth|token|session|jwt|login', 'Verify authentication and authorization boundaries',
     'Trace the cited authentication or token behavior to its entry points. Check expiry, authorization per operation, and server-side validation while preserving existing defenses.',
     'Inspect authentication and authorization tests for expired credentials and cross-user access; record any missing deployment context.'),
    (r'pickle|yaml|deserial|upload|archive|path', 'Review untrusted input handling',
     'Trace how external data reaches the cited parser or file operation. Check safe parsing, size limits, schema validation, and path confinement where applicable.',
     'Inspect the relevant code and tests for malformed input, oversized data, and path traversal; establish which inputs are actually untrusted.'),
    (r'secret|password|credential|api.key', 'Review credential handling',
     'Inspect how the cited credential-related behavior loads, scopes, and redacts sensitive values; verify that logs and client responses cannot disclose them.',
     'Review configuration and logging paths using dummy credentials; document rotation and deployment responsibilities without exposing real values.'),
    (r'dependen|package|requirements|npm|pip', 'Review dependency reproducibility',
     'Check the cited dependency configuration for reproducible resolution, integrity verification where supported, and a documented update process.',
     'Inspect manifests, lockfiles, and CI policy; distinguish declared version ranges from actual installed versions.'),
]


def repository_fallback(profile, reason='No accepted recommendations were returned by the hosted reviewer.'):
    findings, used = [], set()
    for observation in profile['observations']:
        if observation['kind'] != 'observed':
            continue
        text = re.sub(r'https?://\S+', '', observation['claim'] + ' ' + observation['quote'], flags=re.I)
        text = observation['path'] + ' ' + text
        # A manifest declaring a parser is dependency evidence, not evidence of parser execution.
        manifest = re.search(r'(?:^|/)(?:requirements[^/]*\.txt|pyproject\.toml|package(?:-lock)?\.json)$', observation['path'])
        checks = [CHECKS[-1], *CHECKS[:-1]] if manifest else CHECKS
        for pattern, title, action, verification in checks:
            if title in used or not re.search(pattern, text, re.I):
                continue
            used.add(title)
            findings.append(make_finding(observation, title, action, verification, len(findings) + 1))
            break
        if len(findings) == 3:
            break
    if not findings:
        observed = next((o for o in profile['observations'] if o['kind'] == 'observed'), None)
        if observed:
            findings.append(make_finding(observed, 'Document and verify component trust boundaries',
                'Trace the cited behavior to its inputs, callers, and privileges. Document trust boundaries and verify existing validation and access controls before proposing a change.',
                'Inspect entry points and tests associated with the cited file; list which controls and deployment boundaries remain unverified.', 1))
    return {'summary': 'Local repository verification suggestions are provided; these do not establish a vulnerability or an incident connection.',
            'findings': findings, 'existing_defenses': [], 'rejected_matches': [],
            'questions': [reason, 'Confirm deployment entry points, trust boundaries, and existing security tests.'] +
                         ([] if findings else ['No direct repository observations passed citation checks; provide inspectable code evidence before requesting specific changes.']),
            'followup_requests': [], 'origin': 'local verification fallback'}


def make_finding(observation, title, action, verification, number):
    return {'id': f'R{number}', 'title': title, 'classification': 'Repository improvement',
            'impact': 'Low', 'confidence': 'Low', 'incident_ids': [], 'evidence_ids': [observation['id']],
            'mechanism': 'Defensive repository review; no external attack is asserted.',
            'prerequisite': 'Confirm how the cited behavior is reached and protected in deployment.',
            'reasoning': f"Verification scope: {observation['path']}: {observation['claim']}",
            'counterevidence': 'Existing controls may already address this check; their absence is not established.',
            'missing_information': ['Runtime reachability and the effectiveness of existing controls remain unverified.'],
            'prerequisite_assessments': [], 'action': action, 'verification': verification}
