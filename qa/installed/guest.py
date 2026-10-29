"""Run only as the synthetic wizard user in runner.py's new disposable VM."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlparse
from wam import cli, release_pins

SHA = '679be8ce8eea6ba13bf031104ea991202b5c373a'
ROOT = Path.home() / 'native-web-qa'
assert (ROOT / 'disposable.json').read_text().strip() == SHA
assert not any(os.environ.get(k) for k in ('GH_TOKEN', 'GITHUB_TOKEN', 'TINFOIL_API_KEY', 'OPENAI_API_KEY'))
ROOT.mkdir(exist_ok=True)


def run(argv, timeout=300, stdin=None, cwd=None):
    p = subprocess.run(argv, input=stdin, text=True, capture_output=True, timeout=timeout, cwd=cwd)
    # Only this newly provisioned guest. Never print Docker env or account files.
    if p.returncode:
        raise RuntimeError(f'{argv[0:3]} exit {p.returncode}: {p.stderr[-3000:]}')
    return p.stdout


def save(name, doc):
    (ROOT / name).write_text(json.dumps(doc, indent=2) + '\n')


c = cli.Config()
assert c.runtipi_root.is_relative_to(Path.home())
reg = json.loads((c.home / 'apps.json').read_text())
assert 'wizard-search' not in {x['id'] for x in reg['apps']}, 'Refuse reused/preinstalled Search'
release = json.loads((c.home / 'release.json').read_text())
assert release['release'] == '0.3.73'
# Extend an isolated local candidate snapshot; do not edit the published release or baseline receipt.
launcher = (Path.home() / '.local/bin/wam').read_text()
import re
pins_match = re.search(r'WIZARD_RELEASE_PINS=".*?-(.*?)\}"', launcher)
assert pins_match, 'Installed WAM launcher no longer advertises release pins'
baseline_pins = Path(pins_match[1])
pins = json.loads(baseline_pins.read_text())
assert pins['version'] == '0.3.73'
assert pins == json.loads((ROOT / 'base-release.json').read_text()), 'Published base manifest changed since staging'
pins['default_apps']['web-search'] = {'app': 'wizard-search', 'repo': 'humanitylabs-org/wizard-search', 'commit': SHA, 'index_version': '0.3.2'}
pinfile = ROOT / 'candidate-pins.json'
save(pinfile.name, pins)
os.environ['WIZARD_RELEASE_PINS'] = str(pinfile)
# REUSE WAM's pin-index adapter: CLI-only pins would be overwritten by manager index lookup.
image = release_pins.image_ref(pins['images']['wizard-app-manager'])
release_pins.configure_manager(c.runtipi_root / 'user-config/tipi-compose.yml', image, str(pinfile))
compose = ['sudo', '-n', 'docker', 'compose', '-p', 'runtipi', '-f', 'docker-compose.yml', '-f', 'user-config/tipi-compose.yml']
run(compose + ['up', '-d', '--force-recreate', '--wait', 'wizard-release-index'], cwd=c.runtipi_root)
run(compose + ['up', '-d', '--force-recreate', '--no-deps', 'runtipi'], cwd=c.runtipi_root)
for attempt in range(30):
    try:
        run([str(Path.home() / '.local/bin/wam'), 'apps', '--json'], timeout=40)
        break
    except RuntimeError:
        if attempt == 29:
            raise
        time.sleep(10)
# Fresh default first; keys are injected only AFTER its real bridge/UI search has passed.
install = run([str(Path.home() / '.local/bin/wam'), 'install', 'wizard-search'], timeout=1200)
(ROOT / 'install.log').write_text(install)
reg = json.loads(run([str(Path.home() / '.local/bin/wam'), 'apps', '--json']))
app = next(a for a in reg['apps'] if a['id'] == 'wizard-search')
assert app['status'] == 'running' and app.get('mcp') and app.get('view'), app
installed = c.runtipi_root / 'apps/wizardapps/wizard-search'
assert (installed / '.wizard-commit').read_text().strip() == SHA
assert json.loads((installed / '.wizard-source').read_text())['repo'] == 'humanitylabs-org/wizard-search'
expected = json.loads((ROOT / 'search-files.json').read_text())
containers = run(['sudo', '-n', 'docker', 'ps', '--filter', 'label=com.docker.compose.service=wizard-search', '--format', '{{.ID}}']).split()
assert len(containers) == 1
hash_code = 'import json,hashlib;from pathlib import Path;names=' + repr(list(expected)) + ';print(json.dumps({n:hashlib.sha256(Path("/app",n).read_bytes()).hexdigest() for n in names}))'
actual = json.loads(run(['sudo', '-n', 'docker', 'exec', containers[0], 'python3', '-c', hash_code]))
assert actual == expected, 'Running container does not contain the tested Search bytes'
image_id = run(['sudo', '-n', 'docker', 'inspect', containers[0], '--format', '{{.Image}}']).strip()
save('running.json', {'container': containers[0], 'image_id': image_id, 'files': actual})
save('installed.json', {'source': SHA, 'search': app, 'shell': next(a for a in reg['apps'] if a['id'] == 'wizard-ux')})
# Existing bridge wiring is installed by WAM; the engine uses its own generated config.
engine = run(['sudo', '-n', 'docker', 'ps', '--filter', 'label=com.docker.compose.service=hermes-agent-engine', '--format', '{{.ID}}']).split()
assert len(engine) == 1, 'Select the engine by service label, not package name/count'
probe = (ROOT / 'dispatcher.py').read_text()
result = run(['sudo', '-n', 'docker', 'exec', '-i', '-u', '1000:1000', engine[0], 'python', '-'], timeout=240, stdin=probe)
(ROOT / 'dispatcher.log').write_text(result)
marker = [l for l in result.splitlines() if l.startswith('NATIVE_WEB_DISPATCHER=')]
assert len(marker) == 1
proof = json.loads(marker[0].split('=', 1)[1])
assert proof['status']['policy']['mode'] == 'free-only' and proof['search']['results']
save('dispatcher.json', proof)
shell = next(a for a in reg['apps'] if a['id'] == 'wizard-ux')
port = urlparse(shell['view']['local']).port
assert port and 1024 <= port <= 65535
print('NATIVE_WEB_GUEST=' + json.dumps({'shell_port': port, 'search_commit': SHA, 'result_count': len(proof['search']['results'])}))
