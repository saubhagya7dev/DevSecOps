"""Explicit live smoke checks; no repository code, prompts, or credentials are printed."""
import os
import time

from . import contracts
from .config import ROLE_MODELS
from .network import FetchError, get_json
from .providers import ModelClient


def check_apis(report=print):
    """Check every integration independently. Return nonzero if any fails or lacks a key."""
    client = ModelClient(lambda *args: None, lambda: None)
    results = []

    def check(name, operation, credential=None):
        started = time.monotonic()
        if credential and not os.getenv(credential, '').strip():
            status, detail = 'MISSING', f'Set {credential} in .env or the server environment.'
        else:
            report(f'Checking {name} ...', flush=True)
            try:
                detail = operation()
                status = 'PASS'
            except (ValueError, OSError) as exc:
                status, detail = 'FAIL', str(exc)
            except Exception:
                # Unexpected objects/provider bodies must never be printed.
                status, detail = 'FAIL', 'Unexpected response. Check provider connectivity and compatibility.'
        elapsed = round(time.monotonic() - started, 2)
        results.append({'integration': name, 'status': status, 'detail': detail, 'seconds': elapsed})
        report(f'[{status}] {name} ({elapsed:.2f}s): {detail}', flush=True)

    expected = {
        'analyst': (contracts.PROFILE, {'summary': 'ok', 'technologies': [], 'components': [],
                                      'observations': [], 'research_questions': [], 'unknowns': []}),
        'researcher': (contracts.INCIDENTS, {'incidents': [], 'research_limitations': []}),
        'reviewer': (contracts.REVIEW, {'summary': 'ok', 'findings': [], 'existing_defenses': [],
                                      'rejected_matches': [], 'questions': [], 'followup_requests': []}),
    }
    report('Live API checks: three small model requests, one Tavily search, and one GitHub request. Provider charges may apply.', flush=True)
    for role, (schema, value) in expected.items():
        settings = ROLE_MODELS[role]

        def model_check(role=role, schema=schema, value=value):
            result = client.call(role, 'This is an API connectivity test. Return exactly the expected JSON '
                                 'object supplied in expected_response, matching the schema. Do not analyze or research.',
                                 {'expected_response': value}, schema, max_output_tokens=2048)
            if result != value:
                raise ValueError('API returned JSON, but the expected smoke-test response did not match.')
            return 'Authentication, inference, and the role JSON contract passed.'

        check(f"{role}: {settings['provider']} / {settings['model']}", model_check, settings['credential'])

    def search_check():
        # No date window: test retrieval independently of publication coverage.
        response = client.search('CISA known exploited vulnerabilities catalog', ['cisa.gov'], None, None)
        from .agents import search_sources
        candidates = search_sources(response)
        if response['results'] and not candidates:
            raise ValueError('Tavily returned results but none passed the primary-source URL filter.')
        return f'Authentication and search passed; {len(candidates)} eligible result(s). Empty results do not prove coverage.'

    check('Tavily search', search_check, 'TAVILY_API_KEY')

    def github_check():
        headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}
        token = os.getenv('GITHUB_TOKEN', '').strip()
        if token:
            headers['Authorization'] = f'Bearer {token}'
        try:
            result = get_json('https://api.github.com/repos/octocat/Hello-World', headers=headers,
                              timeout=35, limit=100_000)
        except FetchError as exc:
            raise ValueError(f'GitHub API request failed: {exc}') from exc
        if not isinstance(result, dict) or result.get('full_name') != 'octocat/Hello-World':
            raise ValueError('GitHub returned unexpected repository metadata.')
        return 'Public repository metadata readable' + (' with configured GitHub token.' if token else ' without a token.')

    check('GitHub API', github_check)
    passed = sum(result['status'] == 'PASS' for result in results)
    report(f'\n{passed}/{len(results)} integrations passed. This is a connectivity smoke test, not a full repository review.', flush=True)
    return results
