from __future__ import annotations

import json, math, time
from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean, pstdev

import numpy as np
import pandas as pd
import requests

START = pd.Timestamp('2021-10-05T00:00:00Z')
END = pd.Timestamp('2026-10-05T00:00:00Z')
WARMUP = pd.Timestamp('2021-02-01T00:00:00Z')
PAIRS = ['BTC/USDT','ETH/USDT','SOL/USDT','XRP/USDT','DOGE/USDT','BNB/USDT','SUI/USDT','LINK/USDT','ADA/USDT','LTC/USDT']
NEW_CANDIDATES = ['SPOT_GRID','SPOT_DCA','RECURRING_BUY','FUTURES_GRID','SMART_ARBITRAGE']
FUTURES_TYPES = {'FUTURES_GRID','FUTURES_DCA','SIGNAL_BOT'}
TF_WEIGHTS = {'15m':0.10,'1H':0.20,'4H':0.35,'1D':0.35}
SCORE_WEIGHTS = {'market':0.16,'technical':0.16,'trend':0.10,'volatility':0.10,'compatibility':0.20,'performance':0.08,'capital_efficiency':0.08,'news_sentiment':0.04,'confidence':0.08}
MAX_SINGLE = 0.50
MAX_FUTURES = 0.20
MAX_BOTS = 4
CONTINUITY_BONUS = 5.0

BASE='https://www.okx.com'
S=requests.Session(); S.headers.update({'User-Agent':'OKX-Bot-Analyzer-Backtest/1.0'})
_last_req=0.0

def get_json(path, params, min_gap=0.11, tries=8):
    global _last_req
    for n in range(tries):
        wait=min_gap-(time.time()-_last_req)
        if wait>0: time.sleep(wait)
        try:
            r=S.get(BASE+path,params=params,timeout=25)
            _last_req=time.time()
            if r.status_code==429:
                time.sleep(min(8,0.8*(n+1))); continue
            r.raise_for_status(); p=r.json()
            if p.get('code')=='0': return p
        except Exception:
            if n==tries-1: raise
            time.sleep(min(8,0.7*(n+1)))
    raise RuntimeError('request failed')

def fetch_history(pair, bar='1H', start=WARMUP, end=END):
    inst=pair.replace('/','-'); cursor=None; rows={}; pages=0
    while True:
        params={'instId':inst,'bar':bar,'limit':'300'}
        if cursor is not None: params['after']=str(cursor)
        p=get_json('/api/v5/market/history-candles',params)
        data=p.get('data') or []
        if not data: break
        pages+=1; oldest=10**30
        for x in data:
            ts=int(x[0]); oldest=min(oldest,ts)
            if ts <= int(end.timestamp()*1000) and ts >= int(start.timestamp()*1000):
                rows[ts]={'timestamp':ts,'open':float(x[1]),'high':float(x[2]),'low':float(x[3]),'close':float(x[4]),'volume':float(x[5]),'confirmed':len(x)<9 or x[8]=='1'}
        if oldest <= int(start.timestamp()*1000): break
        if cursor==oldest: break
        cursor=oldest
        if pages>600: break
    vals=[v for _,v in sorted(rows.items()) if v['confirmed']]
    print(f'DATA {pair} {bar}: {len(vals)} bars, {pages} pages')
    return vals

def fetch_15m_before(pair, when):
    inst=pair.replace('/','-')
    p=get_json('/api/v5/market/history-candles',{'instId':inst,'bar':'15m','after':str(int(when.timestamp()*1000)),'limit':'260'})
    vals=[]
    for x in reversed(p.get('data') or []):
        if len(x)>=9 and x[8] != '1': continue
        vals.append({'timestamp':int(x[0]),'open':float(x[1]),'high':float(x[2]),'low':float(x[3]),'close':float(x[4]),'volume':float(x[5]),'confirmed':True})
    return vals

def fetch_funding(pair):
    inst=pair.replace('/','-')+'-SWAP'; cursor=None; out={}; pages=0
    start_ms=int(START.timestamp()*1000)-7*86400000
    while True:
        params={'instId':inst,'limit':'400'}
        if cursor is not None: params['after']=str(cursor)
        try: p=get_json('/api/v5/public/funding-rate-history',params,min_gap=0.21)
        except Exception: break
        data=p.get('data') or []
        if not data: break
        pages+=1; oldest=10**30
        for x in data:
            ts=int(x['fundingTime']); oldest=min(oldest,ts)
            if ts >= start_ms and ts <= int(END.timestamp()*1000)+8*3600000:
                rate=float(x.get('realizedRate') or x.get('fundingRate') or 0)
                out[ts]=rate
        if oldest <= start_ms: break
        if cursor==oldest: break
        cursor=oldest
        if pages>40: break
    print(f'FUNDING {pair}: {len(out)} events, {pages} pages')
    return sorted(out.items())

