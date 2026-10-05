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


# Temporary deployment diagnostics for v1.1 source layout
try:
    print("=== OKX V1.1 SOURCE DIAGNOSTICS ===")
    for p in ROOT.rglob("*"):
        if p.is_file() and p.suffix.lower() in {".py",".js",".html"}:
            try:
                t=p.read_text(encoding="utf-8", errors="ignore")
                hits=[]
                for needle in ["En el último análisis","OPENAI_API_KEY","OKX_BASE_URL","Fuentes","assistant","chat"]:
                    if needle.lower() in t.lower(): hits.append(needle)
                if hits:
                    print("DIAGFILE", p.relative_to(ROOT), "HITS", ",".join(hits))
                    for line in t.splitlines():
                        if any(n.lower() in line.lower() for n in ["En el último análisis","OPENAI_API_KEY","OKX_BASE_URL","/api/assistant","chat"]):
                            print("DIAGLINE", p.relative_to(ROOT), line[:800])
            except Exception as e:
                pass
    print("=== END DIAGNOSTICS ===")
except Exception:
    pass

import runpy
runpy.run_path(str(ROOT / "run.py"), run_name="__main__")
