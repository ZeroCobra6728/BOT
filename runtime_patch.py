from pathlib import Path
import shutil, re, urllib.request, json, base64

ROOT=Path(__file__).resolve().parent\n\nconfig_path=ROOT/"app/config.py"\nif config_path.exists():\n    cfg=config_path.read_text(encoding="utf-8")\n    if "gemini_api_key:" not in cfg:\n        cfg=cfg.replace("    openai_api_key: str | None = os.getenv("OPENAI_API_KEY") or os.getenv("AI_API_KEY") or None", "    openai_api_key: str | None = os.getenv("OPENAI_API_KEY") or os.getenv("AI_API_KEY") or None\n    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY") or None")\n        config_path.write_text(cfg,encoding="utf-8")
ai=ROOT/"ai_override.py"\ntry:\n    with urllib.request.urlopen("https://api.github.com/repos/ZeroCobra6728/BOT/git/blobs/ee7b4325a6abe38cf4fc4478dbc6f064c410acc4", timeout=10) as resp:\n        blob=json.load(resp)\n    ai.write_bytes(base64.b64decode(blob["content"]))\nexcept Exception as exc:\n    print(f"GEMINI_PATCH_FETCH_WARNING: {exc}", flush=True)
target=ROOT/"app/services/ai.py"
if ai.exists() and target.exists():
    shutil.copyfile(ai,target)

js_path=ROOT/"app/static/app.js"
if js_path.exists():
    js=js_path.read_text(encoding="utf-8")
    if "function humanSourceUrl(" not in js:
        helper=r'''
function humanSourceUrl(s,pair=''){
 const raw=String(s?.url||'');
 try{
   const u=new URL(raw);
   if(u.hostname.includes('okx.com') && u.pathname.startsWith('/api/')){
     let inst=u.searchParams.get('instId')||String(pair||'').replace('/','-');
     inst=inst.replace('-SWAP','');
     if(inst && inst.includes('-')) return 'https://www.okx.com/es-la/trade-spot/'+inst.toLowerCase();
     return 'https://www.okx.com/es-la/markets/rankings/spot';
   }
   if(u.hostname.includes('coingecko.com') && u.pathname.includes('/api/'))
     return 'https://www.coingecko.com/';
 }catch(e){}
 return raw||'#';
}
'''
        js=js.replace("function sourcesHtml(sources){",helper+"\nfunction sourcesHtml(sources){")
    js=js.replace('href="${esc(s.url)}"', 'href="${esc(humanSourceUrl(s))}"')
    js=js.replace('href="${esc(tf.source_url||\'#\')}"', 'href="${esc(humanSourceUrl({url:tf.source_url,name:tf.source},p.pair))}"')
    js_path.write_text(js,encoding="utf-8")
