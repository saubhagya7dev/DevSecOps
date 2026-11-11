import os
import subprocess
import sys
import unittest
from unittest.mock import patch

from devsecops.config import ROOT, read_settings


class SettingsTests(unittest.TestCase):
    def test_settings_are_explicit_immutable_and_validate_budget(self):
        settings = read_settings({'ANALYST_MODEL': 'custom-model', 'RESEARCHER_TOKEN_BUDGET': '2500', 'ENABLE_VCDB': '1'})
        self.assertEqual(settings.role_models['analyst']['model'], 'custom-model')
        self.assertEqual(settings.researcher_token_budget, 2500)
        self.assertTrue(settings.vcdb_enabled)
        with self.assertRaises(TypeError):
            settings.role_models['analyst']['model'] = 'changed'
        for invalid in ('0', '-1', 'not-a-number'):
            with self.assertRaisesRegex(ValueError, 'positive integer'):
                read_settings({'RESEARCHER_TOKEN_BUDGET': invalid})

    def test_import_does_not_read_dotenv(self):
        code = ('from pathlib import Path; from unittest.mock import patch; '
                'guard=patch.object(Path,"read_text",side_effect=AssertionError("dotenv read")); '
                'guard.start(); import devsecops.config; print("imported")')
        result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('imported', result.stdout)

    def test_bootstrap_applies_environment_before_adapters_import(self):
        code = ('from devsecops.config import configure; configure(); '
                'from devsecops.providers import ROLE_MODELS, RESEARCHER_TOKEN_BUDGET; '
                'assert ROLE_MODELS["analyst"]["model"]=="custom-model"; '
                'assert RESEARCHER_TOKEN_BUDGET==2500')
        with patch.dict(os.environ, {'ANALYST_MODEL': 'custom-model', 'RESEARCHER_TOKEN_BUDGET': '2500'}):
            result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