def to_df(rows):
    if not rows: return pd.DataFrame(columns=['open','high','low','close','volume'])
    df=pd.DataFrame(rows)
    df['dt']=pd.to_datetime(df['timestamp'],unit='ms',utc=True)
    return df.set_index('dt')[['open','high','low','close','volume']].sort_index()

def resample(df, rule):
    if df.empty: return df.copy()
    z=df.resample(rule,label='left',closed='left').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
    return z

def _ema(vals, period):
    if len(vals)<period: return None
    a=2/(period+1); e=float(np.mean(vals[:period]))
    for v in vals[period:]: e=a*v+(1-a)*e
    return e

def _ema_series(vals, period):
    if len(vals)<period: return []
    a=2/(period+1); e=float(np.mean(vals[:period])); out=[e]
    for v in vals[period:]: e=a*v+(1-a)*e; out.append(e)
    return out

def _rsi(vals, period=14):
    if len(vals)<=period:return None
    dif=np.diff(vals); gains=np.maximum(dif,0); losses=np.maximum(-dif,0)
    ag=float(np.mean(gains[:period])); al=float(np.mean(losses[:period]))
    for g,l in zip(gains[period:],losses[period:]): ag=(ag*(period-1)+g)/period; al=(al*(period-1)+l)/period
    if al==0:return 100.0
    rs=ag/al; return 100-100/(1+rs)

def _atr(rows, period=14):
    if len(rows)<=period:return None
    tr=[]
    for i in range(1,len(rows)):
        h,l,pc=rows[i]['high'],rows[i]['low'],rows[i-1]['close']; tr.append(max(h-l,abs(h-pc),abs(l-pc)))
    a=float(np.mean(tr[:period]))
    for x in tr[period:]: a=(a*(period-1)+x)/period
    return a

def _adx(rows,period=14):
    if len(rows)<period*2+1:return None
    tr=[]; pdm=[]; mdm=[]
    for i in range(1,len(rows)):
        cur,prev=rows[i],rows[i-1]; up=cur['high']-prev['high']; down=prev['low']-cur['low']
        pdm.append(up if up>down and up>0 else 0); mdm.append(down if down>up and down>0 else 0)
        tr.append(max(cur['high']-cur['low'],abs(cur['high']-prev['close']),abs(cur['low']-prev['close'])))
    ats=sum(tr[:period]); ps=sum(pdm[:period]); ms=sum(mdm[:period]); dx=[]
    for i in range(period,len(tr)):
        ats=ats-ats/period+tr[i]; ps=ps-ps/period+pdm[i]; ms=ms-ms/period+mdm[i]
        if ats==0: continue
        pdi=100*ps/ats; mdi=100*ms/ats; den=pdi+mdi; dx.append(0 if den==0 else 100*abs(pdi-mdi)/den)
    if not dx:return None
    if len(dx)<period:return float(np.mean(dx))
    v=float(np.mean(dx[:period]))
    for x in dx[period:]:v=(v*(period-1)+x)/period
    return v

