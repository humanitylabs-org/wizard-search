# Bridge-only upstream authentication repair (parent only)

The observed 502 came from forwarding JSON without the approved loopback proxy's
required provider Authorization. Search's app-only caller token is not that key.
`private-proxy-bridge.py` now requires `--upstream-token-file`, validates its regular
mode-0600 file before binding, and sends its value only to the explicitly approved
loopback `/v1/chat/completions`. Redirects fail closed. Errors remain generic; no
headers, bodies or credential values are logged. There is no credential discovery.

## Already packaged release: do not rerun package

The parent first provisions **only the existing approved main legacy Search
TINFOIL_API_KEY** into `$BACKUP/upstream-token`, without displaying its value.
The file must be regular, not a symlink, mode 0600, with one ASCII token and at
most 8192 bytes; the existing `$BACKUP` must remain mode 0700. Never inspect the
upstream service's private owning agent/container, create an account/key, or put
this key in the app container, repo, image, environment arguments or command line.

Set `SOURCE` to the clean pushed bridge-fix checkout and `BACKUP` to the already
active release's `parent-backup`. The following commands **are parent actions,
not executed by the bridge-fix builder**. They back up the old helper/unit without
overwriting previous repair backups, update only this helper and one bridge-unit
argument, restart only the bridge, then read back that exact target. Any unexpected
unit drift aborts before writes. Existing Search caller token and upstream/model,
container/image, lifecycle receipts, root routes and legacy service are untouched.

```sh
set -eu
export SOURCE BACKUP
python3 -c '
import hmac, os, runpy, shutil, stat
from pathlib import Path
source=Path(os.environ["SOURCE"]); backup=Path(os.environ["BACKUP"])
assert stat.S_IMODE(backup.stat().st_mode)==0o700, "Protect backup directory first"
unit=Path.home()/".config/systemd/user/wizard-search-private-proxy.service"
helper=backup/"private-proxy-bridge.py"; upstream=backup/"upstream-token"
read=runpy.run_path(str(source/"ops/private-proxy-bridge.py"))["read_upstream_token"]
assert not hmac.compare_digest(read(upstream),(backup/"proxy-token").read_text().strip()), "Credentials must differ"
old=unit.read_text()
needle=" --upstream http://127.0.0.1:3301/v1/chat/completions"
assert old.count("ExecStart=")==1 and old.count(needle)==1 and str(helper) in old
assert "--upstream-token-file" not in old, "Inspect already-updated unit rather than overwriting"
assert helper.is_file()
assert not (backup/"bridge-before-upstream-auth.py").exists()
assert not (backup/"bridge-before-upstream-auth.service").exists()
new=old.replace(needle," --upstream-token-file "+str(upstream)+needle)
shutil.copy2(helper,backup/"bridge-before-upstream-auth.py")
shutil.copy2(unit,backup/"bridge-before-upstream-auth.service")
shutil.copy2(source/"ops/private-proxy-bridge.py",helper)
unit.write_text(new)
assert unit.read_text()==new and helper.read_bytes()==(source/"ops/private-proxy-bridge.py").read_bytes()
print("Bridge helper and explicit upstream credential path installed; no app/image changes")
'
systemctl --user daemon-reload
systemctl --user restart wizard-search-private-proxy.service
systemctl --user is-active wizard-search-private-proxy.service
systemctl --user show wizard-search-private-proxy.service -p ExecStart -p ActiveState -p SubState -p MainPID
cmp "$SOURCE/ops/private-proxy-bridge.py" "$BACKUP/private-proxy-bridge.py"
```

Read back the same bridge via harmless real inference, without printing response
content or credentials (the gateway is the parent's already-discovered gateway):

```sh
export BRIDGE_URL=http://10.128.40.1:19332/v1/chat/completions
python3 -c '
import json, os, urllib.error, urllib.request
from pathlib import Path
caller=(Path(os.environ["BACKUP"])/"proxy-token").read_text().strip()
body=json.dumps({"model":"gpt-oss-120b","messages":[{"role":"user","content":"Reply only SEARCH OK"}],"reasoning_effort":"low","max_tokens":32,"stream":False}).encode()
request=urllib.request.Request(os.environ["BRIDGE_URL"],data=body,headers={"Content-Type":"application/json","Authorization":"Bearer "+caller})
try:
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=120) as response:
        status=response.status; value=json.load(response)
except urllib.error.HTTPError as error:
    code=error.code; error.close(); raise SystemExit("Bridge readback failed: HTTP "+str(code)) from None
except (OSError,ValueError):
    raise SystemExit("Bridge readback failed; no response body logged") from None
assert status==200 and value.get("choices"), "No successful chat completion"
print("Bridge readback: HTTP 200 with chat choices")
'
```

This proves the bridge HTTP path only. Parent still owns real installed Search
overview/translation/OCR and device acceptance; synthetic regressions do not prove
those surfaces. This change does not require an app image rebuild or model change.

## Future new packages

Pass `--upstream-token-file /explicit/protected/input` to `parent-release.py package`.
Its preflight validates before its first production write, then copies the value
with exclusive mode-0600 creation to the protected backup. Its unit contains only
the file path; Search's container still receives only the separate caller token.
For the current already-packaged release use the bridge-only commands above.

## Focused verification

`PYTHONDONTWRITEBYTECODE=1 python3 qa/bridge-auth-test.py` uses synthetic secrets,
ephemeral loopback servers and stdlib only. It checks correct separate upstream
Authorization and byte-preserved requests/streaming, wrong/missing/provider caller
credentials rejected before upstream, no forwarded caller-only headers, unchanged
origin/path/model gates, generic/log-safe upstream failures, redirect refusal,
missing/unsafe/empty/oversized/malformed/symlink/FIFO credential files rejected
before listening, distinct credential roles, and actual package preflight ordering.
`qa/bridge-proof.py` retains its Forum-only disposable Docker streaming fixture and
now supplies/asserts separate upstream credentials; no heavy job was submitted here.
