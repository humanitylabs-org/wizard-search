"""Real configuration -> shipped app.js -> setup DOM. No browser or upstream traffic."""
import importlib.util
import json
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('notice_search', ROOT / 'server.py')
assert spec and spec.loader
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


@unittest.skipUnless(shutil.which('node'), 'Node is required for the shipped UI render test')
class SetupNoticeTests(unittest.TestCase):
    def render(self, mode='', approved='', free=True, keys=True):
        with patch.multiple(s, POLICY_MODE=mode, POLICY_APPROVED=approved,
                            SEARXNG_URL='http://searx.invalid' if free else '', SOCKS='', LLM_URL='',
                            DATA_DIR=ROOT / 'not-a-real-data-directory',
                            FC_CLOUD_KEY='fake-notice-fc' if keys else '', BD_TOKEN='fake-notice-bd' if keys else '',
                            FIRECRAWL_URL='http://router.invalid' if keys else ''):
            cfg = s.configuration()
        result = subprocess.run(['node', str(ROOT / 'tests/render_setup.cjs')], input=json.dumps(cfg),
                                capture_output=True, text=True, check=True, timeout=5)
        view = json.loads(result.stdout)
        self.assertEqual(len(view['requests']), 2)  # reads only, never a settings write
        self.assertNotIn('fake-notice', result.stdout)
        return cfg, view

    def test_default_with_old_keys_shows_pause_even_with_free_search_configured(self):
        cfg, view = self.render()
        self.assertEqual(cfg['state'], 'configured')
        self.assertFalse(view['setupHidden'])
        self.assertIn('paused', view['status'])
        self.assertFalse(view['noticeHidden'])
        self.assertIn('Firecrawl Cloud', view['notice'])
        self.assertIn('Bright Data', view['notice'])
        self.assertIn('WIZARD_SEARCH_PROVIDER_POLICY=approved-upgrades', view['notice'])
        self.assertIn('WIZARD_SEARCH_APPROVED_UPGRADES=firecrawl_cloud,brightdata,firecrawl_router', view['notice'])
        self.assertIn('legacy-race', view['notice'])
        self.assertIn('kept', view['notice'])

    def test_no_free_provider_keeps_setup_required_and_the_pause_notice(self):
        _, view = self.render(free=False)
        self.assertFalse(view['setupHidden'])
        self.assertIn('Setup required', view['status'])
        self.assertIn('paused', view['status'])

    def test_explicit_choices_are_not_reinterpreted_or_reapproval_prompts(self):
        for mode, approved in [('legacy-race', ''), ('approved-upgrades', 'firecrawl_cloud,brightdata,firecrawl_router')]:
            with self.subTest(mode=mode):
                cfg, view = self.render(mode, approved)
                self.assertEqual(cfg['policy']['mode'], mode)
                self.assertEqual(cfg['policy']['blocked_configured'], [])
                self.assertTrue(view['setupHidden'])
                self.assertTrue(view['noticeHidden'])
                self.assertNotIn('paused', view['status'])

    def test_partial_approval_names_only_paused_providers_and_keeps_approved_selection(self):
        cfg, view = self.render('approved-upgrades', 'brightdata')
        self.assertEqual(cfg['policy']['approved_upgrades'], ['brightdata'])
        self.assertTrue(cfg['usable']['brightdata'])
        self.assertIn('Firecrawl Cloud', view['notice'])
        self.assertNotIn('Bright Data', view['notice'])
        self.assertIn('current provider choices are unchanged', view['notice'])
        self.assertIn('WIZARD_SEARCH_APPROVED_UPGRADES=brightdata,firecrawl_cloud,firecrawl_router', view['notice'])

    def test_invalid_policy_reports_safe_fallback_and_pause(self):
        cfg, view = self.render('typo')
        self.assertTrue(cfg['policy']['error'])
        self.assertIn('settings need correction', view['status'])
        self.assertIn('paused', view['status'])
        self.assertFalse(view['setupHidden'])

    def test_fresh_keyless_setup_has_no_paid_notice(self):
        _, view = self.render(keys=False)
        self.assertTrue(view['setupHidden'])
        self.assertTrue(view['noticeHidden'])
        self.assertNotIn('paused', view['status'])
