"""Lightweight preparation regressions. Never start a VM, container or browser."""
import ast
import importlib.util
import hashlib
from pathlib import Path
import re
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('installed_runner', HERE / 'runner.py')
assert spec and spec.loader
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class PreparationTests(unittest.TestCase):
    def test_exact_dependency_hash(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / 'file'
            p.write_bytes(b'actual-file')
            runner.check_manifest({str(p): hashlib.sha256(p.read_bytes()).hexdigest()})

    def test_changed_dependency_refused(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / 'file'
            p.write_bytes(b'drift')
            with self.assertRaisesRegex(AssertionError, 'Drift'):
                runner.check_manifest({str(p): '0' * 64})

    def test_symlink_refused(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / 'file'
            p.write_bytes(b'a')
            link = Path(t) / 'link'
            link.symlink_to(p)
            with self.assertRaisesRegex(AssertionError, 'nonregular'):
                runner.check_manifest({str(link): hashlib.sha256(b'a').hexdigest()})

    def test_all_staged_python_parses(self):
        for p in HERE.glob('*.py'):
            ast.parse(p.read_text(), filename=str(p))

    def test_published_launcher_parser(self):
        launcher = 'export WIZARD_RELEASE_PINS="${WIZARD_RELEASE_PINS-/home/wizard/.wizard-os/release-pins.json}"\ncd "/home/wizard/.local/share/wizard-app-manager" && exec "/home/wizard/.local/share/wizard-app-manager/.venv/bin/python" -m wam "$@"'
        guest = (HERE / 'guest.py').read_text()
        pattern = ast.literal_eval(next(n.args[0] for n in ast.walk(ast.parse(guest)) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'search'))
        match = re.search(pattern, launcher)
        assert match
        self.assertEqual(match[1], '/home/wizard/.wizard-os/release-pins.json')
        self.assertIsNotNone(re.search(r'cd "([^\"]+)" && exec "([^\"]+)" -m wam', launcher))

    def test_no_model_or_rpc_substitute(self):
        dispatcher = (HERE / 'dispatcher.py').read_text()
        self.assertIn('handle_function_call(tool,', dispatcher)
        self.assertIn("allowed_mcp_names=['wizard']", dispatcher)
        for blocked in ('AIAgent(', '/chat/completions', 'openai.OpenAI', 'urllib.request', 'requests.post'):
            self.assertNotIn(blocked, dispatcher)

    def test_pinned_shell_skin_ids(self):
        browser = (HERE / 'browser.cjs').read_text()
        self.assertIn("x.id === 'nebula'", browser)
        self.assertIn("x.id === 'obsidian-light'", browser)
        self.assertNotIn('/paper/i', browser)


if __name__ == '__main__':
    unittest.main()
