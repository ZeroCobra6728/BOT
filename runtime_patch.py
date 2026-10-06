from pathlib import Path

ROOT=Path(__file__).resolve().parent

def patch(path, old, new, marker):
    p=ROOT/path
    if not p.exists(): return
    s=p.read_text(encoding='utf-8')
    if marker in s: return
    if old not in s: raise RuntimeError(f'Patch v1.3 no encontró bloque: {path}')
    p.write_text(s.replace(old,new,1),encoding='utf-8')

# 1) Noticias: sentimiento real y trazable en vez de score fijo 50.
p=ROOT/'app/services/news.py'
if p.exists():
    s=p.read_text(encoding='utf-8')
    if 'def _news_sentiment(' not in s:
        helper=r'''
POS_NEWS={"approved":8,"approval":7,"inflow":5,"adoption":5,"partnership":4,"upgrade":4,"record high":5,"all-time high":5,"surges":4,"rallies":4,"rebound":3,"recovers":3,"growth":3,"bullish":3}
NEG_NEWS={"bankruptcy":12,"bankrupt":12,"insolvency":12,"hack":11,"hacked":11,"exploit":10,"stolen":10,"withdrawals halted":12,"freeze withdrawals":12,"liquidation":7,"lawsuit":6,"sued":6,"rejected":6,"ban":8,"banned":8,"outage":6,"crash":9,"plunges":7,"slumps":6,"tumbles":6,"sell-off":6,"selloff":6,"falls":4,"drops":4,"fraud":10,"default":10}
SEVERE_NEWS={"bankruptcy","bankrupt","insolvency","hack","hacked","exploit","stolen","withdrawals halted","freeze withdrawals","fraud","default","crash"}
def _news_label(v):
    return "Muy negativo" if v<=25 else "Negativo" if v<45 else "Neutral" if v<=55 else "Positivo" if v<75 else "Muy positivo"
def _news_sentiment(items,pair):
    name,ticker=ASSET_NAMES[pair]; total=weight_sum=0.0; direct_n=high_n=0; out=[]
    for i,item in enumerate(items):
        text=str(item.get("title") or "").lower(); direct=name.lower() in text or f" {ticker.lower()} " in f" {text} "
        pos=[(k,w) for k,w in POS_NEWS.items() if k in text]; neg=[(k,w) for k,w in NEG_NEWS.items() if k in text]
        score=max(0.0,min(100.0,50+sum(w for _,w in pos)*1.35-sum(w for _,w in neg)*1.55))
        severe=any(k in text for k in SEVERE_NEWS); impact="alta" if severe or len(neg)>=2 or (direct and (score<=30 or score>=75)) else "media" if direct or score<42 or score>62 else "baja"
        direct_n+=1 if direct else 0; high_n+=1 if impact=="alta" else 0
        w=(1.0 if direct else .65)*(1.0/(1+.15*i))*(1.2 if impact=="alta" else 1.0 if impact=="media" else .8)
        total+=score*w; weight_sum+=w
        row=dict(item); row.update({"sentiment_score":round(score,1),"sentiment_label":_news_label(score),"impact":impact,"direct_asset_relevance":direct,"sentiment_signals":{"positive":[k for k,_ in pos][:4],"negative":[k for k,_ in neg][:4]}}); out.append(row)
    overall=round(total/weight_sum if weight_sum else 50.0,1)
    confidence=round(min(85.0,38+min(25,len(out)*6)+min(14,direct_n*4)+min(8,high_n*2)),1)
    return out,overall,confidence,_news_label(overall)
'''
        s=s.replace('class NewsService:',helper+'\nclass NewsService:',1)
    old='''        if not dedup:\n            return {"status":"UNAVAILABLE","score":50.0,"confidence":30.0,"items":[],"warning":"No fue posible obtener noticias curadas en esta consulta.","fetched_at":now}\n        return {"status":"OK","score":50.0,"confidence":55.0,"items":dedup,"warning":None,"fetched_at":now}\n'''
    new='''        if not dedup:\n            return {"status":"UNAVAILABLE","score":50.0,"confidence":30.0,"items":[],"summary":"Sin noticias suficientes: sentimiento neutral.","warning":"No fue posible obtener noticias curadas en esta consulta.","fetched_at":now}\n        items,score,confidence,label=_news_sentiment(dedup,pair)\n        return {"status":"OK","score":score,"confidence":confidence,"items":items,"summary":f"Sentimiento de noticias: {label} ({score:.0f}/100).","warning":None,"fetched_at":now}\n        # v1.3-news-sentiment\n'''
    if 'v1.3-news-sentiment' not in s:
        if old not in s: raise RuntimeError('Patch v1.3 news return no encontrado')
        s=s.replace(old,new,1)
    s=s.replace('OKX-Bot-Analyzer/1.1','OKX-Bot-Analyzer/1.3')
    p.write_text(s,encoding='utf-8')

