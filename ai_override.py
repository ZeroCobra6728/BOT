from __future__ import annotations
import base64, json, re
import httpx
from app.config import settings

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"\nGEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

def _extract_text(payload: dict) -> str:
    if payload.get("output_text"):
        return str(payload["output_text"]).strip()
    parts=[]
    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue
        for c in item.get("content", []):
            if c.get("type") in {"output_text","text"} and c.get("text"):
                parts.append(c["text"])
    return "\n".join(parts).strip()

async def _response(input_items, instructions: str, max_output_tokens: int=900) -> str:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY no configurada")
    if isinstance(input_items, str):
        input_items=[{"role":"user","content":input_items}]
    payload={
        "model":"gpt-6-luna",
        "instructions":instructions,
        "input":input_items,
        "max_output_tokens":max_output_tokens,
        "store":False,
    }
    headers={"Authorization":f"Bearer {settings.openai_api_key}","Content-Type":"application/json"}
    async with httpx.AsyncClient(timeout=40.0) as client:
        r=await client.post(OPENAI_RESPONSES_URL,headers=headers,json=payload)
        if r.status_code >= 400:
            detail=""
            try:
                detail=(r.json().get("error") or {}).get("message","")
            except Exception:
                detail=r.text[:300]
            raise RuntimeError(f"OpenAI HTTP {r.status_code}: {detail[:300]}")
        data=r.json()
    text=_extract_text(data)
    if not text:
        raise RuntimeError("OpenAI no devolvió texto")
    return text

def _sources(context: dict):
    return ((context.get("analysis") or {}).get("sources") or [])[:8]

async def _gemini_text(prompt: str) -> str:
    import os
    key=os.getenv("GEMINI_API_KEY","").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY no configurada")
    async with httpx.AsyncClient(timeout=40.0) as client:
        r=await client.post(GEMINI_URL,headers={"x-goog-api-key":key,"Content-Type":"application/json"},json={"contents":[{"parts":[{"text":prompt}]}]})
    if r.status_code >= 400:
        detail=r.text[:300]
        raise RuntimeError(f"Gemini HTTP {r.status_code}: {detail}")
    data=r.json()
    parts=((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    text="".join(str(p.get("text","")) for p in parts).strip()
    if not text:
        raise RuntimeError("Gemini no devolvió texto")
    return text

async def answer_assistant(message: str, page: str, context: dict) -> dict:
    if not settings.openai_api_key:
        return {"answer":"La IA no está configurada en el servidor. El administrador debe configurar OPENAI_API_KEY.","sources":_sources(context),"mode":"error","warning":"OPENAI_API_KEY no configurada"}
    compact={
        "page":page,
        "bots":context.get("bots",[])[:8],
        "portfolio":context.get("portfolio",{}),
        "analysis":context.get("analysis",{}),
        "history":context.get("history",[])[:3],
    }
    raw=json.dumps(compact,ensure_ascii=False,default=str)
    if len(raw)>22000:
        raw=raw[:22000]
    instructions=(
        "Eres el Asistente de OKX Bot Analyzer. Conversa naturalmente y responde siempre en español. "
        "Puedes responder preguntas generales aunque no estén relacionadas con trading. "
        "Para preguntas sobre el portafolio, bots, scores, precios, mercado o decisiones de esta aplicación, usa el contexto JSON proporcionado como fuente de verdad y no inventes datos faltantes. "
        "Si el usuario pide información actual que no está en el contexto, dilo claramente. "
        "Cuando expliques una recomendación financiera, incluye riesgos relevantes y no prometas rentabilidad. "
        "La política de esta herramienta busca distribuir el 100% del capital entre estrategias elegibles, pero eso no implica seguridad. "
        "Sé útil, directo y evita repetir automáticamente la recomendación principal si la pregunta no la solicita."
    )
    prompt=f"Pregunta del usuario: {message}\n\nContexto actual de OKX Bot Analyzer (puede estar vacío):\n{raw}"
    try:
        text=await _gemini_text(instructions+"\\n\\n"+prompt)
        return {"answer":text,"sources":_sources(context),"mode":"ia"}
    except Exception as exc:
        msg=str(exc)
        print(f"GEMINI_ASSISTANT_ERROR: {msg}", flush=True)
        public="El asistente gratuito de Gemini no pudo responder en este momento."
        if "429" in msg:
            public+=" Gemini respondió con un límite temporal o de cuota del nivel gratuito."
        elif "401" in msg:
            public+=" Gemini rechazó la clave configurada; revisa GEMINI_API_KEY."
        elif "403" in msg:
            public+=" La clave/proyecto no tiene permiso para usar el modelo configurado."
        return {"answer":public,"sources":_sources(context),"mode":"error","warning":msg[:220]}

async def analyze_screenshots(files: list[tuple[str,str,bytes]]) -> dict:
    if not settings.openai_api_key:
        return {"provider_status":"NO_CONFIGURADO","detected":{},"contradictions":[],"message":"La visión automática requiere OPENAI_API_KEY en el servidor."}
    content=[{"type":"input_text","text":"Analiza estas capturas de bots de OKX. Devuelve SOLO JSON válido con claves: pair, bot_type, roi, pnl, capital, duration_hours, grid_profit, floating_pnl, date, lower_price, upper_price, leverage, contradictions. Usa null si no es visible y no inventes valores."}]
    for name,mime,data in files[:4]:
        b64=base64.b64encode(data).decode("ascii")
        content.append({"type":"input_image","image_url":f"data:{mime};base64,{b64}","detail":"high"})
    try:
        text=await _response([{"role":"user","content":content}],"Extrae únicamente datos visibles de capturas de OKX. No infieras números ocultos.",900)
        cleaned=re.sub(r"^```(?:json)?|```$","",text.strip(),flags=re.MULTILINE).strip()
        detected=json.loads(cleaned)
        contradictions=detected.pop("contradictions",[]) if isinstance(detected,dict) else []
        return {"provider_status":"OK","detected":detected,"contradictions":contradictions,"message":"Datos detectados por visión. Revisa y confirma antes de guardar."}
    except Exception as exc:
        print(f"OPENAI_VISION_ERROR: {exc}", flush=True)
        return {"provider_status":"ERROR","detected":{},"contradictions":[],"message":"No fue posible analizar las capturas automáticamente. Revisa la configuración de OpenAI e introduce los datos manualmente."}
