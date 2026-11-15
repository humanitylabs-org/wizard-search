"""Phone Back on search results clears the search before leaving Search (issue #38)."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('node'), 'node not installed')
class BackClearsSearch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = subprocess.run(['node', str(ROOT / 'tests/back_harness.cjs')], capture_output=True, text=True, timeout=30)
        if out.returncode:
            raise AssertionError(out.stderr)
        cls.r = json.loads(out.stdout.strip().splitlines()[-1])

    def test_empty_start_screen_is_root(self):
        self.assertFalse(self.r['start_can'])

    def test_results_on_all_tab_are_a_back_layer(self):
        self.assertEqual(self.r['results']['q'], 'python docs')
        self.assertTrue(self.r['results']['results_shown'])
        self.assertTrue(self.r['results_can'])
        self.assertTrue(self.r['results_back'])

    def test_back_clears_query_results_and_box(self):
        a = self.r['after_back']
        self.assertEqual((a['q'], a['box'], a['tab']), ('', '', 'all'))
        self.assertTrue(a['empty_shown'])
        self.assertFalse(a['results_shown'])
        self.assertFalse(a['images_shown'])
        self.assertFalse(a['url_has_q'])
        self.assertEqual(a['title'], 'Search')
        # Then Back behaves as before: nothing left, the shell leaves Search.
        self.assertFalse(self.r['after_can'])
        self.assertFalse(self.r['after_back_again'])

    def test_images_tab_steps_to_all_then_clears(self):
        self.assertTrue(self.r['images_back'])
        self.assertEqual((self.r['images_after']['tab'], self.r['images_after']['q']), ('all', 'python docs'))
        self.assertTrue(self.r['images_back2'])
        self.assertEqual(self.r['images_after2']['q'], '')
        self.assertTrue(self.r['images_after2']['empty_shown'])


if __name__ == '__main__':
    unittest.main()
