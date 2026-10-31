"""Lightweight preparation regressions. Never start a VM, container or browser."""
import ast
import importlib.util
import hashlib
import os
import subprocess
from pathlib import Path
import re
import tempfile
import unittest
from urllib.parse import urlparse

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

    def helper(self):
        # Full byte-identical real rig snapshot, not a mocked argparse interface.
        fixture = HERE / 'fixtures/fresh_launch.py.txt'
        self.assertEqual(hashlib.sha256(fixture.read_bytes()).hexdigest(),
                         'a78a1b08b0bea0ddd96b359e59645ad554be2e17443684f042998454e0d3ac7b')
        actual = Path(os.environ.get('FRESH_LAUNCH_HELPER', fixture))
        self.assertEqual(actual.read_bytes(), fixture.read_bytes())
        return actual

    def config(self):
        return dict(fresh_helper=str(self.helper()), work='/srv/work/new-adapter/run',
                    vm='l4-nw-search-679be8c', release='0.3.73')

    def test_real_fresh_helper_positional_contract(self):
        c = self.config()
        argv = runner.fresh_argv(c)
        self.assertEqual(argv[2:], ['/srv/work/new-adapter/run/fresh-evidence',
                                    '/srv/work/new-adapter/run/lima', c['vm'], '0.3.73'])
        runner.check_fresh_contract(self.helper(), argv)

    def test_legacy_flagged_rig_contract_rejected(self):
        c = self.config()
        with self.assertRaises(AssertionError):
            runner.check_fresh_contract(self.helper(), ['python3', c['fresh_helper'],
                '--q2', 'unrelated-base.sh', '--lima', 'L', '--evidence', 'E', '--vm', c['vm']])

    def test_real_lane_prefix_rejected(self):
        c = self.config()
        c['vm'] = 'nw-search-679be8c'
        with self.assertRaisesRegex(AssertionError, 'refuse non-lane VM'):
            runner.check_fresh_contract(self.helper(), runner.fresh_argv(c))

    def test_lima_command_is_not_prequoted(self):
        command = "printf '%s\\n' 'a b'; test 1 = 1"
        argv = runner.shell_argv('l4-nw-search-test', command)
        self.assertEqual(argv[-4:], ['--', 'bash', '-lc', command])
        # Local bash exercises the same final argv, without Lima/VM side effects.
        p = subprocess.run(argv[-3:], text=True, capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.strip(), 'a b')

    def test_registry_shell_port_not_nonexistent_view_local(self):
        # Actual r3/fresh/evidence/installed-readback.log:469-497: no top-level port.
        local = 'http://127.0.0.1:8796/wizard-os-home/'
        shell = {'view': {'url': local}}
        tree = ast.parse((HERE / 'guest.py').read_text())
        node = next(n for n in tree.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'port' for t in n.targets))
        for view in [{'url': local}, {'url': 'https://synthetic.example/wizard-os-home/', 'local': local}]:
            shell['view'] = view
            scope = {'shell': shell, 'urlparse': urlparse}
            exec(compile(ast.Module(body=[node], type_ignores=[]), '<guest-port>', 'exec'), scope)
            self.assertEqual(scope['port'], 8796)

    def test_dispatcher_uses_installed_wam_engine_interpreter(self):
        guest = (HERE / 'guest.py').read_text()
        self.assertIn("engine[0], agent_link.HERMES_PY, '-'", guest)

    def test_published_launcher_parser(self):
        launcher = 'export WIZARD_RELEASE_PINS="${WIZARD_RELEASE_PINS-/home/wizard/.wizard-os/release-pins.json}"\ncd "/home/wizard/.local/share/wizard-app-manager" && exec "/usr/bin/python3" -m wam "$@"'
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
