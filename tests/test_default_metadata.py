"""Package metadata must mark the default without undoing app-wall access."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DefaultSearchMetadataTests(unittest.TestCase):
    def test_system_search_keeps_tinfoil_connection_and_recipe_revision(self):
        manifest = (ROOT / 'wizard.md').read_text()
        self.assertIn('\nsystem: true\n', manifest)
        self.assertIn('\nuses: [tinfoil-api-key]\n', manifest)
        self.assertEqual(json.loads((ROOT / 'runtipi/config.json').read_text())['tipi_version'], 2)

    def test_all_package_versions_match(self):
        version = next(line.split(': ', 1)[1] for line in (ROOT / 'wizard.md').read_text().splitlines() if line.startswith('version: '))
        self.assertEqual(json.loads((ROOT / 'runtipi/config.json').read_text())['version'], version)
        self.assertEqual(json.loads((ROOT / 'openapi.json').read_text())['info']['version'], version)
        self.assertEqual(json.loads((ROOT / 'setup.json').read_text())['version'], version)
        self.assertIn("version: '" + version + "'", (ROOT / 'web/app.js').read_text())
