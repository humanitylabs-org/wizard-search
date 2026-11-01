import json
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

    def test_ubuntu_seed_must_be_pinned_and_reaches_helper_env(self):
        src = Path(runner.__file__).read_text()
        self.assertIn("cfg['ubuntu_seed'] in cfg['files']", src)
        self.assertIn("env['L4_UBUNTU_IMAGE_SEED'] = cfg['ubuntu_seed']", src)
        helper = self.helper().read_text()
        self.assertIn("os.environ.get('L4_UBUNTU_IMAGE_SEED'", helper)
        self.assertIn("image_hash != '5fa5b05e5ec239858c4531485d6023b0896448c2df7c63b34f8dae6ea6051a44'", helper)

    def test_doctor_tolerates_only_known_app_manager_404(self):
        ok = "PASS  index reachable  x\nFAIL  App Manager API reachable  GET /marketplace/all -> 404: b'404 page not found\\n'\n"
        self.assertEqual(len(runner.doctor_known_issues(1, ok)), 1)
        self.assertEqual(runner.doctor_known_issues(0, "PASS  a\n"), [])
        for bad in ("PASS  a\nFAIL  Hermes discovers wizard-builder  denied\n", "", ok + "FAIL  other\n"):
            with self.assertRaises(AssertionError):
                runner.doctor_known_issues(1, bad)
        with self.assertRaises(AssertionError):
            runner.doctor_known_issues(None, ok)

    def test_lima_socket_path_limit_is_checked(self):
        # A 12-hex stage dir pushed the real socket path to exactly 108 bytes and limactl refused.
        self.assertFalse(runner.lima_socket_fits('/srv/work/native-web-installed-a68a475a49c7/run', 'l4-nw-search-679be8c-a68a475a'))
        self.assertTrue(runner.lima_socket_fits('/srv/work/native-web-installed-a71d8dea/run', 'l4-nw-search-679be8c-a71d8dea'))

    def test_dispatcher_decode_unwraps_stock_hermes_result(self):
        import ast
        src = (Path(runner.__file__).parent / 'dispatcher.py').read_text()
        fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == 'decode')
        ns = {'json': json}
        exec(compile(ast.Module([fn], []), 'dispatcher', 'exec'), ns)
        decode = ns['decode']
        body = {'policy': {'mode': 'free-only'}}
        self.assertEqual(decode(json.dumps({'result': json.dumps(body)})), body)
        self.assertEqual(decode(json.dumps({'result': 'x', 'structuredContent': body})), body)
        self.assertEqual(decode({'content': [{'type': 'text', 'text': json.dumps(body)}]}), body)
        with self.assertRaises(AssertionError):
            decode(json.dumps({'error': 'boom'}))
        with self.assertRaises(AssertionError):
            decode(json.dumps({'result': json.dumps({'error': 'provider_unavailable'})}))

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

    def candidate_module(self):
        spec = importlib.util.spec_from_file_location('candidate_adapter', HERE / 'wam_candidate.py')
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_candidate_is_optional_but_never_mutable(self):
        self.assertIsNone(runner.wam_candidate(None))
        candidate = {'repo': 'humanitylabs-org/wizard-app-manager', 'commit': 'a' * 40}
        self.assertEqual(runner.wam_candidate(candidate), candidate)
        for invalid in ({}, {'repo': candidate['repo'], 'commit': 'main'},
                        {'repo': candidate['repo'], 'commit': 'a' * 12},
                        {'repo': candidate['repo'], 'commit': 'A' * 40},
                        {'repo': 'someone/other', 'commit': 'a' * 40},
                        {**candidate, 'branch': 'main'}):
            with self.subTest(invalid=invalid), self.assertRaises(AssertionError):
                runner.wam_candidate(invalid)

    def candidate_fixture(self, root):
        checkout = root / 'wam'
        (checkout / '.git').mkdir(parents=True)
        launcher = root / 'launcher'
        launcher.write_text(f'export WIZARD_RELEASE_PINS="${{WIZARD_RELEASE_PINS-baseline}}"\ncd "{checkout}" && exec "/usr/bin/python3" -m wam "$@"\n')
        compose = root / 'compose.yml'
        compose.write_text('image: baseline-manager@sha256:fixture\n')
        return checkout, launcher, compose

    def candidate_command(self, checkout, sha, calls, mismatch=None, dirty=False):
        def run(argv, cwd=None):
            calls.append(argv)
            self.assertEqual(cwd, checkout)
            if 'status' in argv:
                return ' M tracked.py' if dirty else ''
            if 'FETCH_HEAD^{commit}' in argv:
                return mismatch or sha
            if argv[-2:] == ['rev-parse', 'HEAD']:
                return sha if any('checkout' in a for a in calls) else 'b' * 40
            if argv[0] == '/usr/bin/python3':
                return str(checkout / 'wam/packaging.py')
            return ''
        return run

    def test_candidate_reuses_launcher_checkout_and_records_sha(self):
        with tempfile.TemporaryDirectory() as t:
            checkout, launcher, compose = self.candidate_fixture(Path(t))
            calls, sha = [], 'a' * 40
            before = launcher.read_bytes(), compose.read_bytes()
            result = self.candidate_module().install_candidate(
                {'repo': 'humanitylabs-org/wizard-app-manager', 'commit': sha}, launcher, compose,
                self.candidate_command(checkout, sha, calls))
            fetch = next(a for a in calls if 'fetch' in a)
            self.assertEqual(fetch[-2:], ['https://github.com/humanitylabs-org/wizard-app-manager.git', sha])
            self.assertIn('credential.helper=', fetch)
            self.assertIn('core.hooksPath=/dev/null', fetch)
            self.assertEqual(result['commit'], sha)
            self.assertEqual(result['before_commit'], 'b' * 40)
            self.assertEqual(result['manager_compose_sha256'], hashlib.sha256(before[1]).hexdigest())
            self.assertEqual((launcher.read_bytes(), compose.read_bytes()), before)
            self.assertFalse(any('install.sh' in a or 'docker' in a or 'pip' in a for a in calls))

    def test_candidate_fetch_mismatch_refuses_checkout(self):
        with tempfile.TemporaryDirectory() as t:
            checkout, launcher, compose = self.candidate_fixture(Path(t))
            calls, sha = [], 'a' * 40
            with self.assertRaisesRegex(AssertionError, 'Fetched WAM candidate SHA mismatch'):
                self.candidate_module().install_candidate(
                    {'repo': 'humanitylabs-org/wizard-app-manager', 'commit': sha}, launcher, compose,
                    self.candidate_command(checkout, sha, calls, mismatch='c' * 40))
            self.assertFalse(any('checkout' in a for a in calls))

    def test_candidate_dirty_baseline_refuses_fetch(self):
        with tempfile.TemporaryDirectory() as t:
            checkout, launcher, compose = self.candidate_fixture(Path(t))
            calls, sha = [], 'a' * 40
            with self.assertRaisesRegex(AssertionError, 'Dirty baseline'):
                self.candidate_module().install_candidate(
                    {'repo': 'humanitylabs-org/wizard-app-manager', 'commit': sha}, launcher, compose,
                    self.candidate_command(checkout, sha, calls, dirty=True))
            self.assertFalse(any('fetch' in a for a in calls))

    def test_candidate_checkout_and_module_mismatch_refused(self):
        for broken in ('HEAD', 'module'):
            with self.subTest(broken=broken), tempfile.TemporaryDirectory() as t:
                checkout, launcher, compose = self.candidate_fixture(Path(t))
                calls, sha = [], 'a' * 40
                normal = self.candidate_command(checkout, sha, calls)
                def command(argv, cwd=None):
                    result = normal(argv, cwd)
                    if broken == 'HEAD' and argv[-2:] == ['rev-parse', 'HEAD'] and any('checkout' in a for a in calls):
                        return 'c' * 40
                    if broken == 'module' and argv[0] == '/usr/bin/python3':
                        return '/unrelated/wam/packaging.py'
                    return result
                with self.assertRaises(AssertionError):
                    self.candidate_module().install_candidate(
                        {'repo': 'humanitylabs-org/wizard-app-manager', 'commit': sha}, launcher, compose, command)

    def test_candidate_real_detached_checkout_and_launcher(self):
        # Real git/Python, local fixture transport only: no GitHub, installer, VM or Docker.
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            upstream, checkout = root / 'upstream', root / 'installed'
            module = self.candidate_module()
            module.run(['git', 'init', str(upstream)])
            (upstream / 'wam').mkdir()
            (upstream / 'wam/__init__.py').write_text('')
            (upstream / 'wam/packaging.py').write_text('CONTEXT = "host"\n')
            module.run(['git', 'add', '.'], cwd=upstream)
            commit = ['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m']
            module.run(commit + ['baseline'], cwd=upstream)
            module.run(['git', 'clone', str(upstream), str(checkout)])
            (upstream / 'wam/packaging.py').write_text('CONTEXT = "/app-data"\n')
            module.run(['git', 'add', '.'], cwd=upstream)
            module.run(commit + ['candidate'], cwd=upstream)
            sha = module.run(['git', 'rev-parse', 'HEAD'], cwd=upstream)
            launcher, compose = root / 'wam-launcher', root / 'compose.yml'
            import sys
            launcher.write_text(f'cd "{checkout}" && exec "{sys.executable}" -m wam "$@"\n')
            compose.write_text('image: unchanged-baseline\n')
            def local_transport(argv, cwd=None):
                argv = [str(upstream) if a == 'https://github.com/humanitylabs-org/wizard-app-manager.git' else a for a in argv]
                # Avoid creating an untracked __pycache__ in this tiny synthetic checkout.
                if argv[0] == sys.executable:
                    argv.insert(1, '-B')
                return module.run(argv, cwd)
            result = module.install_candidate({'repo': 'humanitylabs-org/wizard-app-manager', 'commit': sha},
                                              launcher, compose, local_transport)
            self.assertEqual(result['commit'], sha)
            self.assertEqual((checkout / 'wam/packaging.py').read_text(), 'CONTEXT = "/app-data"\n')
            self.assertEqual(module.run(['git', 'status', '--porcelain'], cwd=checkout), '')
            self.assertEqual(module.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], cwd=checkout), 'HEAD')

    def test_candidate_phase_is_after_baseline_before_search_and_receipted(self):
        src = (HERE / 'runner.py').read_text()
        self.assertLess(src.index("run('fresh-rig'"), src.index("guest('wam-candidate'"))
        self.assertLess(src.index("guest('wam-candidate'"), src.index("guest('install-and-dispatch'"))
        self.assertIn("receipt['wam_candidate']", src)
        self.assertIn("str(here / script) in cfg['files']", src)
        self.assertIn("receipt['cleanup']['verified_not_running']", src)
        guest = (HERE / 'guest.py').read_text()
        self.assertIn("Path(cli.__file__).resolve()", guest)
        self.assertIn("release_pins.image_ref(pins['images']['wizard-app-manager'])", guest)

    def test_installed_shell_public_open_after_registry_refresh(self):
        browser = (HERE / 'browser.cjs').read_text()
        self.assertIn('?shell=${shell}&open=wizard-search', browser)
        self.assertIn("size.width > 600 ? 'desktop' : 'phone'", browser)
        self.assertIn("deeplink?.log?.includes('open:wizard-search')", browser)
        self.assertIn('await window.WizCore.appsLoaded()', browser)
        refresh = browser.index('await window.WizCore.refreshApps({afterPending:true})')
        route = browser.index("window.WizCore.deeplink.route(location.pathname + '?open=wizard-search')")
        frame = browser.index("page.waitForSelector('iframe[data-own-app=\"wizard-search\"]'")
        self.assertLess(refresh, route)
        self.assertLess(route, frame)
        self.assertIn("registry.APP['wizard-search']", browser)
        self.assertIn('if (!app?.url) throw Error', browser)
        self.assertIn("assert.equal(opened.shell,shell)", browser)
        self.assertNotIn('iframe[src*=', browser)
        self.assertNotIn('app-session=', browser)  # must exercise the full installed shells

    def test_installed_browser_failure_capture_precedes_rethrow_and_close(self):
        browser = (HERE / 'browser.cjs').read_text()
        capture = browser.index('await captureFailure(page,details,error)')
        rethrow = browser.index('throw error;', capture)
        close = browser.index('finally { await browser?.close(); }')
        self.assertLess(capture, rethrow)
        self.assertLess(rethrow, close)
        self.assertIn('fullPage:true,timeout:10000', browser)
        self.assertIn('`${stem}.png`', browser)
        self.assertIn('`${stem}.json`', browser)
        for field in ('href:location.href', 'iframeSrcs:', 'visibleAppIds:', 'registeredApps:', 'backendAppIds:', 'deeplinkLog:'):
            self.assertIn(field, browser)
        self.assertIn('catch (e) { state.screenshotError', browser)
        self.assertIn('catch (e) { state.pageStateError', browser)

    def test_pinned_shell_skin_ids(self):
        browser = (HERE / 'browser.cjs').read_text()
        self.assertIn("x.id === 'nebula'", browser)
        self.assertIn("x.id === 'obsidian-light'", browser)
        self.assertNotIn('/paper/i', browser)


if __name__ == '__main__':
    unittest.main()