# 2) Nuevos candidatos sí pueden desplazar bots existentes; continuidad queda como bonus.
patch('app/services/allocation.py',
'''    eligible.sort(key=lambda x: x["utility"], reverse=True)\n    # Keep viable existing bots first; only displace them when evidence is materially poor.\n    existing = [c for c in eligible if c.get("existing") and c.get("score", 0) >= 40 and c.get("risk_score", 100) < 80]\n    selected = existing[: settings.risk.max_recommended_bots]\n    selected_keys = {c["key"] for c in selected}\n    for c in eligible:\n        if len(selected) >= settings.risk.max_recommended_bots:\n            break\n        if c["key"] in selected_keys:\n            continue\n        # avoid stacking many new strategies on the same asset unless needed\n        if any(x["pair"] == c["pair"] and not c.get("existing") for x in selected):\n            continue\n        selected.append(c); selected_keys.add(c["key"])\n    if not selected:\n        selected = [eligible[0]]\n''',
'''    eligible.sort(key=lambda x: x["utility"], reverse=True)\n    # v1.3: todos compiten por utilidad; el bot existente conserva solo el bonus de continuidad.\n    selected=[]; selected_pairs=set()\n    for c in eligible:\n        if len(selected) >= settings.risk.max_recommended_bots: break\n        if c["pair"] in selected_pairs: continue\n        selected.append(c); selected_pairs.add(c["pair"])\n    if not selected: selected=[eligible[0]]\n    # v1.3-dynamic-selection\n''','v1.3-dynamic-selection')

# 3) Noticias muy negativas elevan riesgo y reducen score; positivas solo confirman moderadamente.
patch('app/services/recommendation.py',
'''    score = overall_score(base=base, compatibility=compat, performance=performance, risk_score=risk["score"], capital_efficiency=cap_eff,\n                          news_sentiment=state.get("news", {}).get("score", 50), confidence=confidence)\n    return {"score": score, "compatibility": compat, "risk": risk, "confidence": round(confidence, 1), "positive": pos, "negative": neg, "direction": direction}\n''',
'''    news=state.get("news",{}) or {}; news_score=float(news.get("score",50) or 50); news_conf=float(news.get("confidence",30) or 30)\n    score = overall_score(base=base, compatibility=compat, performance=performance, risk_score=risk["score"], capital_efficiency=cap_eff,\n                          news_sentiment=news_score, confidence=confidence)\n    risk=dict(risk); risk["reasons"]=list(risk.get("reasons",[]))\n    if news_conf>=45 and news_score<=35:\n        score=max(0.0,round(score-min(10.0,(35-news_score)*.40+2),1)); risk["score"]=round(min(100.0,float(risk["score"])+min(12.0,(35-news_score)*.45+2)),1)\n        risk["reasons"].append(f"Noticias relevantes con sentimiento muy negativo ({news_score:.0f}/100).")\n        if bot_type in {BotType.FUTURES_GRID,BotType.FUTURES_DCA,BotType.SIGNAL_BOT} and risk["score"]>=settings.risk.futures_ineligible_risk: risk["eligible"]=False\n    elif news_conf>=50 and news_score>=70:\n        score=min(100.0,round(score+min(3.0,(news_score-65)*.12),1))\n    return {"score": score, "compatibility": compat, "risk": risk, "confidence": round(confidence, 1), "positive": pos, "negative": neg, "direction": direction}\n    # v1.3-news-risk-overlay\n''','v1.3-news-risk-overlay')

