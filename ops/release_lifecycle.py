"""One Search lifecycle submission, durable receipt, bounded exact-image readback.

No guessed request-status endpoint. Runtipi wait_status alone can see the old running
container; require immutable Docker image ID, revision and Search HTTP health too.
"""
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request


def protected_write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, indent=2); stream.write('\n')
        stream.flush(); os.fsync(stream.fileno())
    os.replace(temp, path)


def inspect_container(name):
    raw = subprocess.check_output(['docker', 'inspect', name], stderr=subprocess.DEVNULL, timeout=5)
    return json.loads(raw)[0]


def read_health(url):
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.load(response)


def submit_and_verify(rt, urn, action, body, receipt, expected_image, expected_revision,
                      container, health_url, timeout=90, *, inspect=inspect_container,
                      health=read_health, clock=time.monotonic, sleep=time.sleep):
    """Never automatically resubmit after either an ambiguous POST/PATCH or timeout."""
    if action not in ('update', 'update-config'):
        raise ValueError('Unsupported Search release action')
    if not expected_image.startswith('sha256:') or not expected_revision:
        raise ValueError('Expected immutable image ID and revision required')
    receipt = Path(receipt)
    if receipt.exists():
        raise FileExistsError('Lifecycle receipt exists: inspect it; do not duplicate mutation')
    state = {'urn': urn, 'action': action, 'state': 'submission_started',
             'expected_image': expected_image, 'expected_revision': expected_revision,
             'automatic_resubmission': False}
    protected_write(receipt, state)
    # Exact API verified against the installed pinned wam/runtipi.py and AppFormBody.
    result = rt.req('PATCH', '/app-lifecycle/' + urn + '/' + action, body, timeout=120)
    request_id = result['requestId']
    if not isinstance(request_id, str) or not request_id:
        raise ValueError('Missing lifecycle requestId; inspect submission, never retry blindly')
    state.update(state='submitted', requestId=request_id)
    protected_write(receipt, state)  # Persist before the first wait/readback.
    deadline = clock() + timeout
    last = 'not yet observed'
    while clock() < deadline:
        try:
            status = rt.wait_status(urn, {'running'}, timeout=max(1, min(3, int(deadline-clock()))))
            live = inspect(container)  # May be absent during a legitimate recreate.
            exact = (status == 'running' and live['State']['Running'] is True
                     and live['Image'] == expected_image
                     and live['Config']['Labels'].get('org.opencontainers.image.revision') == expected_revision
                     and live['State'].get('Health', {}).get('Status', 'healthy') == 'healthy')
            last = {'status': status, 'image': live['Image'], 'running': live['State']['Running']}
            if exact and health(health_url).get('ok') is True:
                state.update(state='verified', observed=last)
                protected_write(receipt, state)
                return state
        except (subprocess.SubprocessError, OSError, RuntimeError, ValueError, KeyError) as ex:
            last = type(ex).__name__  # No keys, environment or response body in receipt.
        sleep(min(1, max(0, deadline-clock())))
    state.update(state='verification_timeout', observed=last)
    protected_write(receipt, state)
    raise TimeoutError('Lifecycle submitted once; exact-image health not verified in bounded wait; inspect receipt')
