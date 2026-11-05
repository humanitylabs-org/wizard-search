#!/usr/bin/env python3
"""Browser-free operator contracts; no live writes or systemd calls."""
import ast
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('activation', ROOT / 'ops/wam-voice-activate.py')
assert spec is not None and spec.loader is not None
activation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(activation)


class OperatorContracts(unittest.TestCase):
    def test_pointer_refuses_nonlink_and_wrong_target(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            (home / 'builder/current').mkdir(parents=True)
            with self.assertRaises(ValueError):
                activation.pointer(home, activation.BASE)
            (home / 'builder/current').rmdir()
            (home / 'other').mkdir()
            (home / 'builder/releases' / activation.BASE).mkdir(parents=True)
            (home / 'builder/current').symlink_to(home / 'other')
            with self.assertRaises(ValueError):
                activation.pointer(home, activation.BASE)

    def test_delta_rejects_added_removed_and_unrelated_files(self):
        before = {'wam/registry.py': 'a', 'other': 'b'}
        for after in [{'wam/registry.py': 'c'}, {**before, 'new': 'x'}, {'wam/registry.py': 'c', 'other': 'x'}, before]:
            with self.assertRaises(ValueError):
                activation.validate_delta(before, after)

    def test_delta_rejects_unreviewed_identity(self):
        with self.assertRaisesRegex(ValueError, 'identity'):
            activation.validate_delta({'wam/registry.py': 'a'}, {'wam/registry.py': 'b'})

    def test_dry_run_never_queries_systemd_or_creates_backup(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            for action in ['activate', 'rollback']:
                args = ['activate.py', action, '--os-home', str(base / 'os'), '--api-baseline', str(base / 'old'),
                        '--api-release', str(base / activation.HOST_SHA), '--backup', str(base / 'backup')]
                with patch('sys.argv', args), patch.object(activation, 'show', side_effect=AssertionError('systemd forbidden')), patch.object(activation, 'run', side_effect=AssertionError('execution forbidden')):
                    activation.main()
            self.assertEqual(list(base.iterdir()), [])

    def test_parent_helper_binds_reused_image_and_full_runtime_map(self):
        # Execute only the real package branch's pure manifest/image-binding block.
        source = (ROOT / 'ops/parent-release.py').read_text()
        block = source[source.index(' image_sha=manifest.get('):source.index(' assert not backup.exists()')]
        code = compile(ast.parse('if True:\n' + block), '<actual package binding>', 'exec')
        reuse_path = Path(__file__).resolve().parents[1] / 'image-reuse.json'
        # On a local source checkout the receipt is passed explicitly, not invented.
        import os
        reuse_path = Path(os.environ.get('QA_IMAGE_REUSE', reuse_path))
        if not reuse_path.exists():
            self.skipTest('Provide QA_IMAGE_REUSE for exact recorded image binding')
        reuse = json.loads(reuse_path.read_text())
        manifest = {'image_source_sha': reuse['runtime_source_sha'], 'runtime_bytes_identical': True,
                    'runtime_file_sha256': dict(reuse['runtime_file_sha256'])}
        import hashlib
        values = {'manifest': manifest, 'sha': 'qa-only-new-source', 'root': ROOT, 'hashlib': hashlib}
        exec(code, values)
        self.assertEqual(values['image_sha'], reuse['runtime_source_sha'])
        key = next(iter(manifest['runtime_file_sha256']))
        manifest['runtime_file_sha256'][key] = '0' * 64
        with self.assertRaises(AssertionError):
            exec(code, values)
        manifest['runtime_file_sha256'] = dict(reuse['runtime_file_sha256'])
        manifest['runtime_file_sha256']['unreviewed-extra'] = '0' * 64
        with self.assertRaises(AssertionError):
            exec(code, values)
        manifest['runtime_file_sha256'] = dict(reuse['runtime_file_sha256'])
        del manifest['runtime_file_sha256'][key]
        with self.assertRaises(AssertionError):
            exec(code, values)


if __name__ == '__main__':
    unittest.main(verbosity=2)
