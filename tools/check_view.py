from pathlib import Path
import ast
root = Path(__file__).resolve().parents[1]
ast.parse((root / "server.py").read_text())
for name in ("index.html", "app.js", "app.css", "icon.svg"):
    assert (root / "web" / name).is_file(), name
assert "/wizard-os-home/core/app-client.js" in (root / "web/index.html").read_text()
print("view source and runtime syntax OK")
