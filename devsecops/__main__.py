import argparse
import os
import sys
import time
from pathlib import Path

from .config import load_env


def main():
    load_env()
    parser = argparse.ArgumentParser(description='Incident-informed repository review: local UI or CLI.')
    parser.add_argument('--port', type=int, default=int(os.getenv('PORT', '8765')))
    parser.add_argument('--repo', help='Analyze a public GitHub URL directly from the CLI')
    parser.add_argument('--demo', action='store_true', help='Run the clearly labeled synthetic offline example via CLI')
    parser.add_argument('--output', default='test-output/report.md')
    args = parser.parse_args()
    if not args.repo and not args.demo:
        from .server import serve
        serve(args.port)
        return
    from .demo import DEMO_URL
    from .pipeline import Runner
    from .repository import parse_repo
    from .store import Store
    repo = DEMO_URL if args.demo else args.repo
    parse_repo(repo)
    if not args.demo and not os.getenv('OPENAI_API_KEY'):
        parser.error('Set OPENAI_API_KEY before starting a live analysis.')
    store = Store()
    job = store.create(repo, 'demo' if args.demo else 'live', 180)
    runner = Runner(store, demo_delay=0)
    future = runner.submit(job['id'])
    after = 0
    try:
        while not future.done():
            for event in store.events(job['id'], after):
                print(f"[{event['stage']}] {event['title']}: {event['detail']}", flush=True)
                after = event['seq']
            time.sleep(0.2)
        future.result()
        result = store.get(job['id'])
        if not result['report']:
            print(result['error'] or result['status'], file=sys.stderr)
            sys.exit(1)
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(result['report'], encoding='utf-8')
        output.with_suffix('.json').write_text(__import__('json').dumps(result['artifacts'], indent=2), encoding='utf-8')
        print(f'Report saved: {output}')
    finally:
        runner.pool.shutdown(wait=True)


if __name__ == '__main__':
    main()
