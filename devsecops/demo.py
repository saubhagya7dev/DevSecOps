"""Synthetic offline fixtures. These are NOT real incidents or repository findings."""
from .contracts import validate_shape, PROFILE, INCIDENTS, REVIEW

DEMO_URL = 'https://github.com/example-labs/preview-service'


def fixture():
    content = 'import requests\n\ndef preview(url):\n    return requests.get(url, timeout=5).text\n'
    repo = {'url': DEMO_URL, 'name': 'example-labs/preview-service', 'commit': '0' * 40,
            'description': 'SYNTHETIC EXAMPLE — not an actual GitHub repository', 'language': 'Python',
            'files': [{'path': 'app/preview.py', 'content': content, 'truncated': False,
                       'url': DEMO_URL + '/blob/' + '0' * 40 + '/app/preview.py'}],
            'tree_paths': ['app/preview.py'], 'skipped': [],
            'coverage': {'files_read': 1, 'files_in_tree': 1, 'eligible_files': 1, 'files_skipped_by_budget_or_error': 0,
                         'truncated_files': 0, 'tree_truncated': False, 'characters_read': len(content)}}
    profile = {'summary': 'Illustrative Python preview service that fetches a caller-provided URL. This offline fixture demonstrates the workflow; no real repository was inspected.',
               'technologies': [{'name': 'Python / Requests', 'version': 'Unknown in this fixture', 'evidence_ids': ['E1']}],
               'components': [{'name': 'Preview fetcher', 'description': 'Performs an outbound HTTP request using the supplied URL.', 'evidence_ids': ['E1']}],
               'observations': [{'id': 'E1', 'claim': 'The preview function passes its URL argument into an outbound request.',
                                 'path': 'app/preview.py', 'start_line': 3, 'end_line': 4,
                                 'quote': 'def preview(url):\n    return requests.get(url, timeout=5).text', 'kind': 'observed'}],
               'research_questions': ['Which SSRF attack prerequisites should a URL-preview feature defend against?'],
               'unknowns': ['Caller authentication, route exposure, URL validation upstream, and outbound network policies are unknown.']}
    passage = 'In this fictional training scenario, an attacker supplied an internal destination to a URL-preview feature. The server fetched that destination using its own network access.'
    research = {'incidents': [{'id': 'I1', 'title': 'Illustrative SSRF scenario — fictional', 'source_id': 'S1',
                               'source_quote': passage, 'publication_date': 'unknown', 'incident_date': 'unknown',
                               'victim': 'Fictional training service', 'source_type': 'background guidance',
                               'mechanism': 'Server-side request forgery through an attacker-controlled URL.',
                               'prerequisites': ['Attacker controls the requested destination.', 'Server can reach a sensitive destination.'],
                               'technologies': ['Outbound HTTP client'], 'mitigations': ['Destination validation and network restrictions.'],
                               'unknowns': ['No real incident is represented.']}],
                'sources': [{'id': 'S1', 'title': 'Synthetic local training passage — not a published incident',
                             'url': 'https://example.org/fictional-training-only', 'text': passage,
                             'retrieved_at': 'Offline fixture; no network request'}],
                'research_limitations': ['OFFLINE EXAMPLE: all repository and incident content in this run is synthetic.']}
    review = {'summary': 'One prerequisite deserves verification in this hypothetical example. No exploitability claim is established.',
              'findings': [{'id': 'F1', 'title': 'Verify URL destination controls', 'classification': 'Needs verification',
                            'impact': 'High', 'confidence': 'Medium', 'incident_ids': ['I1'], 'evidence_ids': ['E1'],
                            'mechanism': 'A server fetches an attacker-selected destination.',
                            'prerequisite': 'Untrusted input reaches this function and sensitive destinations are reachable.',
                            'reasoning': 'The function uses the URL directly, but the fixture does not show its callers or network boundary.',
                            'counterevidence': 'A request timeout exists; upstream destination validation may also exist but is not shown.',
                            'missing_information': ['Input trust boundary', 'Upstream validation', 'Outbound network policy'],
                            'action': 'Inspect callers and validate destination policy, redirects, and resolved addresses; restrict outbound access where appropriate.',
                            'verification': 'In an isolated environment, test that prohibited destinations and redirect targets are rejected while permitted URLs still work.'}],
              'existing_defenses': [{'description': 'The HTTP request sets a five-second timeout.', 'evidence_ids': ['E1']}],
              'rejected_matches': [], 'questions': ['Is this function reachable from an untrusted request?'], 'followup_requests': []}
    validate_shape(profile, PROFILE)
    validate_shape({k: research[k] for k in ('incidents', 'research_limitations')}, INCIDENTS)
    validate_shape(review, REVIEW)
    return repo, profile, research, review
