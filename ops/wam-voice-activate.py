#!/usr/bin/env python3
"""Parent-only host WAM activation. Dry run by default; no registry/agent edits.

This installs the reviewed API archive as a NEW release and uses the supported
managed builder installer. Rollback retains both releases. See WAM-VOICE-REVIEW.md.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

BASE = '0934bfcb8dcbe6868e49aa618d002fc3e3e11a3b7d0f731ebc02161e564a5f78'
CANDIDATE = 'fe78cab4e62b1abd99cdb47d09e200c93a031b07c97eaa395e57680ff24655fb'
HOST_SHA = '975fcbd37a84f0a79bd593db317f27b500a2cac6'
ARCHIVE_SHA = '45bc08bfd924875edd81f9694b715eff37aa9175240a946a3dc8d56ff25d689b'
REGISTRY_SHA = '26aeb059c9dc4b586cfbae0a2cbe1b068832b26ffb7ce4e3ad9104b978d0dca5'
UNIT = 'wizard-app-manager-api.service'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def files(root):
    return {str(p.relative_to(root)): digest(p) for p in sorted(root.rglob('*'))
            if p.is_file() and p.name != 'bundle.json'
            and '__pycache__' not in p.parts and p.suffix != '.pyc'}


def bundle_digest(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


def validate_delta(before, after):
    if set(before) != set(after) or sorted(k for k in before if before[k] != after[k]) != ['wam/registry.py']:
        raise ValueError('Expected exactly one changed distribution file: wam/registry.py')
    if bundle_digest(before) != BASE or bundle_digest(after) != CANDIDATE:
        raise ValueError('Unreviewed bundle identity')
    if after['wam/registry.py'] != REGISTRY_SHA:
        raise ValueError('Unreviewed registry implementation')


def pointer(home, expected):
    link = home / 'builder/current'
    target = home / 'builder/releases' / expected
    if not link.is_symlink() or link.resolve(strict=True) != target.resolve(strict=True):
        raise ValueError('Builder current pointer drift; preserving it')
    rows = files(target)
    manifest = json.loads((target / 'bundle.json').read_text())
    if bundle_digest(rows) != expected or manifest['files'] != rows or manifest['sha256'] != expected:
        raise ValueError('Builder release bytes drift; preserving it')
    return rows


def run(argv, **kw):
    return subprocess.run(argv, check=True, timeout=60, **kw)


def show(prop):
    return subprocess.check_output(['systemctl', '--user', 'show', UNIT, '-p', prop, '--value'], text=True, timeout=15).strip()


def builder(source, home, operation, arg):
    # No Hermes home/fresh/agent mount operation is ever supplied.
    program = ('from pathlib import Path; from wam.builder_bundle import ' + operation +
               '; import sys; ' + operation + '(Path(sys.argv[1]), ' +
               ('source=Path(sys.argv[2])' if operation == 'install' else 'sys.argv[2]') + ')')
    run(['/usr/bin/python3', '-c', program, str(home), str(arg)], cwd=source,
        env={**os.environ, 'PYTHONPATH': str(source), 'PYTHONDONTWRITEBYTECODE': '1'})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['activate', 'rollback'])
    p.add_argument('--execute', action='store_true')
    for name in ['os-home', 'api-baseline', 'api-release', 'backup']:
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--source-archive', type=Path)
    p.add_argument('--builder-source', type=Path)
    a = p.parse_args()
    for key in ['os_home', 'api_baseline', 'api_release', 'backup']:
        value = getattr(a, key)
        if not value.is_absolute():
            p.error(key + ' must be an absolute operator-selected path')
    dropin = Path.home() / '.config/systemd/user' / (UNIT + '.d') / '99-search-voice.conf'
    content = '[Service]\nWorkingDirectory=' + str(a.api_release) + '\nEnvironment="PYTHONPATH=' + str(a.api_release) + '"\n'
    if any(c in str(a.api_release) for c in '\n\r"% \\'):
        p.error('API release path must have no whitespace, systemd specifiers or quoting characters')
    if not a.execute:
        print(json.dumps({'dry_run': True, 'action': a.action, 'unit': UNIT, 'dropin': str(dropin),
                          'api_release': str(a.api_release), 'builder_baseline': BASE, 'builder_candidate': CANDIDATE,
                          'registry_regeneration': 'parent must verify both entrypoints and lifecycle/mirror afterwards'}))
        return
    if a.action == 'activate':
        if not a.source_archive or not a.builder_source:
            p.error('activate requires --source-archive and --builder-source')
        assert digest(a.source_archive) == ARCHIVE_SHA, 'Reviewed API source archive differs'
        before = pointer(a.os_home, BASE)
        validate_delta(before, files(a.builder_source))
        assert digest(a.api_baseline / 'wam/registry.py') == before['wam/registry.py']
        assert Path(show('WorkingDirectory')).resolve() == a.api_baseline.resolve(), 'API cwd drift'
        command = show('ExecStart')
        assert '/usr/bin/python3' in command and '-m wam serve' in command, 'API command drift'
        assert not a.api_release.resolve().is_relative_to(a.api_baseline.resolve()), 'Never nest a new release in the sealed baseline'
        assert not a.api_release.exists() and not a.api_release.is_symlink(), 'Never edit an existing release'
        assert a.api_release.name == HOST_SHA, 'New release must be named with reviewed source SHA'
        assert not dropin.exists() and not dropin.is_symlink(), 'Dedicated drop-in occupied; preserve it'
        assert not a.backup.exists(), 'Never overwrite rollback material'
        # Resolve import prerequisites before any production write.
        run(['/usr/bin/python3', '-c', 'import yaml'], stdout=subprocess.DEVNULL)
        a.backup.mkdir(parents=True, mode=0o700)
        a.backup.chmod(0o700)
        publications = []
        for name in ['builder/python', 'bin/wam']:
            src = a.os_home / name
            assert src.is_file() and not src.is_symlink()
            saved = a.backup / src.name
            shutil.copy2(src, saved)
            publications.append({'target': str(src), 'saved': str(saved)})
        journal = {'os_home': str(a.os_home), 'api_baseline': str(a.api_baseline),
                   'api_release': str(a.api_release), 'dropin': str(dropin), 'content': content,
                   'publications': publications, 'production_registry_modified': False}
        (a.backup / 'rollback.json').write_text(json.dumps(journal, indent=2) + '\n')
        a.api_release.mkdir(parents=True)
        with tarfile.open(a.source_archive) as archive:
            archive.extractall(a.api_release, filter='data')
        assert digest(a.api_release / 'wam/registry.py') == REGISTRY_SHA
        builder(a.api_release, a.os_home, 'install', a.builder_source)
        pointer(a.os_home, CANDIDATE)
        dropin.parent.mkdir(parents=True, exist_ok=True)
        with dropin.open('x') as stream:
            stream.write(content)
    else:
        journal = json.loads((a.backup / 'rollback.json').read_text())
        for key in ['os_home', 'api_baseline', 'api_release']:
            assert str(getattr(a, key)) == journal[key], 'Rollback target mismatch'
        assert str(dropin) == journal['dropin'] and content == journal['content']
        assert Path(show('WorkingDirectory')).resolve() in (a.api_baseline.resolve(), a.api_release.resolve()), 'API cwd drift; preserve it'
        # Accept only our baseline or candidate, including partial activation.
        current = (a.os_home / 'builder/current').resolve().name
        assert current in (BASE, CANDIDATE), 'Builder changed since activation; preserve it'
        pointer(a.os_home, current)
        if dropin.exists():
            assert not dropin.is_symlink() and dropin.read_text() == content, 'Drop-in drift'
        builder(a.api_baseline, a.os_home, 'rollback', BASE)
        pointer(a.os_home, BASE)
        for row in journal['publications']:
            shutil.copy2(row['saved'], row['target'])
        dropin.unlink(missing_ok=True)
    run(['systemctl', '--user', 'daemon-reload'])
    run(['systemctl', '--user', 'restart', UNIT])
    run(['systemctl', '--user', 'is-active', '--quiet', UNIT])
    expected = a.api_release if a.action == 'activate' else a.api_baseline
    assert Path(show('WorkingDirectory')).resolve() == expected.resolve()
    assert (Path('/proc') / show('MainPID') / 'cwd').resolve() == expected.resolve(), 'Process cwd mismatch'
    print(a.action + ': API process and managed builder pointers verified. Parent registry/lifecycle readback still required.')


if __name__ == '__main__':
    main()
