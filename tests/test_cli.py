import json
import subprocess
import sys
import unittest
from pathlib import Path

from devsecops.store import Store
from tests.test_review import workspace_temp


class CliTests(unittest.TestCase):
    def test_offline_review_backup_and_explicit_retention_in_isolated_directory(self):
        with workspace_temp() as tmp:
            root = Path(tmp)
            code = ('import sys; from pathlib import Path; import devsecops.config as config; '
                    'config.DATA=Path(sys.argv[1])/"data"; sys.argv=["run.py",*sys.argv[2:]]; '
                    'from devsecops.__main__ import main; main()')

            def run(*args):
                return subprocess.run([sys.executable, '-c', code, str(root), *args],
                                      capture_output=True, text=True, timeout=20)

            report = root / 'report.md'
            result = run('--demo', '--output', str(report))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('ILLUSTRATIVE OFFLINE EXAMPLE', report.read_text(encoding='utf-8'))
            artifacts = json.loads(report.with_suffix('.json').read_text(encoding='utf-8'))
            self.assertEqual(artifacts['validation']['model_calls'], 0)
            self.assertIn('stage_seconds', artifacts['validation'])
            backup = root / 'backup.sqlite3'
            self.assertEqual(run('--backup', str(backup)).returncode, 0)
            self.assertEqual(Store(backup).storage_stats()['investigations'], 1)
            self.assertNotEqual(run('--prune-before', '9999-01-01T00:00:00+00:00').returncode, 0)
            store = Store(root / 'data' / 'reviews.sqlite3')
            self.assertEqual(store.storage_stats()['investigations'], 1)
            result = run('--prune-before', '9999-01-01T00:00:00+00:00', '--confirm-prune')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(store.storage_stats()['investigations'], 0)