def analyze(rows):
    if len(rows)<35:return None
    rows=rows[-260:]; vals=np.array([x['close'] for x in rows],dtype=float); vols=np.array([x['volume'] for x in rows],dtype=float); price=float(vals[-1])
    e20,e50,e200=_ema(vals,20),_ema(vals,50),_ema(vals,200)
    fast=_ema_series(vals,12); slow=_ema_series(vals,26); macd_line=None; macd_signal=None
    if fast and slow:
        off=len(fast)-len(slow); ls=[fast[i+off]-slow[i] for i in range(len(slow))]; macd_line=ls[-1]; macd_signal=_ema(ls,9)
    a=_atr(rows); r=_rsi(vals); ad=_adx(rows)
    if len(vals)>=20:
        w=vals[-20:]; mid=float(np.mean(w)); sd=float(np.std(w)); bbw=0 if mid==0 else 4*sd/mid*100
    else: bbw=None
    logret=np.diff(np.log(vals[vals>0])) if len(vals)>=20 else []
    hv=float(np.std(logret[-60:])*math.sqrt(365)*100) if len(logret)>=2 else None
    mom=0 if len(vals)<15 else (price/vals[-15]-1)*100
    avgv=float(np.mean(vols[-20:])) if len(vols)>=20 else float(np.mean(vols)); prev=float(np.mean(vols[-40:-20])) if len(vols)>=40 else avgv
    vc=0 if prev==0 else (avgv/prev-1)*100
    ta=0
    if e20 is not None and e50 is not None and e200 is not None:
        if price>e20>e50>e200:ta=2
        elif price<e20<e50<e200:ta=-2
        elif price>e50:ta=1
        elif price<e50:ta=-1
    wr=rows[-20:]; highs=[x['high'] for x in wr]; lows=[x['low'] for x in wr]; support=min(lows); resistance=max(highs); midx=len(wr)//2
    if max(highs[midx:])>max(highs[:midx]) and min(lows[midx:])>min(lows[:midx]): lab='HH/HL'
    elif max(highs[midx:])<max(highs[:midx]) and min(lows[midx:])<min(lows[:midx]): lab='LH/LL'
    else: lab='MIXED'
    span=resistance-support; pos=.5 if span==0 else (price-support)/span
    return {'price':price,'ema20':e20,'ema50':e50,'ema200':e200,'rsi':r,'macd':{'line':macd_line,'signal':macd_signal,'histogram':None if macd_signal is None else macd_line-macd_signal},'adx':ad,'atr':a,'atr_pct':None if a is None or price==0 else a/price*100,'bollinger':{'width_pct':bbw},'historical_volatility':hv,'momentum_14':mom,'volume':float(vols[-1]),'volume_change_pct':vc,'trend_alignment':ta,'structure':{'label':lab,'support':support,'resistance':resistance,'range_position':max(0,min(1,pos))}}

def regime(m):
    ad=m.get('adx') or 0; ap=m.get('atr_pct') or 0; r=m.get('rsi') or 50; mom=m.get('momentum_14') or 0; tr=m.get('trend_alignment') or 0; pos=m['structure'].get('range_position'); bbw=m['bollinger'].get('width_pct') or 0; vc=m.get('volume_change_pct') or 0; st=m['structure'].get('label')
    if pos is not None and pos>.94 and mom>2 and vc>15 and ad>22:return 'Breakout',min(95,65+ad*.6)
    if pos is not None and pos<.06 and mom<-2 and vc>15 and ad>22:return 'Breakdown',min(95,65+ad*.6)
    if ad>=35 and tr>=2 and r>=55:return 'Strong Bullish',min(95,70+ad*.5)
    if ad>=25 and tr>0 and mom>0:return 'Bullish',min(92,65+ad*.5)
    if tr>0 and mom>=-1:return 'Weak Bullish',66
    if ad>=35 and tr<=-2 and r<=45:return 'Strong Bearish',min(95,70+ad*.5)
    if ad>=25 and tr<0 and mom<0:return 'Bearish',min(92,65+ad*.5)
    if tr<0 and mom<=1:return 'Weak Bearish',66
    if ad<20:
        if ap>=2.2 or bbw>=8:return 'Sideways + High Volatility',74
        if ap<=1.0 or bbw<=4:return 'Sideways + Low Volatility',74
        return 'Sideways',72
    if vc>30 and ap>2:return 'Volatility Expansion',70
    if vc<-20 and bbw<4:return 'Volatility Compression',68
    if st=='MIXED':return 'Transition / Uncertain',58
    return 'Transition / Uncertain',55

def market_scores(m, conf):
    r=m.get('rsi') or 50; ad=m.get('adx') or 0; mom=m.get('momentum_14') or 0; tr=m.get('trend_alignment') or 0; ap=m.get('atr_pct') or 0
    technical=50+min(18,max(-18,mom*2))+(8 if 42<=r<=68 else -6 if r>78 or r<22 else 0)
    trend=50+tr*16+min(12,ad/3)*(1 if tr>=0 else -.35)
    vol=78 if .8<=ap<=3.5 else 58 if ap<5 else 38
    market=technical*.35+trend*.35+vol*.30
    cl=lambda x:max(0,min(100,float(x)))
    return {'market':cl(market),'technical':cl(technical),'trend':cl(trend),'volatility':cl(vol),'confidence':cl(conf)}

