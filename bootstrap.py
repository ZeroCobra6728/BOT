from __future__ import annotations
import base64, io, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MARKER = ROOT / ".runtime_extracted_v1_1"

def extract_runtime() -> None:
    if MARKER.exists() and (ROOT / "app" / "main.py").exists():
        return
    encoded = "".join(p.read_text(encoding="utf-8") for p in sorted(ROOT.glob("runtime_bundle.part*")))
    raw = base64.b64decode(encoded)
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        zf.extractall(ROOT)
    MARKER.write_text("okx-bot-analyzer-v1.1", encoding="utf-8")

extract_runtime()

import runpy
runpy.run_path(str(ROOT / "run.py"), run_name="__main__")