# 4) Mostrar el efecto de noticias dentro de la explicación de cada recomendación.
patch('app/services/public_analysis.py',
'''    negatives=list(ev["negative"])+list(ev["risk"]["reasons"])\n    if not negatives:\n        negatives=["No se detectó un factor negativo dominante, pero el mercado puede cambiar y el capital sigue expuesto a pérdidas."]\n''',
'''    negatives=list(ev["negative"])+list(ev["risk"]["reasons"])\n    news=state.get("news",{}) or {}\n    if news.get("status")=="OK":\n        ns=float(news.get("score",50) or 50)\n        if ns<=40: negatives.append(f"Sentimiento de noticias negativo: {ns:.0f}/100; se incorpora como factor de riesgo, no como señal aislada.")\n        elif ns>=60: reasons.append(f"Sentimiento de noticias positivo: {ns:.0f}/100; se usa solo como confirmación secundaria.")\n    if not negatives:\n        negatives=["No se detectó un factor negativo dominante, pero el mercado puede cambiar y el capital sigue expuesto a pérdidas."]\n    # v1.3-news-explanation\n''','v1.3-news-explanation')

# Versión backend.
p=ROOT/'app/config.py'
if p.exists():
    s=p.read_text(encoding='utf-8').replace('APP_VERSION = "1.1"','APP_VERSION = "1.3"')
    p.write_text(s,encoding='utf-8')

# UI + fuentes legibles; se mantiene el botón IA oculto.
p=ROOT/'app/static/app.js'
if p.exists():
    js=p.read_text(encoding='utf-8')
    js=js.replace('v1.1','v1.3').replace('V1.1','V1.3').replace('Versión 1.1','Versión 1.3')
    js+='\n// v1.3 UI cleanup\ndocument.addEventListener("DOMContentLoaded",()=>{document.querySelectorAll("body *").forEach(el=>{if(el.children.length===0&&el.textContent)el.textContent=el.textContent.replace(/Versión 1\\.[12]/g,"Versión 1.3").replace(/v1\\.[12]/g,"v1.3").replace(/V1\\.[12]/g,"V1.3")});const ai=[...document.querySelectorAll("button,a,div")].find(el=>el.textContent.trim()==="IA"&&el.children.length===0);if(ai)(ai.closest("button")||ai).style.display="none"});\n'
    if 'function humanSourceUrl(' not in js:
        helper=r'''\nfunction humanSourceUrl(s,pair=''){const raw=String(s?.url||'');try{const u=new URL(raw);if(u.hostname.includes('okx.com')&&u.pathname.startsWith('/api/')){let inst=u.searchParams.get('instId')||String(pair||'').replace('/','-');inst=inst.replace('-SWAP','');if(inst&&inst.includes('-'))return 'https://www.okx.com/es-la/trade-spot/'+inst.toLowerCase();return 'https://www.okx.com/es-la/markets/rankings/spot'}if(u.hostname.includes('coingecko.com')&&u.pathname.includes('/api/'))return 'https://www.coingecko.com/'}catch(e){}return raw||'#'}\n'''
        js=js.replace('function sourcesHtml(sources){',helper+'\nfunction sourcesHtml(sources){')
    js=js.replace('href="${esc(s.url)}"','href="${esc(humanSourceUrl(s))}"')
    js=js.replace('href="${esc(tf.source_url||\'#\')}"','href="${esc(humanSourceUrl({url:tf.source_url,name:tf.source},p.pair))}"')
    p.write_text(js,encoding='utf-8')

# Validación de sintaxis antes de iniciar servidor.
for rel in ['app/services/news.py','app/services/allocation.py','app/services/recommendation.py','app/services/public_analysis.py','app/config.py']:
    p=ROOT/rel
    if p.exists(): compile(p.read_text(encoding='utf-8'),str(p),'exec')
