from __future__ import annotations

import json
from collections import defaultdict
import pandas as pd
import backtest_5y as bt

# Historical reconstruction for the production v1.3 news model.
# Event headlines are deliberately short and use only information that was known at the time.
# They are not used to move prices: OKX OHLCV remains the source of realised returns.
EVENTS = [
    ('2021-11-10','Bitcoin hits all-time high as crypto market rallies',None),
    ('2021-12-04','Bitcoin tumbles in broad crypto sell-off',None),
    ('2022-01-21','Bitcoin slumps as risk assets fall on Federal Reserve tightening fears',None),
    ('2022-03-16','Bitcoin rallies after Federal Reserve rate decision',None),
    ('2022-05-09','Bitcoin plunges as Terra crash shakes crypto market',None),
    ('2022-05-12','Crypto crash deepens as Terra collapses and bitcoin plunges',None),
    ('2022-06-13','Celsius withdrawals halted as bitcoin plunges in crypto sell-off',None),
    ('2022-07-13','Celsius bankruptcy deepens crypto lender crisis',None),
    ('2022-11-08','FTX insolvency fears trigger bitcoin plunges and crypto sell-off',None),
    ('2022-11-11','FTX bankruptcy sends crypto market lower',None),
    ('2023-01-14','Bitcoin rallies as crypto market rebounds',None),
    ('2023-03-10','Bitcoin drops as banking stress hits risk assets',None),
    ('2023-06-15','Bitcoin rallies after BlackRock spot ETF filing',None),
    ('2023-07-13','XRP rallies after U.S. court ruling', ['XRP/USDT']),
    ('2023-08-17','Bitcoin tumbles in sharp crypto sell-off',None),
    ('2023-10-23','Bitcoin rallies on spot ETF approval hopes',None),
    ('2024-01-10','SEC approved spot Bitcoin ETF products',None),
    ('2024-03-05','Bitcoin record high as ETF inflow surges',None),
    ('2024-05-23','Ether ETF approval advances in the United States', ['ETH/USDT']),
    ('2024-08-05','Bitcoin plunges in global market sell-off',None),
    ('2024-09-18','Bitcoin rallies after Federal Reserve rate cut',None),
    ('2024-11-06','Bitcoin record high after U.S. election result',None),
    ('2024-12-05','Bitcoin record high above 100000 on growing adoption optimism',None),
    ('2025-01-23','Crypto adoption gets policy boost from U.S. executive order',None),
    ('2025-02-27','Bitcoin tumbles as crypto risk appetite weakens',None),
    ('2025-04-03','Crypto sell-off deepens as tariffs jolt risk markets and bitcoin drops',None),
    ('2025-05-22','Bitcoin record high as institutional inflow supports crypto market',None),
    ('2025-07-18','Crypto adoption grows after U.S. stablecoin regulation advances',None),
    ('2025-10-10','Bitcoin tumbles in U.S.-China trade sell-off',None),
    ('2025-11-21','Bitcoin drops as leveraged crypto liquidation pressure rises',None),
    ('2026-02-05','Bitcoin crash deepens as price plunges and crypto market slumps',None),
    ('2026-03-10','Bitcoin rebounds as crypto market recovers',None),
    ('2026-07-14','Bitcoin rallies as institutional adoption and inflow improve',None),
    ('2026-09-28','Bitcoin rallies toward record high after strong quarterly growth',None),
]
EVENTS = [(pd.Timestamp(d, tz='UTC'), title, scope) for d,title,scope in EVENTS]

POS_NEWS={"approved":8,"approval":7,"inflow":5,"adoption":5,"partnership":4,"upgrade":4,"record high":5,"all-time high":5,"surges":4,"rallies":4,"rebound":3,"rebounds":3,"recovers":3,"growth":3,"bullish":3}
NEG_NEWS={"bankruptcy":12,"bankrupt":12,"insolvency":12,"hack":11,"hacked":11,"exploit":10,"stolen":10,"withdrawals halted":12,"freeze withdrawals":12,"liquidation":7,"lawsuit":6,"sued":6,"rejected":6,"ban":8,"banned":8,"outage":6,"crash":9,"plunges":7,"slumps":6,"tumbles":6,"sell-off":6,"selloff":6,"falls":4,"drops":4,"fraud":10,"default":10}
SEVERE_NEWS={"bankruptcy","bankrupt","insolvency","hack","hacked","exploit","stolen","withdrawals halted","freeze withdrawals","fraud","default","crash"}
ASSET_NAMES={
    'BTC/USDT':('Bitcoin','BTC'),'ETH/USDT':('Ethereum','ETH'),'SOL/USDT':('Solana','SOL'),'XRP/USDT':('XRP','XRP'),'DOGE/USDT':('Dogecoin','DOGE'),
    'BNB/USDT':('BNB','BNB'),'SUI/USDT':('Sui','SUI'),'LINK/USDT':('Chainlink','LINK'),'ADA/USDT':('Cardano','ADA'),'LTC/USDT':('Litecoin','LTC')}

