from pathlib import Path
import shutil, re, urllib.request, json, base64

ROOT=Path(__file__).resolve().parent

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
