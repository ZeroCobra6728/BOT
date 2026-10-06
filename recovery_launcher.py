from __future__ import annotations
import base64, io, zipfile, runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MARKER = ROOT / ".runtime_extracted_recovery_v14"

def extract_runtime() -> None:
    if MARKER.exists() and (ROOT / "app" / "main.py").exists():
        return
    encoded = "".join(p.read_text(encoding="utf-8") for p in sorted(ROOT.glob("runtime_bundle.part*")))
    raw = base64.b64decode(encoded)
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        zf.extractall(ROOT)
    MARKER.write_text("okx-bot-analyzer-recovery-v1.4", encoding="utf-8")

extract_runtime()
runpy.run_path(str(ROOT / "runtime_patch.py"), run_name="__runtime_patch__")
runpy.run_path(str(ROOT / "runtime_js_fix.py"), run_name="__runtime_js_fix__")

# Recovery of the frontend parser repair that existed in the last known-good v1.3.
js_path = ROOT / "app" / "static" / "app.js"
if js_path.exists():
    js = js_path.read_text(encoding="utf-8")
    js = js.replace("\\nfunction humanSourceUrl(", "\nfunction humanSourceUrl(")
    js = js.replace("}\\n\nfunction sourcesHtml", "}\n\nfunction sourcesHtml")
    js_path.write_text(js, encoding="utf-8")

runpy.run_path(str(ROOT / "run.py"), run_name="__main__")