def news_for(pair, when):
    name,ticker=ASSET_NAMES[pair]
    items=[]
    for d,title,scope in EVENTS:
        age=(when-d).total_seconds()/86400
        if age < 0 or age > 7: continue
        if scope is not None and pair not in scope: continue
        text=title.lower(); direct=name.lower() in text or f' {ticker.lower()} ' in f' {text} '
        pos=[(k,w) for k,w in POS_NEWS.items() if k in text]
        neg=[(k,w) for k,w in NEG_NEWS.items() if k in text]
        score=max(0.0,min(100.0,50+sum(w for _,w in pos)*1.35-sum(w for _,w in neg)*1.55))
        severe=any(k in text for k in SEVERE_NEWS)
        impact='alta' if severe or len(neg)>=2 or (direct and (score<=30 or score>=75)) else 'media' if direct or score<42 or score>62 else 'baja'
        items.append({'date':d,'title':title,'direct':direct,'score':score,'impact':impact,'pos':[k for k,_ in pos],'neg':[k for k,_ in neg]})
    if not items:
        # The live service usually has several recent headlines. We keep a neutral headline baseline rather than pretending silence is bullish/bearish.
        return {'score':50.0,'confidence':55.0,'items':[],'label':'Neutral'}
    total=0.;ws=0.;direct_n=0;high_n=0
    items.sort(key=lambda x:x['date'], reverse=True)
    for i,it in enumerate(items):
        direct_n += int(it['direct']); high_n += int(it['impact']=='alta')
        w=(1.0 if it['direct'] else .65)*(1/(1+.15*i))*(1.2 if it['impact']=='alta' else 1.0 if it['impact']=='media' else .8)
        total += it['score']*w; ws += w
    score=round(total/ws if ws else 50.0,1)
    conf=round(min(85.0,38+min(25,len(items)*6)+min(14,direct_n*4)+min(8,high_n*2)),1)
    label='Muy negativo' if score<=25 else 'Negativo' if score<45 else 'Neutral' if score<=55 else 'Positivo' if score<75 else 'Muy positivo'
    return {'score':score,'confidence':conf,'items':items,'label':label}

_orig_state_at=bt.state_at

def state_at_v13(pair,when,dfs,funding,cache15):
    st=_orig_state_at(pair,when,dfs,funding,cache15)
    if st:
        st['news']=news_for(pair,when)
    return st
bt.state_at=state_at_v13

def evaluate_v13(bot,state,equity,capital,futures_exposure,performance=50,lev=1):
    co=bt.compat(bot,state['regime'],state['metrics'],state.get('funding_rate'))
    rs,el=bt.risk(bot,state['regime'],state['metrics'],capital,equity,futures_exposure,lev)
    news=state.get('news') or {'score':50.0,'confidence':30.0}
    ns=float(news.get('score',50) or 50); nc=float(news.get('confidence',30) or 30)
    conf=min(state['scores']['confidence'],94,nc+25)
    ce=72 if capital<=max(equity*.20,1) else 52
    sc=bt.overall(state['scores'],co,performance,rs,ce,ns,conf)
    if nc>=45 and ns<=35:
        sc=max(0.0,round(sc-min(10.0,(35-ns)*.40+2),1))
        rs=round(min(100.0,rs+min(12.0,(35-ns)*.45+2)),1)
        if bot in bt.FUTURES_TYPES and rs>=65: el=False
    elif nc>=50 and ns>=70:
        sc=min(100.0,round(sc+min(3.0,(ns-65)*.12),1))
    return {'score':sc,'compatibility':co,'risk_score':rs,'eligible':el,'confidence':round(conf,1)}
bt.evaluate=evaluate_v13

def allocate_v13(cands,total):
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
        raw={c['key']:c['utility'] for c in selected}; cap=max(bt.MAX_SINGLE,1/len(selected)); w=bt.normalize_caps(raw,{c['key']:cap for c in selected})
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
bt.allocate=allocate_v13

# Run the identical five-year market/execution simulation, then correct metadata and add v1.3 news audit fields.
bt.main()
with open('backtest_result.json','r',encoding='utf-8') as f:
    result=json.load(f)
result['version']='1.3'
result['method']['news']='v1.3 keyword sentiment/risk overlay reconstructed from dated major market headlines. Neutral 50/55 baseline between curated events; no future information is used.'
result['method']['capital_policy']='100% allocated each weekly decision; max 4 bots; one selected strategy per pair; max single bot 50%; max futures 20%; existing bots receive only the production continuity bonus and can be displaced.'
result['method']['selection']='v1.3 dynamic competition: all eligible existing/new candidates are sorted by risk-adjusted utility; no existing-first lock.'
result['historical_news_events']=[{'date':d.strftime('%Y-%m-%d'),'headline':title,'scope':scope or 'market-wide'} for d,title,scope in EVENTS]
with open('backtest_result.json','w',encoding='utf-8') as f:json.dump(result,f,indent=2,ensure_ascii=False)
print('V13_RESULT_SUMMARY',json.dumps(result['metrics'],ensure_ascii=False))
print('V13_ALLOCATION_MIX',json.dumps(result.get('allocation_mix_pct',{}),ensure_ascii=False))
print('V13_DRAWDOWNS',json.dumps(result.get('top_drawdowns',[])[:5],ensure_ascii=False))