def compat(bot,reg,m,funding=None):
    ad=m.get('adx') or 0; ap=m.get('atr_pct') or 0; tr=m.get('trend_alignment') or 0
    if bot=='SPOT_GRID':
        tab={'Sideways':90,'Sideways + High Volatility':94,'Sideways + Low Volatility':80,'Weak Bullish':78,'Weak Bearish':62,'Bullish':60,'Bearish':42,'Strong Bearish':22,'Strong Bullish':48,'Breakout':42,'Breakdown':18}; return tab.get(reg,55)
    if bot=='SPOT_DCA':
        tab={'Bullish':88,'Weak Bullish':86,'Sideways + High Volatility':84,'Sideways':78,'Sideways + Low Volatility':70,'Weak Bearish':58,'Bearish':38,'Strong Bearish':15,'Breakdown':12,'Breakout':72,'Strong Bullish':70}; return tab.get(reg,58)
    if bot=='RECURRING_BUY':
        v=72
        if reg in {'Strong Bearish','Breakdown'}:v-=18
        if reg in {'Bullish','Weak Bullish','Sideways'}:v+=8
        return v
    if bot=='FUTURES_GRID':
        if reg=='Sideways + High Volatility':return 90
        if reg in {'Sideways','Sideways + Low Volatility'}:return 78
        if reg in {'Bullish','Weak Bullish','Bearish','Weak Bearish'}:return 84
        if reg in {'Breakout','Breakdown','Strong Bullish','Strong Bearish'}:return 38
        return 55
    if bot=='SMART_ARBITRAGE':
        if funding is None:return 45
        return 82 if funding>.00005 else 65 if funding>0 else 25
    return 50

def risk(bot,reg,m,capital,equity,futures_exposure=0,lev=1):
    s=28.; eligible=True; ap=m.get('atr_pct') or 0; hv=m.get('historical_volatility') or 0
    if ap>3:s+=12
    if hv>100:s+=10
    if reg in {'Breakdown','Strong Bearish','Breakout','Strong Bullish'}:s+=8
    if equity>0 and capital/equity>MAX_SINGLE:s+=12
    if bot in FUTURES_TYPES:
        s+=18
        if lev>3:s+=22; eligible=False
        if equity>0 and (futures_exposure+capital)/equity>MAX_FUTURES:s+=18; eligible=False
    if bot=='FUTURES_DCA':s+=18; eligible=False
    if s>=65 and bot in FUTURES_TYPES:eligible=False
    return min(100,s),eligible

def overall(base,co,perf,rsk,cap_eff,news,conf):
    vals={'market':base['market'],'technical':base['technical'],'trend':base['trend'],'volatility':base['volatility'],'compatibility':co,'performance':perf,'capital_efficiency':cap_eff,'news_sentiment':news,'confidence':conf}
    w=sum(vals[k]*SCORE_WEIGHTS[k] for k in SCORE_WEIGHTS)-max(0,rsk-45)*.22
    return round(max(0,min(100,w)),1)

def evaluate(bot,state,equity,capital,futures_exposure,performance=50,lev=1):
    co=compat(bot,state['regime'],state['metrics'],state.get('funding_rate'))
    rs,el=risk(bot,state['regime'],state['metrics'],capital,equity,futures_exposure,lev)
    # Current production news score is neutral 50; historical headline availability is assumed, so news confidence=55 => ceiling 80.
    conf=min(state['scores']['confidence'],94,80)
    ce=72 if capital<=max(equity*.20,1) else 52
    sc=overall(state['scores'],co,performance,rs,ce,50,conf)
    return {'score':sc,'compatibility':co,'risk_score':rs,'eligible':el,'confidence':round(conf,1)}

def utility(c):
    b=c['score']*.45+c['confidence']*.20+(100-c['risk_score'])*.25+c['compatibility']*.10
    if c.get('existing'):b+=CONTINUITY_BONUS
    b*=c.get('diversification_factor',1.0)
    return max(.1,b)

def normalize_caps(weights,caps):
    out={k:max(0,v) for k,v in weights.items()}
    for _ in range(20):
        total=sum(out.values())
        if total<=0:break
        out={k:v/total for k,v in out.items()}; excess=0; free=[]
        for k,v in list(out.items()):
            cap=caps.get(k,1)
            if v>cap+1e-12:excess+=v-cap; out[k]=cap
            else:free.append(k)
        if excess<=1e-12 or not free:break
        ft=sum(out[k] for k in free)
        if ft<=0:
            for k in free:out[k]+=excess/len(free)
        else:
            for k in free:out[k]+=excess*out[k]/ft
    t=sum(out.values())
    return {k:v/t for k,v in out.items()} if t>0 else out

