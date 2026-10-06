from pathlib import Path

ROOT = Path(__file__).resolve().parent
js_path = ROOT / "app/static/app.js"

if js_path.exists():
    js = js_path.read_text(encoding="utf-8")
    # v1.3 source helper was inserted with literal \\n tokens, which breaks JS parsing.
    js = js.replace("\\nfunction humanSourceUrl(", "\nfunction humanSourceUrl(")
    js = js.replace("}\\n\nfunction sourcesHtml", "}\n\nfunction sourcesHtml")
    js_path.write_text(js, encoding="utf-8")
