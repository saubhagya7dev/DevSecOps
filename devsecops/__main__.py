import argparse
import os
import sys
import time
from pathlib import Path

from .config import configure, missing_credentials


def main():
    configure()
    parser = argparse.ArgumentParser(description='Incident-informed repository review: local UI or CLI.')
    parser.add_argument('--port', type=int, default=int(os.getenv('PORT', '8765')))
    parser.add_argument('--repo', help='Analyze a public GitHub URL directly from the CLI')
    parser.add_argument('--demo', action='store_true', help='Run the clearly labeled synthetic offline example via CLI')
    parser.add_argument('--check-apis', action='store_true', help='Make small live requests to verify Gemini, both Groq models, Tavily, and GitHub')
    parser.add_argument('--backup', metavar='PATH', help='Save a consistent SQLite backup to a new file')
    parser.add_argument('--prune-before', metavar='ISO_TIMESTAMP', help='Remove terminal history older than a timezone-aware timestamp')
    parser.add_argument('--confirm-prune', action='store_true', help='Confirm the explicit history retention operation')
    parser.add_argument('--output', default='test-output/report.md')
    args = parser.parse_args()
    if sum(map(bool, (args.repo, args.demo, args.check_apis, args.backup, args.prune_before))) > 1:
        parser.error('Choose one action: server, repo, demo, check-apis, backup, or prune-before.')
    if args.confirm_prune and not args.prune_before:
        parser.error('--confirm-prune requires --prune-before.')
    if args.backup or args.prune_before:
        if args.prune_before and not args.confirm_prune:
            parser.error('--prune-before requires --confirm-prune; back up history first.')
        from .ownership import InstanceLock
        from .store import Store
        with InstanceLock():
            store = Store()
            if args.backup:
                print(f'Backup saved: {store.backup(args.backup)}')
            else:
                print(f'Removed {store.prune_history(args.prune_before)} terminal investigation(s).')
        return
    if args.check_apis:
        if args.repo or args.demo:
            parser.error('--check-apis cannot be combined with --repo or --demo.')
        from .diagnostics import check_apis
        results = check_apis()
        raise SystemExit(0 if all(result['status'] == 'PASS' for result in results) else 1)
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
    if not args.demo and missing_credentials():
        parser.error('Set ' + ', '.join(missing_credentials()) + ' before starting a live analysis.')
    from .ownership import InstanceLock
    with InstanceLock():
        store = Store()
        store.recover()
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
            runner.close()


if __name__ == '__main__':
    main()