def allocate(cands,total):
    eligible=[dict(c) for c in cands if c.get('eligible',True)]
    if not eligible:return []
    for c in eligible:c['utility']=utility(c); c['futures']=c['bot_type'] in FUTURES_TYPES
    eligible.sort(key=lambda x:x['utility'],reverse=True)
    existing=[c for c in eligible if c.get('existing') and c['score']>=40 and c['risk_score']<80]
    selected=existing[:MAX_BOTS]; keys={c['key'] for c in selected}
    for c in eligible:
        if len(selected)>=MAX_BOTS:break
        if c['key'] in keys:continue
        if any(x['pair']==c['pair'] and not c.get('existing') for x in selected):continue
        selected.append(c);keys.add(c['key'])
    if not selected:selected=[eligible[0]]
    if len(selected)==1:w={selected[0]['key']:1.0}
    else:
        raw={c['key']:c['utility'] for c in selected}; cap=max(MAX_SINGLE,1/len(selected)); w=normalize_caps(raw,{c['key']:cap for c in selected})
        fk=[c['key'] for c in selected if c['futures']]; sk=[c['key'] for c in selected if not c['futures']]; ft=sum(w.get(k,0) for k in fk)
        if ft>MAX_FUTURES and sk:
            scale=MAX_FUTURES/ft; rel=0
            for k in fk:old=w[k];w[k]=old*scale;rel+=old-w[k]
            st=sum(w[k] for k in sk)
            for k in sk:w[k]+=rel*(w[k]/st if st>0 else 1/len(sk))
    out=[];running=0
    for i,c in enumerate(selected):
        amt=round(total-running,2) if i==len(selected)-1 else round(total*w[c['key']],2)
        if i<len(selected)-1:running+=amt
        out.append({**c,'amount':amt,'pct':amt/total*100 if total else 0})
    return out

def funding_latest(events, ts):
    if not events:return None
    times=np.array([x[0] for x in events],dtype=np.int64); i=np.searchsorted(times,int(ts.timestamp()*1000),side='right')-1
    return events[i][1] if i>=0 else None

def funding_sum(events,t0,t1):
    a=int(t0.timestamp()*1000);b=int(t1.timestamp()*1000)
    return sum(r for t,r in events if a<t<=b)

def state_at(pair,when,dfs,funding,cache15):
    one=dfs[pair]['1H']; four=dfs[pair]['4H']; day=dfs[pair]['1D']
    def rows_before(df,n=260):
        z=df[df.index<when].tail(n); return [{'open':float(r.open),'high':float(r.high),'low':float(r.low),'close':float(r.close),'volume':float(r.volume)} for r in z.itertuples()]
    r1=rows_before(one);r4=rows_before(four);rd=rows_before(day)
    if len(rd)<200 or len(r4)<200 or len(r1)<200:return None
    key=(pair,when.isoformat())
    if key not in cache15:
        try:cache15[key]=fetch_15m_before(pair,when)
        except Exception:cache15[key]=[]
    r15=cache15[key]
    if len(r15)<200:return None
    m15,m1,m4,md=analyze(r15),analyze(r1),analyze(r4),analyze(rd)
    if not all([m15,m1,m4,md]):return None
    g15,c15=regime(m15);g1,c1=regime(m1);g4,c4=regime(m4);gd,cd=regime(md)
    regs={'15m':g15,'1H':g1,'4H':g4,'1D':gd}; agreement=sum(TF_WEIGHTS[k] for k,v in regs.items() if v==g4)
    conf=min(96,c4*.55+cd*.30+agreement*15); scores=market_scores(m4,conf)
    return {'pair':pair,'metrics':m4,'regime':g4,'regime_confidence':conf,'scores':scores,'funding_rate':funding_latest(funding.get(pair,[]),when),'daily_closes':[x['close'] for x in rd[-61:]],'timeframe_regimes':regs}

def div_factors(states):
    rets={}
    for p,s in states.items():
        c=s['daily_closes']; rets[p]=np.diff(np.log(np.array(c,dtype=float))) if len(c)>1 else np.array([])
    out={}
    for p,r in rets.items():
        vals=[]
        for q,o in rets.items():
            if q==p:continue
            n=min(len(r),len(o))
            if n>=10 and np.std(r[-n:])>0 and np.std(o[-n:])>0:vals.append(abs(float(np.corrcoef(r[-n:],o[-n:])[0,1])))
        av=float(np.mean(vals)) if vals else 0
        out[p]=round(max(.75,1-max(0,av-.50)*.50),4)
    return out

