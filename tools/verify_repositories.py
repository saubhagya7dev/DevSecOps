"""Run real repository reviews sequentially; never execute the target repositories."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from devsecops.config import missing_credentials
from devsecops.pipeline import Runner
from devsecops.store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repositories', nargs='+', help='Public GitHub repository URLs')
    parser.add_argument('--live', action='store_true', required=True,
                        help='Use configured hosted APIs; consumes account quota')
    parser.add_argument('--days', type=int, default=180)
    parser.add_argument('--output', type=Path, default=ROOT / 'test-output' / (
        'live-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')))
    args = parser.parse_args()
    if missing_credentials():
        parser.error('Missing credentials: ' + ', '.join(missing_credentials()))
    args.output.mkdir(parents=True, exist_ok=True)
    store = Store(args.output / 'reviews.sqlite3')
    original_emit = store.emit

    def emit(job_id, stage, title, detail=''):
        print(f'[{stage}] {title}: {detail}', flush=True)
        return original_emit(job_id, stage, title, detail)

    store.emit = emit
    runner = Runner(store, demo_delay=0)
    results = []
    try:
        for url in args.repositories:
            print(f'Reviewing {url}', flush=True)
            job = store.create(url, 'live', args.days)
            runner.run(job['id'])
            result = store.get(job['id'])
            artifacts = result['artifacts']
            validation = artifacts.get('validation', {})
            research = artifacts.get('research', {})
            summary = {'repository': url, 'job_id': job['id'], 'status': result['status'],
                       'stages': result['stages'], 'error': result['error'],
                       'commit': artifacts.get('repository', {}).get('commit'),
                       'live_role_usage': validation.get('role_usage', {}),
                       'incidents': len(research.get('incidents', [])),
                       'findings': len(artifacts.get('review', {}).get('findings', [])),
                       'research_error': research.get('error', ''),
                       'coverage': research.get('coverage', {}),
                       'validation_warnings': validation.get('warnings', [])}
            results.append(summary)
            (args.output / (job['id'] + '.json')).write_text(json.dumps(artifacts, indent=2), encoding='utf-8')
            (args.output / (job['id'] + '.md')).write_text(result.get('report', ''), encoding='utf-8')
            (args.output / 'summary.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
            print(json.dumps(summary), flush=True)
    finally:
        runner.pool.shutdown(wait=True)
    print(f'Results: {args.output.resolve()}')
    # Partial output, skipped roles, cached extraction, and zero findings are distinguishable in summary.json.
    return 0 if all(item['status'] == 'completed' for item in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
