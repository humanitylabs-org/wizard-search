#!/usr/bin/env python3
"""Bounded adapter around the existing fresh-box rig, installed WAM and shell.

Default is read-only preflight. --execute is for the parent's durable forum job.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time

SHA = '679be8ce8eea6ba13bf031104ea991202b5c373a'


def check_manifest(manifest):
    for name, expected in manifest.items():
        p = Path(name)
        assert p.is_file() and not p.is_symlink(), f'Missing/nonregular dependency: {p}'
        assert hashlib.sha256(p.read_bytes()).hexdigest() == expected, f'Drift: {p}'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('config', type=Path)
    ap.add_argument('--execute', action='store_true')
    args = ap.parse_args()
    cfg = json.loads(args.config.read_text())
    here = Path(__file__).resolve().parent
    check_manifest(cfg['files'])
    work = Path(cfg['work'])
    assert work.is_absolute() and str(work).startswith('/srv/work/')
    assert not work.exists(), 'Refuse reused mutable VM/evidence directory'
    assert re.fullmatch(r'nw-search-[a-z0-9-]+', cfg['vm'])
    assert cfg['release'] == '0.3.73' and cfg['search_commit'] == SHA
    assert shutil.disk_usage(work.parent).free >= 300 * 1024**3, '300 GiB admission floor'
    assert os.access('/dev/kvm', os.R_OK | os.W_OK), 'KVM unavailable to worker user'
    for command in ['python3', 'limactl', 'node', 'ssh']:
        assert shutil.which(command), f'Missing {command}'
    assert Path(cfg['playwright'], 'package.json').is_file()
    assert json.loads(Path(cfg['playwright'], 'package.json').read_text())['version'] == '1.64.1'
    print(json.dumps({'preflight':'PASS','release':cfg['release'],'search':SHA,'execute':args.execute}), flush=True)
    if not args.execute:
        return
    # Do not carry this worker's provider credentials into installer, browser or guest commands.
    env = {k:os.environ[k] for k in ('PATH','HOME','USER','LANG','WIZARD_HEAVY_JOB_ID','WIZARD_HEAVY_LOCK_FD') if k in os.environ}
    work.mkdir()
    out = work / 'evidence'
    out.mkdir()
    env['LIMA_HOME'] = str(work / 'lima')
    env['TMPDIR'] = str(work / 'tmp')
    Path(env['TMPDIR']).mkdir()
    vm = cfg['vm']
    tunnel = None
    receipt = {'search_commit':SHA,'base_release':cfg['release'],'scope':'installed WAM + stock dispatcher + real shell; no inference, Browser work or live deployment','state':'running','files':cfg['files']}

    def save():
        (out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')

    def run(name, argv, timeout, stdin=None):
        r = subprocess.run(argv, env=env, input=stdin, capture_output=True, text=True, timeout=timeout)
        (out / (name + '.log')).write_text(r.stdout + r.stderr)
        assert r.returncode == 0, f'{name} exit {r.returncode}; see its log'
        return r.stdout

    def shell(name, command, timeout=120, stdin=None):
        return run(name, ['limactl','shell','--workdir','/',vm,'bash','-lc',shlex.quote(command)], timeout, stdin)

    def guest(name, file):
        # Invoke the interpreter and source directory that the installed wam launcher owns.
        code = ('import os,re,subprocess; from pathlib import Path; '
                's=(Path.home()/".local/bin/wam").read_text(); '
                'm=re.search(r\'cd "([^\"]+)" && exec "([^\"]+)" -m wam\',s); '
                'assert m,"WAM launcher layout changed"; '
                f'p=Path.home()/"native-web-qa/{file}"; '
                'raise SystemExit(subprocess.call([m[2],str(p)],cwd=m[1],env={**os.environ,"PYTHONPATH":m[1]}))')
        return shell(name, 'sudo -iu wizard python3 -c ' + shlex.quote(code), 1500)

    def browser(mode, port):
        run(mode + '-browser', ['node',str(here/'browser.cjs'),cfg['playwright'],f'http://127.0.0.1:{port}',str(out),mode], 480)

    def terminate(signum, frame):
        raise InterruptedError(f'signal {signum}')

    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    signal.signal(signal.SIGALRM, terminate)
    signal.alarm(6000)
    try:
        save()
        # Fresh helper owns its VM creation/install/readback/stop. Never start an old saved VM.
        run('fresh-rig', ['python3',cfg['fresh_helper'],'--q2',cfg['base_runner'],'--lima',env['LIMA_HOME'],'--evidence',str(work/'fresh-evidence'),'--vm',vm,'--release',cfg['release'],'--step-timeout','2700'], 3500)
        run('start', ['limactl','start','--tty=false',vm], 300)
        payload = {p.name:base64.b64encode(p.read_bytes()).decode() for p in (here/'guest.py',here/'dispatcher.py',here/'notice.py')}
        payload['disposable.json'] = base64.b64encode((SHA+'\n').encode()).decode()
        payload['search-files.json'] = base64.b64encode(json.dumps(cfg['search_files']).encode()).decode()
        seed = ('import json,base64;from pathlib import Path; p=Path.home()/"native-web-qa";p.mkdir(exist_ok=False); '
                f'd=json.loads({json.dumps(json.dumps(payload))}); '
                '[(p.joinpath(k).write_bytes(base64.b64decode(v))) for k,v in d.items()]')
        shell('seed-owned-guest', 'sudo -iu wizard python3 -c ' + shlex.quote(seed))
        text = guest('install-and-dispatch', 'guest.py')
        marker = [x for x in text.splitlines() if x.startswith('NATIVE_WEB_GUEST=')]
        assert len(marker) == 1
        proof = json.loads(marker[0].split('=',1)[1])
        assert proof['search_commit'] == SHA and proof['result_count'] > 0
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0))
            port = sock.getsockname()[1]
        tunnel = subprocess.Popen(['ssh','-F',str(work/'lima'/vm/'ssh.config'),'-o','ExitOnForwardFailure=yes','-N','-L',f'127.0.0.1:{port}:127.0.0.1:{proof["shell_port"]}',f'lima-{vm}'], env=env, stdout=subprocess.DEVNULL, stderr=(out/'tunnel.log').open('w'))
        for attempt in range(60):
            assert tunnel.poll() is None, 'SSH tunnel exited'
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=1):
                    break
            except OSError:
                time.sleep(1)
        else:
            raise RuntimeError('SSH tunnel readiness timeout')
        browser('fresh', port)
        guest('paused-notice-seed', 'notice.py')
        browser('notice', port)
        export = ('import json,base64;from pathlib import Path;p=Path.home()/"native-web-qa";'
                  'print(json.dumps({n:base64.b64encode((p/n).read_bytes()).decode() for n in '
                  '["installed.json","running.json","dispatcher.json","dispatcher.log","install.log","candidate-pins.json"]}))')
        raw = shell('collect-guest-evidence','sudo -iu wizard python3 -c '+shlex.quote(export))
        for name, content in json.loads(raw).items():
            (out/name).write_bytes(base64.b64decode(content))
        receipt.update(state='PASS pending screenshot review', dispatcher=proof, model_driven='NOT RUN; no substitute model authorized')
    except Exception as error:
        receipt.update(state='FAIL', error=str(error))
        raise
    finally:
        signal.alarm(0)
        if tunnel:
            tunnel.terminate()
            try:
                tunnel.wait(timeout=10)
            except subprocess.TimeoutExpired:
                tunnel.kill(); tunnel.wait(timeout=5)
        stopped = subprocess.run(['limactl','stop','--force',vm],env=env,text=True,capture_output=True,timeout=120)
        (out/'stop.log').write_text(stopped.stdout+stopped.stderr)
        state = subprocess.run(['limactl','list','--json'],env=env,text=True,capture_output=True,timeout=30)
        (out/'lima-final.jsonl').write_text(state.stdout)
        rows = [json.loads(line) for line in state.stdout.splitlines() if line.startswith('{')]
        own = next((x for x in rows if x.get('name') == vm), None)
        receipt['cleanup'] = {'stop_exit':stopped.returncode,'own_vm':own,'verified_not_running':state.returncode == 0 and (own is None or own.get('status') == 'Stopped')}
        if not receipt['cleanup']['verified_not_running']:
            receipt['state'] = 'FAIL cleanup'
        save()
        assert receipt['cleanup']['verified_not_running'], 'Owned VM not confirmed stopped'


if __name__ == '__main__':
    main()