def range_levels(state,price,n=12):
    s=state['metrics']['structure']; lo=float(s['support']); hi=float(s['resistance']); ap=float(state['metrics'].get('atr_pct') or 1.5)/100
    minhalf=max(.02,ap*1.5)
    if not (lo<price<hi) or (hi-lo)/price<.04:
        lo=min(lo,price*(1-minhalf));hi=max(hi,price*(1+minhalf))
    lo=max(price*.5,lo); hi=min(price*1.5,hi)
    if hi<=lo:lo=price*.96;hi=price*1.04
    return np.linspace(lo,hi,n+1)

def path_points(bar):
    o,h,l,c=bar.open,bar.high,bar.low,bar.close
    return [o,l,h,c] if c>=o else [o,h,l,c]

def crossed(a,b,levels):
    if b>a:return sorted([x for x in levels if a<x<=b])
    if b<a:return sorted([x for x in levels if b<=x<a],reverse=True)
    return []

def ret_spot_grid(df,state):
    if df.empty:return 0.0
    cap=1.0; p0=float(df.iloc[0].open); levels=range_levels(state,p0); cash=.5; qty=(.5*(1-.001))/p0; unit=1/(12*p0); fee=.0008
    for bar in df.itertuples():
        pts=path_points(bar)
        for a,b in zip(pts[:-1],pts[1:]):
            for px in crossed(a,b,levels):
                if b>a:
                    q=min(unit,qty)
                    if q>0:cash+=q*px*(1-fee);qty-=q
                else:
                    q=min(unit,cash/(px*(1+fee)))
                    if q>0:cash-=q*px*(1+fee);qty+=q
    return cash+qty*float(df.iloc[-1].close)-1

def ret_spot_dca(df):
    if df.empty:return 0.0
    cash=1.0;qty=0.;cost=0.;base=None;levels=[];filled=set(); pending=True; fee=.001
    for bar in df.itertuples():
        if pending:
            px=float(bar.open); spend=min(.25,cash); q=spend*(1-fee)/px;cash-=spend;qty+=q;cost+=spend;base=px;levels=[px*.97,px*.94,px*.90];filled=set();pending=False
        for j,lv in enumerate(levels):
            if j not in filled and bar.low<=lv and cash>1e-9:
                spend=min(.25,cash);q=spend*(1-fee)/lv;cash-=spend;qty+=q;cost+=spend;filled.add(j)
        if qty>0:
            avg=cost/qty;tp=avg*1.025
            if bar.high>=tp:
                cash+=qty*tp*(1-fee);qty=0.;cost=0.;pending=True
    return cash+qty*float(df.iloc[-1].close)-1

def ret_recurring(df):
    if df.empty:return 0.0
    cash=1.;qty=0.;fee=.001; days=sorted(set(df.index.floor('D')))[:7]; per=1/7
    for d in days:
        z=df[df.index>=d]
        if z.empty:continue
        px=float(z.iloc[0].open); spend=min(per,cash);cash-=spend;qty+=spend*(1-fee)/px
    return cash+qty*float(df.iloc[-1].close)-1

def ret_futures_grid(df,state,fundsum):
    if df.empty:return 0.0
    p0=float(df.iloc[0].open);levels=range_levels(state,p0);reg=state['regime'];sgn=1 if 'Bullish' in reg or reg=='Breakout' else -1 if 'Bearish' in reg or reg=='Breakdown' else 0
    equity=1.;pos=sgn*(1/p0);unit=2/(12*p0);last=p0;fee=.0002;maxq=2/p0
    equity-=abs(pos)*p0*.0005
    for bar in df.itertuples():
        pts=path_points(bar)
        for a,b in zip(pts[:-1],pts[1:]):
            cur=a
            for px in crossed(a,b,levels):
                equity+=pos*(px-cur);cur=px
                dq=-unit if b>a else unit
                new=max(-maxq,min(maxq,pos+dq));actual=new-pos;equity-=abs(actual)*px*fee;pos=new
                if equity<=.20:return -.80
            equity+=pos*(b-cur);last=b
            if equity<=.20:return -.80
    equity-=sgn*abs(pos*p0)*fundsum
    return max(-.80,equity-1)

def ret_smart_arb(fundsum):
    return .5*fundsum-.0002

