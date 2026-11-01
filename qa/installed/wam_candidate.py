"""Switch only the fresh guest's host CLI checkout; never run WAM's installer."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


def run(argv, cwd=None):
    env = {k: os.environ[k] for k in ('PATH', 'HOME', 'LANG') if k in os.environ}
    env['GIT_TERMINAL_PROMPT'] = '0'
    return subprocess.run(argv, cwd=cwd, env=env, check=True, capture_output=True,
                          text=True, timeout=180).stdout.strip()


def install_candidate(candidate, launcher, manager_compose, command=run):
    assert set(candidate) == {'repo', 'commit'}
    assert candidate['repo'] == 'humanitylabs-org/wizard-app-manager'
    sha = candidate['commit']
    assert isinstance(sha, str) and re.fullmatch(r'[0-9a-f]{40}', sha), 'Unpinned WAM candidate'
    launcher_bytes = launcher.read_bytes()
    match = re.search(r'cd "([^\"]+)" && exec "([^\"]+)" -m wam', launcher_bytes.decode())
    assert match, 'WAM launcher layout changed'
    checkout, interpreter = Path(match[1]), match[2]
    assert checkout.is_absolute() and (checkout / '.git').is_dir()
    # REUSE install.sh:102-109: launcher cd's to HERE and execs PY -m wam.
    # Updating that checkout needs no pip install, launcher rewrite, API restart or manager image.
    compose_bytes = manager_compose.read_bytes()
    git = ['git', '-c', 'credential.helper=', '-c', 'core.hooksPath=/dev/null']
    assert not command(git + ['status', '--porcelain'], cwd=checkout), 'Dirty baseline WAM checkout'
    before = command(git + ['rev-parse', 'HEAD'], cwd=checkout)
    command(git + ['fetch', '--no-tags', '--depth=1',
                   'https://github.com/' + candidate['repo'] + '.git', sha], cwd=checkout)
    fetched = command(git + ['rev-parse', 'FETCH_HEAD^{commit}'], cwd=checkout)
    assert fetched == sha, 'Fetched WAM candidate SHA mismatch'
    command(git + ['checkout', '--detach', sha], cwd=checkout)
    actual = command(git + ['rev-parse', 'HEAD'], cwd=checkout)
    assert actual == sha, 'WAM candidate checkout SHA mismatch'
    assert not command(git + ['status', '--porcelain'], cwd=checkout)
    assert launcher.read_bytes() == launcher_bytes, 'WAM launcher changed'
    assert manager_compose.read_bytes() == compose_bytes, 'Manager compose changed'
    # Fresh process: never keep baseline Python modules cached across checkout.
    module = command([interpreter, '-c', 'import wam.packaging; print(wam.packaging.__file__)'], cwd=checkout)
    assert Path(module).resolve() == (checkout / 'wam/packaging.py').resolve()
    return {'repo': candidate['repo'], 'requested_commit': sha, 'before_commit': before,
            'commit': actual, 'checkout': str(checkout), 'interpreter': interpreter,
            'module': module, 'launcher_sha256': hashlib.sha256(launcher_bytes).hexdigest(),
            'manager_compose_sha256': hashlib.sha256(compose_bytes).hexdigest(),
            'scope': 'host CLI checkout only; baseline manager image unchanged'}


def main():
    root = Path.home() / 'native-web-qa'
    assert (root / 'disposable.json').read_text().strip() == '679be8ce8eea6ba13bf031104ea991202b5c373a'
    assert not any(os.environ.get(k) for k in ('GH_TOKEN', 'GITHUB_TOKEN', 'TINFOIL_API_KEY', 'OPENAI_API_KEY'))
    candidate = json.loads((root / 'wam-candidate-request.json').read_text())
    # Read baseline Config before replacing its checkout; no baseline module is used afterwards.
    from wam import cli
    config = cli.Config()
    assert config.runtipi_root.is_relative_to(Path.home())
    result = install_candidate(candidate, Path.home() / '.local/bin/wam',
                               config.runtipi_root / 'user-config/tipi-compose.yml')
    (root / 'wam-candidate.json').write_text(json.dumps(result, indent=2) + '\n')
    print('NATIVE_WEB_WAM_CANDIDATE=' + json.dumps(result))


if __name__ == '__main__':
    main()
