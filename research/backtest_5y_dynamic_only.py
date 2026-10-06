from __future__ import annotations
import json
import backtest_5y as bt

def allocate_dynamic(cands,total):
    eligible=[dict(c) for c in cands if c.get('eligible',True)]
    if not eligible:return []
    for c in eligible:
        c['utility']=bt.utility(c); c['futures']=c['bot_type'] in bt.FUTURES_TYPES
    eligible.sort(key=lambda x:x['utility'],reverse=True)
    selected=[];pairs=set()
    for c in eligible:
        if len(selected)>=bt.MAX_BOTS:break
        if c['pair'] in pairs:continue
        selected.append(c);pairs.add(c['pair'])
    if not selected:selected=[eligible[0]]
    if len(selected)==1:
        w={selected[0]['key']:1.0}
    else:
        raw={c['key']:c['utility'] for c in selected};cap=max(bt.MAX_SINGLE,1/len(selected));w=bt.normalize_caps(raw,{c['key']:cap for c in selected})
        fk=[c['key'] for c in selected if c['futures']];sk=[c['key'] for c in selected if not c['futures']];ft=sum(w.get(k,0) for k in fk)
        if ft>bt.MAX_FUTURES and sk:
            scale=bt.MAX_FUTURES/ft;released=0.
            for k in fk:
                old=w[k];w[k]=old*scale;released+=old-w[k]
            st=sum(w[k] for k in sk)
            for k in sk:w[k]+=released*(w[k]/st if st>0 else 1/len(sk))
    out=[];running=0.
    for i,c in enumerate(selected):
        amt=round(total-running,2) if i==len(selected)-1 else round(total*w[c['key']],2)
        if i<len(selected)-1:running+=amt
        out.append({**c,'amount':amt,'pct':amt/total*100 if total else 0})
    return out

bt.allocate=allocate_dynamic
bt.main()
with open('backtest_result.json','r',encoding='utf-8') as f:r=json.load(f)
r['version']='dynamic-only'
r['method']['selection']='v1.3 dynamic competition, but original neutral news score 50.'
with open('backtest_result.json','w',encoding='utf-8') as f:json.dump(r,f,indent=2,ensure_ascii=False)
print('DYNAMIC_ONLY_SUMMARY',json.dumps(r['metrics'],ensure_ascii=False))
print('DYNAMIC_ONLY_MIX',json.dumps(r.get('allocation_mix_pct',{}),ensure_ascii=False))