def strategy_return(bot,pair,state,t0,t1,dfs,funding):
    df=dfs[pair]['1H']; w=df[(df.index>=t0)&(df.index<t1)]
    if w.empty:return 0.0
    fs=funding_sum(funding.get(pair,[]),t0,t1)
    if bot=='SPOT_GRID':return ret_spot_grid(w,state)
    if bot=='SPOT_DCA':return ret_spot_dca(w)
    if bot=='RECURRING_BUY':return ret_recurring(w)
    if bot=='FUTURES_GRID':return ret_futures_grid(w,state,fs)
    if bot=='SMART_ARBITRAGE':return ret_smart_arb(fs)
    return 0.0

def build_states(when,dfs,funding,cache15):
    states={}
    for p in PAIRS:
        try:st=state_at(p,when,dfs,funding,cache15)
        except Exception as e:
            print('STATE_ERR',p,when,e);st=None
        if st:states[p]=st
    return states

def candidates(states,prev_values,total):
    div=div_factors(states);fex=sum(v for (p,b),v in prev_values.items() if b in FUTURES_TYPES);out=[]
    for (p,b),cap in prev_values.items():
        if cap<=0 or p not in states:continue
        ev=evaluate(b,states[p],total,cap,fex,50,2 if b=='FUTURES_GRID' else 1)
        out.append({'key':f'existing:{p}:{b}','pair':p,'bot_type':b,'existing':True,'current_capital':cap,'diversification_factor':div.get(p,1),**ev})
    sizing=max(25,total*.20)
    for p,st in states.items():
        for b in NEW_CANDIDATES:
            ev=evaluate(b,st,total,sizing,fex,50,2 if b=='FUTURES_GRID' else 1)
            if not ev['eligible'] or ev['confidence']<30:continue
            out.append({'key':f'new:{p}:{b}','pair':p,'bot_type':b,'existing':False,'current_capital':0,'diversification_factor':div.get(p,1),**ev})
    return out

def drawdown_episodes(points):
    peakv=points[0]['equity'];peakd=points[0]['date'];under=None;episodes=[]
    for x in points[1:]:
        v=x['equity'];d=x['date']
        if v>=peakv:
            if under:under['recovery']=d;episodes.append(under);under=None
            peakv=v;peakd=d
        else:
            dd=v/peakv-1
            if under is None:under={'peak':peakd,'peak_equity':peakv,'trough':d,'trough_equity':v,'drawdown_pct':dd*100,'recovery':None}
            elif dd<under['drawdown_pct']/100:under.update({'trough':d,'trough_equity':v,'drawdown_pct':dd*100})
    if under:episodes.append(under)
    return sorted(episodes,key=lambda x:x['drawdown_pct'])

def main():
    dfs={};funding={}
    for p in PAIRS:
        rows=fetch_history(p,'1H');d1=to_df(rows);dfs[p]={'1H':d1,'4H':resample(d1,'4h'),'1D':resample(d1,'1D')}
    for p in PAIRS:funding[p]=fetch_funding(p)
    dates=list(pd.date_range(START,END,freq='7D'))
    if dates[-1]<END:dates.append(END)
    cache15={}; equity=100.;prev_values={};curve=[{'date':START.strftime('%Y-%m-%d'),'equity':100.0}]; decisions=[]
    for i,t0 in enumerate(dates[:-1]):
        t1=dates[i+1]
        total=sum(prev_values.values()) if prev_values else equity
        states=build_states(t0,dfs,funding,cache15)
        cs=candidates(states,prev_values,total); alloc=allocate(cs,total)
        if not alloc:
            newvals={}; endeq=total
        else:
            newvals={}; rows=[]
            for a in alloc:
                p,b,amt=a['pair'],a['bot_type'],a['amount'];r=strategy_return(b,p,states[p],t0,t1,dfs,funding);endv=max(0,amt*(1+r));newvals[(p,b)]=newvals.get((p,b),0)+endv
                rows.append({'pair':p,'bot':b,'pct':round(a['pct'],2),'capital':round(amt,2),'score':a['score'],'risk':a['risk_score'],'confidence':a['confidence'],'regime':states[p]['regime'],'period_return_pct':round(r*100,3)})
            endeq=sum(newvals.values()); decisions.append({'date':t0.strftime('%Y-%m-%d'),'equity_start':round(total,4),'equity_end':round(endeq,4),'allocations':rows})
        equity=endeq;prev_values=newvals;curve.append({'date':t1.strftime('%Y-%m-%d'),'equity':round(equity,6)})
        if i%13==0:print('PROGRESS',i,'/',len(dates)-1,t0.date(),'equity',round(equity,2),'states',len(states))
    ser=pd.Series([x['equity'] for x in curve],index=pd.to_datetime([x['date'] for x in curve],utc=True))
    monthly=ser.resample('ME').last(); monthly_points=[{'date':d.strftime('%Y-%m'),'equity':round(float(v),4)} for d,v in monthly.items()]
    weekly_ret=ser.pct_change().dropna(); monthly_ret=monthly.pct_change().dropna()
    annual=ser.resample('YE').last().pct_change().dropna(); years=(END-START).total_seconds()/(365.2425*86400);cagr=(equity/100)**(1/years)-1
    episodes=drawdown_episodes(curve)
    # Allocation mix and contiguous sessions
    mix=defaultdict(float); sessions=[];active={}
    for d in decisions:
        present={}
        for a in d['allocations']:
            k=(a['pair'],a['bot']);present[k]=a['pct'];mix[a['bot']]+=a['pct']/100
        for k in list(active):
            if k not in present:
                s=active.pop(k);s['end']=d['date'];s['weeks']=s['count'];s['avg_pct']=round(s['sum_pct']/s['count'],2);sessions.append(s)
        for k,pct in present.items():
            if k not in active:active[k]={'pair':k[0],'bot':k[1],'start':d['date'],'sum_pct':0.,'count':0}
            active[k]['sum_pct']+=pct;active[k]['count']+=1
    enddate=curve[-1]['date']
    for s in active.values():s['end']=enddate;s['weeks']=s['count'];s['avg_pct']=round(s['sum_pct']/s['count'],2);sessions.append(s)
    ndec=max(1,len(decisions));mix_out={k:round(v/ndec*100,2) for k,v in mix.items()}
    sessions=sorted(sessions,key=lambda x:x['weeks'],reverse=True)[:15]
    # BTC benchmark
    btc=dfs['BTC/USDT']['1H'];pstart=float(btc[btc.index>=START].iloc[0].open);pend=float(btc[btc.index<=END].iloc[-1].close);btc_final=100*(1-.001)/pstart*pend*(1-.001)
    result={'period':{'start':str(START.date()),'end':str(END.date()),'years':years,'decision_frequency':'7D'},'method':{'timeframes':'15m exact weekly snapshot; 1H full; 4H and 1D resampled from OKX 1H','news':'Production news score is neutral 50. Historical headline availability assumed for confidence ceiling only.','fees':'0.10% spot taker, 0.08% grid maker; futures 0.05% entry/0.02% grid; strategy-specific conservative execution proxies.','capital_policy':'100% allocated each decision; max 4 bots; max single bot 50%; max futures 20%; continuity bonus replicated.'},'metrics':{'initial_capital':100.0,'final_capital':round(equity,4),'total_return_pct':round((equity/100-1)*100,3),'cagr_pct':round(cagr*100,3),'avg_weekly_pct':round(float(weekly_ret.mean())*100,4),'median_weekly_pct':round(float(weekly_ret.median())*100,4),'avg_monthly_pct':round(float(monthly_ret.mean())*100,4),'avg_annual_pct':round(float(annual.mean())*100,4) if len(annual) else None,'weekly_vol_pct':round(float(weekly_ret.std())*100,4),'positive_weeks_pct':round(float((weekly_ret>0).mean())*100,2),'max_drawdown_pct':round(episodes[0]['drawdown_pct'],3) if episodes else 0,'btc_buy_hold_final':round(btc_final,4),'btc_buy_hold_return_pct':round((btc_final/100-1)*100,3),'decision_count':len(decisions)},'top_drawdowns':episodes[:8],'allocation_mix_pct':mix_out,'longest_sessions':sessions,'monthly_curve':monthly_points,'annual_returns_pct':{d.strftime('%Y'):round(float(v)*100,3) for d,v in annual.items()},'sample_decisions_first':decisions[:3],'sample_decisions_last':decisions[-3:]}
    print('RESULT_JSON_BEGIN')
    print(json.dumps(result,separators=(',',':')))
    print('RESULT_JSON_END')
    with open('backtest_result.json','w') as f:json.dump(result,f,indent=2)
    pd.DataFrame(monthly_points).to_csv('backtest_monthly.csv',index=False)

if __name__=='__main__':main()
