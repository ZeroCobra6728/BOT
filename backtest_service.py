from __future__ import annotations

import base64
import bisect
import csv
import io
import json
import math
import os
import runpy
import statistics
import threading
import time
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse

ROOT = Path(__file__).resolve().parent
RESULT: dict[str, Any] = {"status": "initializing", "progress": "Preparando runtime v1.4"}
LOCK = threading.Lock()


def log(msg: str) -> None:
    print(f"[BACKTEST] {msg}", flush=True)
    with LOCK:
        RESULT["progress"] = msg


def prepare_runtime() -> None:
    marker = ROOT / ".runtime_extracted_backtest_v14"
    if not (ROOT / "app" / "main.py").exists():
        encoded = "".join(p.read_text(encoding="utf-8") for p in sorted(ROOT.glob("runtime_bundle.part*")))
        raw = base64.b64decode(encoded)
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            zf.extractall(ROOT)
    if not marker.exists():
        runpy.run_path(str(ROOT / "runtime_patch.py"), run_name="__runtime_patch_backtest__")
        runpy.run_path(str(ROOT / "runtime_js_fix.py"), run_name="__runtime_js_fix_backtest__")
        marker.write_text("v1.4", encoding="utf-8")


prepare_runtime()

from app.domain import BotType, MarketRegime  # noqa: E402
from app.services.quant import analyze_candles  # noqa: E402
from app.services.regime import classify_regime  # noqa: E402
from app.services.scoring import market_scores  # noqa: E402
from app.services.recommendation import evaluate  # noqa: E402
from app.services.allocation import allocate_100_percent  # noqa: E402

try:
    from app.config import TIMEFRAME_WEIGHTS  # type: ignore  # noqa: E402
except Exception:
    TIMEFRAME_WEIGHTS = {"15m": 0.10, "1H": 0.20, "4H": 0.35, "1D": 0.35}

PAIRS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT",
    "BNB/USDT", "SUI/USDT", "LINK/USDT", "ADA/USDT", "LTC/USDT",
]
SYMBOL = {p: p.replace("/", "") for p in PAIRS}
START = datetime(2021, 10, 11, tzinfo=timezone.utc)
TARGET_END = datetime(2026, 10, 6, tzinfo=timezone.utc)
FETCH_START = datetime(2021, 1, 1, tzinfo=timezone.utc)
SPOT_BASE = "https://data.binance.vision/data/spot"
FUT_BASE = "https://data.binance.vision/data/futures/um"

# Conservative retail fee/slippage proxies, not claims about a specific user's OKX tier.
SPOT_FEE = 0.0010
GRID_FEE = 0.0008
SLIPPAGE = 0.0002
ARBITRAGE_ROUND_TRIP = 0.0026


def month_tokens(start: datetime, end: datetime) -> list[str]:
    y, m = start.year, start.month
    out = []
    while (y, m) < (end.year, end.month):
        out.append(f"{y:04d}-{m:02d}")
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
    return out


def current_month_days(end: datetime) -> list[str]:
    d = datetime(end.year, end.month, 1, tzinfo=timezone.utc)
    out = []
    while d.date() < end.date():
        out.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    return out


def fetch_zip(client: httpx.Client, url: str) -> bytes | None:
    for attempt in range(3):
        try:
            r = client.get(url, timeout=45, follow_redirects=True)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.content
        except Exception:
            if attempt == 2:
                return None
            time.sleep(0.35 * (attempt + 1))
    return None


def parse_kline_zip(raw: bytes | None) -> list[tuple[int, float, float, float, float, float]]:
    if not raw:
        return []
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            name = zf.namelist()[0]
            text = zf.read(name).decode("utf-8", errors="replace")
    except Exception:
        return []
    rows: list[tuple[int, float, float, float, float, float]] = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 6:
            continue
        try:
            ts = int(float(row[0]))
            if ts > 10**14:  # Binance spot switched some archives to microseconds.
                ts //= 1000
            o, h, l, c, v = map(float, row[1:6])
            rows.append((ts, o, h, l, c, v))
        except Exception:
            continue
    return rows


def parse_funding_zip(raw: bytes | None) -> list[tuple[int, float]]:
    if not raw:
        return []
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            text = zf.read(zf.namelist()[0]).decode("utf-8", errors="replace")
    except Exception:
        return []
    out: list[tuple[int, float]] = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 2:
            continue
        try:
            ts = int(float(row[0]))
            if ts > 10**14:
                ts //= 1000
            # Monthly Binance funding archives use calc_time, funding_interval_hours, last_funding_rate.
            rate = float(row[-1])
            out.append((ts, rate))
        except Exception:
            continue
    return out


def download_symbol(pair: str) -> dict[str, Any]:
    symbol = SYMBOL[pair]
    months = month_tokens(FETCH_START, TARGET_END)
    days = current_month_days(TARGET_END)
    spot_urls = [
        f"{SPOT_BASE}/monthly/klines/{symbol}/1h/{symbol}-1h-{ym}.zip" for ym in months
    ] + [
        f"{SPOT_BASE}/daily/klines/{symbol}/1h/{symbol}-1h-{d}.zip" for d in days
    ]
    funding_urls = [
        f"{FUT_BASE}/monthly/fundingRate/{symbol}/{symbol}-fundingRate-{ym}.zip" for ym in months
    ] + [
        f"{FUT_BASE}/daily/fundingRate/{symbol}/{symbol}-fundingRate-{d}.zip" for d in days
    ]
    spot: list[tuple[int, float, float, float, float, float]] = []
    funding: list[tuple[int, float]] = []
    limits = httpx.Limits(max_connections=16, max_keepalive_connections=8)
    with httpx.Client(headers={"User-Agent": "OKX-Bot-Analyzer-Backtest/1.4"}, limits=limits) as client:
        with ThreadPoolExecutor(max_workers=12) as pool:
            futures = {pool.submit(fetch_zip, client, u): ("spot", u) for u in spot_urls}
            futures.update({pool.submit(fetch_zip, client, u): ("fund", u) for u in funding_urls})
            for fut in as_completed(futures):
                kind, _ = futures[fut]
                raw = fut.result()
                if kind == "spot":
                    spot.extend(parse_kline_zip(raw))
                else:
                    funding.extend(parse_funding_zip(raw))
    spot = sorted({r[0]: r for r in spot}.values(), key=lambda x: x[0])
    funding = sorted({r[0]: r for r in funding}.values(), key=lambda x: x[0])
    return {"pair": pair, "hourly": spot, "funding": funding}


def candle_dict(row: tuple[int, float, float, float, float, float]) -> dict[str, Any]:
    ts, o, h, l, c, v = row
    return {"ts": ts, "timestamp": ts, "open": o, "high": h, "low": l, "close": c, "volume": v}


def aggregate(rows: list[tuple[int, float, float, float, float, float]], hours: int) -> list[tuple[int, float, float, float, float, float]]:
    if not rows:
        return []
    size = hours * 3600 * 1000
    out: list[tuple[int, float, float, float, float, float]] = []
    cur_key = None
    o = h = l = c = v = 0.0
    ts0 = 0
    for ts, ro, rh, rl, rc, rv in rows:
        key = ts // size
        if key != cur_key:
            if cur_key is not None:
                out.append((ts0, o, h, l, c, v))
            cur_key = key
            ts0 = key * size
            o, h, l, c, v = ro, rh, rl, rc, rv
        else:
            h = max(h, rh); l = min(l, rl); c = rc; v += rv
    if cur_key is not None:
        out.append((ts0, o, h, l, c, v))
    return out


def build_store(raw: dict[str, Any]) -> dict[str, Any]:
    h1 = raw["hourly"]
    h4 = aggregate(h1, 4)
    d1 = aggregate(h1, 24)
    return {
        "1H": h1, "4H": h4, "1D": d1,
        "ts1H": [x[0] for x in h1], "ts4H": [x[0] for x in h4], "ts1D": [x[0] for x in d1],
        "funding": raw["funding"], "fund_ts": [x[0] for x in raw["funding"]],
    }


def before(store: dict[str, Any], tf: str, t_ms: int, n: int = 280) -> list[dict[str, Any]]:
    arr = store[tf]
    tss = store["ts" + tf]
    i = bisect.bisect_left(tss, t_ms)
    return [candle_dict(x) for x in arr[max(0, i - n):i]]


def between_rows(store: dict[str, Any], start_ms: int, end_ms: int) -> list[tuple[int, float, float, float, float, float]]:
    tss = store["ts1H"]
    a = bisect.bisect_left(tss, start_ms)
    b = bisect.bisect_left(tss, end_ms)
    return store["1H"][a:b]


def last_funding(store: dict[str, Any], t_ms: int) -> float:
    i = bisect.bisect_left(store["fund_ts"], t_ms) - 1
    return float(store["funding"][i][1]) if i >= 0 else 0.0


def future_funding_sum(store: dict[str, Any], a_ms: int, b_ms: int) -> float:
    tss = store["fund_ts"]
    a = bisect.bisect_left(tss, a_ms)
    b = bisect.bisect_left(tss, b_ms)
    return sum(float(x[1]) for x in store["funding"][a:b])


def state_for(pair: str, store: dict[str, Any], t_ms: int) -> dict[str, Any] | None:
    d1 = before(store, "1D", t_ms, 280)
    h4 = before(store, "4H", t_ms, 280)
    h1 = before(store, "1H", t_ms, 280)
    if len(d1) < 205 or len(h4) < 205 or len(h1) < 205:
        return None
    # Historical archive is 1H. 15m timing is proxied with the latest 1H window; 4H/1D are exact resamples.
    tf_candles = {"15m": h1, "1H": h1, "4H": h4, "1D": d1}
    annual = {"15m": 365 * 24, "1H": 365 * 24, "4H": 365 * 6, "1D": 365}
    analyzed: dict[str, Any] = {}
    for tf, candles in tf_candles.items():
        m = analyze_candles(candles, annualization=annual[tf])
        regime, rc = classify_regime(m)
        analyzed[tf] = {"metrics": m, "regime": str(regime), "regime_confidence": float(rc)}
    primary = analyzed["4H"]
    blended = dict(primary["metrics"])
    for key in ("rsi", "adx", "atr_pct", "historical_volatility", "momentum_14", "volume_change_pct", "trend_alignment"):
        vals = [(float(TIMEFRAME_WEIGHTS.get(tf, 0)), analyzed[tf]["metrics"].get(key)) for tf in TIMEFRAME_WEIGHTS]
        vals = [(w, float(v)) for w, v in vals if v is not None and w > 0]
        if vals:
            blended[key] = sum(w * v for w, v in vals) / sum(w for w, _ in vals)
    bvals = [(float(TIMEFRAME_WEIGHTS.get(tf, 0)), (analyzed[tf]["metrics"].get("bollinger") or {}).get("width_pct")) for tf in TIMEFRAME_WEIGHTS]
    bvals = [(w, float(v)) for w, v in bvals if v is not None and w > 0]
    if bvals:
        blended["bollinger"] = dict(primary["metrics"].get("bollinger") or {})
        blended["bollinger"]["width_pct"] = sum(w * v for w, v in bvals) / sum(w for w, _ in bvals)
    tf_scores = {tf: market_scores(analyzed[tf]["metrics"], analyzed[tf]["regime_confidence"]) for tf in TIMEFRAME_WEIGHTS}
    scores = {k: sum(float(TIMEFRAME_WEIGHTS.get(tf, 0)) * float(tf_scores[tf][k]) for tf in TIMEFRAME_WEIGHTS) for k in ("market", "technical", "trend", "volatility")}
    bull = {"Weak Bullish", "Bullish", "Strong Bullish", "Breakout"}
    bear = {"Weak Bearish", "Bearish", "Strong Bearish", "Breakdown"}
    side = {"Sideways", "Sideways High Vol", "Sideways Low Vol"}
    votes = {"bull": 0.0, "bear": 0.0, "side": 0.0}
    for tf, w in TIMEFRAME_WEIGHTS.items():
        r = analyzed[tf]["regime"]
        votes["bull"] += float(w) if r in bull else 0
        votes["bear"] += float(w) if r in bear else 0
        votes["side"] += float(w) if r in side else 0
    if votes["bull"] >= .55:
        combined = primary["regime"] if primary["regime"] in bull else str(MarketRegime.BULLISH)
    elif votes["bear"] >= .55:
        combined = primary["regime"] if primary["regime"] in bear else str(MarketRegime.BEARISH)
    elif votes["side"] >= .55:
        combined = primary["regime"] if primary["regime"] in side else str(MarketRegime.SIDEWAYS)
    else:
        combined = str(MarketRegime.TRANSITION)
    agree = sum(float(TIMEFRAME_WEIGHTS.get(tf, 0)) for tf in TIMEFRAME_WEIGHTS if analyzed[tf]["regime"] == primary["regime"])
    conf = sum(float(TIMEFRAME_WEIGHTS.get(tf, 0)) * analyzed[tf]["regime_confidence"] for tf in TIMEFRAME_WEIGHTS)
    conf = min(96.0, max(30.0, conf * .88 + agree * 12))
    scores["confidence"] = conf
    return {
        "pair": pair,
        "price": float(primary["metrics"]["price"]),
        "regime": combined,
        "regime_confidence": conf,
        "metrics": blended,
        "scores": scores,
        "funding_rate": last_funding(store, t_ms),
        "news": {"status": "BACKTEST_NEUTRAL", "score": 50.0, "confidence": 0.0, "items": []},
        "data_confidence": 90.0,
        "timeframe_consensus": {"bullish_weight": votes["bull"], "bearish_weight": votes["bear"], "sideways_weight": votes["side"], "exact_4h_agreement": agree},
    }


def pct_returns_daily(store: dict[str, Any], t_ms: int, n: int = 90) -> list[float]:
    rows = store["1D"]
    tss = store["ts1D"]
    i = bisect.bisect_left(tss, t_ms)
    xs = rows[max(0, i - n - 1):i]
    out = []
    for a, b in zip(xs, xs[1:]):
        if a[4] > 0:
            out.append(b[4] / a[4] - 1.0)
    return out


def corr(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    if n < 20:
        return 0.0
    a, b = a[-n:], b[-n:]
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((x - mb) ** 2 for x in b)
    if va <= 0 or vb <= 0:
        return 0.0
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb)


def diversification_factors(stores: dict[str, Any], active_pairs: list[str], t_ms: int) -> dict[str, float]:
    rets = {p: pct_returns_daily(stores[p], t_ms) for p in active_pairs}
    out: dict[str, float] = {}
    for p in active_pairs:
        vals = [corr(rets[p], rets[q]) for q in active_pairs if q != p and rets[p] and rets[q]]
        avg = statistics.fmean(vals) if vals else 0.0
        out[p] = round(max(0.68, 1.0 - max(0.0, avg - 0.40) * 0.62), 4)
    return out


def bot_members() -> dict[str, Any]:
    names = {
        "SPOT_GRID": "Spot Grid",
        "SPOT_DCA": "Spot DCA",
        "SMART_ARBITRAGE": "Smart Arbitrage",
        "RECURRING_BUY": "Recurring Buy",
    }
    out = {}
    for attr, label in names.items():
        if hasattr(BotType, attr):
            out[label] = getattr(BotType, attr)
    return out


def strategy_spot_dca(rows: list[tuple[int, float, float, float, float, float]]) -> float:
    if len(rows) < 2:
        return 0.0
    start = rows[0][4]; end = rows[-1][4]
    cash = 1.0; units = 0.0
    plan = [(0.00, .30), (-.02, .10), (-.04, .12), (-.07, .14), (-.10, .16), (-.14, .18)]
    for drop, weight in plan:
        level = start * (1 + drop)
        triggered = drop == 0 or any(r[3] <= level for r in rows)
        if triggered and cash > 0:
            spend = min(cash, weight)
            fill = level * (1 + SLIPPAGE)
            units += spend * (1 - SPOT_FEE) / fill
            cash -= spend
    return cash + units * end - 1.0


def strategy_recurring(rows: list[tuple[int, float, float, float, float, float]]) -> float:
    if len(rows) < 2:
        return 0.0
    end = rows[-1][4]; units = 0.0; cash = 1.0
    by_day: dict[int, tuple[int, float, float, float, float, float]] = {}
    for r in rows:
        by_day.setdefault(r[0] // 86400000, r)
    buys = list(by_day.values())[:7]
    if not buys:
        return 0.0
    amount = 1.0 / len(buys)
    for r in buys:
        fill = r[4] * (1 + SLIPPAGE)
        spend = min(cash, amount)
        units += spend * (1 - SPOT_FEE) / fill
        cash -= spend
    return cash + units * end - 1.0


def strategy_grid(rows: list[tuple[int, float, float, float, float, float]], atr_pct: float) -> float:
    if len(rows) < 3:
        return 0.0
    p0 = rows[0][4]
    width = max(.045, min(.18, max(.01, abs(float(atr_pct or 0)) / 100.0) * 3.2))
    lower, upper = p0 * (1 - width), p0 * (1 + width)
    ngrid = 12
    step = (upper - lower) / ngrid
    levels = [lower + i * step for i in range(ngrid + 1)]
    cash = 0.50
    units = 0.50 / p0
    order_cash = 0.50 / max(3, ngrid // 2)
    prev = p0
    for _, _, _, _, close, _ in rows[1:]:
        if close > prev:
            crossed = [x for x in levels if prev < x <= close]
            for level in crossed:
                sell_units = min(units, order_cash / max(level, 1e-12))
                if sell_units > 0:
                    cash += sell_units * level * (1 - GRID_FEE)
                    units -= sell_units
        elif close < prev:
            crossed = [x for x in levels if close <= x < prev]
            for level in reversed(crossed):
                spend = min(cash, order_cash)
                if spend > 0:
                    units += spend * (1 - GRID_FEE) / max(level, 1e-12)
                    cash -= spend
        prev = close
    value = cash + units * rows[-1][4]
    return value - 1.0


def strategy_arbitrage(store: dict[str, Any], start_ms: int, end_ms: int, newly_opened: bool) -> float:
    funding = future_funding_sum(store, start_ms, end_ms)
    # 50% of capital notionally supports each hedge leg; positive funding is received by the short leg.
    ret = 0.50 * funding
    if newly_opened:
        ret -= ARBITRAGE_ROUND_TRIP / 2.0
    return ret


def strategy_return(label: str, store: dict[str, Any], state: dict[str, Any], a_ms: int, b_ms: int, newly_opened: bool) -> float:
    rows = between_rows(store, a_ms, b_ms)
    if label == "Spot Grid":
        return strategy_grid(rows, float(state["metrics"].get("atr_pct") or 0))
    if label == "Spot DCA":
        return strategy_spot_dca(rows)
    if label == "Recurring Buy":
        return strategy_recurring(rows)
    if label == "Smart Arbitrage":
        return strategy_arbitrage(store, a_ms, b_ms, newly_opened)
    return 0.0


def max_drawdown(curve: list[dict[str, Any]]) -> dict[str, Any]:
    peak = -1.0; peak_date = None; worst = 0.0; trough_date = None; worst_peak = None
    for x in curve:
        eq = float(x["equity"])
        if eq > peak:
            peak = eq; peak_date = x["date"]
        if peak > 0:
            dd = eq / peak - 1.0
            if dd < worst:
                worst = dd; trough_date = x["date"]; worst_peak = peak_date
    return {"max_drawdown_pct": round(worst * 100, 2), "peak_date": worst_peak, "trough_date": trough_date}


def compounded_groups(weeks: list[dict[str, Any]], fmt: str) -> dict[str, float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for w in weeks:
        dt = datetime.fromisoformat(w["date"])
        grouped[dt.strftime(fmt)].append(float(w["return"]))
    return {k: round((math.prod(1 + r for r in rs) - 1) * 100, 2) for k, rs in grouped.items()}


def run_backtest() -> None:
    global RESULT
    try:
        log("Descargando archivo histórico Binance Vision (1H + funding), 10 pares")
        raw_data: dict[str, Any] = {}
        with ThreadPoolExecutor(max_workers=3) as pool:
            futs = {pool.submit(download_symbol, p): p for p in PAIRS}
            for fut in as_completed(futs):
                p = futs[fut]
                raw = fut.result()
                raw_data[p] = raw
                log(f"{p}: {len(raw['hourly']):,} velas 1H, {len(raw['funding']):,} funding records")
        stores = {p: build_store(raw_data[p]) for p in PAIRS if raw_data[p]["hourly"]}
        if "BTC/USDT" not in stores:
            raise RuntimeError("No se pudo descargar BTC/USDT; backtest abortado")
        latest_ms = min(int(TARGET_END.timestamp() * 1000), stores["BTC/USDT"]["ts1H"][-1])
        end_dt = datetime.fromtimestamp(latest_ms / 1000, tz=timezone.utc)
        effective_end = min(TARGET_END, end_dt - timedelta(days=7))
        log(f"Datos útiles hasta {end_dt.isoformat()}; última semana cerrada inicia antes de {effective_end.date()}")

        members = bot_members()
        if not members:
            raise RuntimeError(f"No se encontraron BotType compatibles. Enum={list(BotType)}")
        log("Bots evaluados: " + ", ".join(members))
        equity = 100.0
        curve = [{"date": START.isoformat(), "equity": equity}]
        weeks: list[dict[str, Any]] = []
        previous: dict[str, dict[str, Any]] = {}
        selection_counter: Counter[str] = Counter()
        pair_counter: Counter[str] = Counter()
        regime_counter: Counter[str] = Counter()
        switch_count = 0
        decision = START
        week_no = 0

        while decision <= effective_end:
            a_ms = int(decision.timestamp() * 1000)
            b_ms = int((decision + timedelta(days=7)).timestamp() * 1000)
            states: dict[str, Any] = {}
            for p, st in stores.items():
                state = state_for(p, st, a_ms)
                if state is not None and between_rows(st, a_ms, b_ms):
                    states[p] = state
            if not states:
                decision += timedelta(days=7)
                continue
            divers = diversification_factors(stores, list(states), a_ms)
            expected_n = 3 if equity < 160 else 4 if equity < 350 else 5
            trial_cap = equity / expected_n
            candidates = []
            for p, state in states.items():
                for label, bt in members.items():
                    key = f"{p}|{label}"
                    existed = key in previous
                    try:
                        ev = evaluate(bt, state, equity, trial_cap, 0.0, performance=50.0, leverage=1.0)
                    except Exception as exc:
                        log(f"evaluate omitido {key}: {type(exc).__name__}: {exc}")
                        continue
                    candidates.append({
                        "key": key, "pair": p, "bot_type": str(bt), "bot_label": label,
                        "score": float(ev["score"]), "confidence": float(ev["confidence"]),
                        "risk_score": float(ev["risk"]["score"]), "eligible": bool(ev["risk"].get("eligible", True)),
                        "existing": existed, "current_capital": float(previous.get(key, {}).get("amount", 0.0)),
                        "floating_pnl": 0.0, "diversification_factor": divers.get(p, 1.0),
                        "regime": state["regime"],
                    })
            if not candidates:
                decision += timedelta(days=7)
                continue
            alloc = allocate_100_percent(candidates, equity, minimums={})
            if not alloc.get("possible") or not alloc.get("allocations"):
                weeks.append({"date": decision.isoformat(), "return": 0.0, "equity_start": equity, "equity_end": equity, "allocations": [], "note": alloc.get("reason")})
                curve.append({"date": (decision + timedelta(days=7)).isoformat(), "equity": equity})
                decision += timedelta(days=7); week_no += 1
                continue
            week_ret = 0.0
            current: dict[str, dict[str, Any]] = {}
            compact_allocs = []
            for row in alloc["allocations"]:
                key = row["key"]; p = row["pair"]; label = row.get("bot_label") or next((lab for lab, bt in members.items() if str(bt) == str(row["bot_type"])), str(row["bot_type"]))
                weight = float(row["allocation_percent"]) / 100.0
                r = strategy_return(label, stores[p], states[p], a_ms, b_ms, key not in previous)
                # Hard safety cap prevents a proxy-model bug from creating impossible weekly returns.
                r = max(-0.65, min(0.65, r))
                week_ret += weight * r
                amount_next = equity * weight * (1 + r)
                current[key] = {"amount": amount_next, "pair": p, "label": label}
                selection_counter[label] += 1; pair_counter[p] += 1; regime_counter[str(states[p]["regime"])] += 1
                compact_allocs.append({"pair": p, "bot": label, "weight_pct": round(weight * 100, 2), "score": round(float(row.get("score", 0)), 1), "risk": round(float(row.get("risk_score", 0)), 1), "confidence": round(float(row.get("confidence", 0)), 1), "regime": states[p]["regime"], "strategy_return_pct": round(r * 100, 3)})
            old_keys, new_keys = set(previous), set(current)
            if week_no > 0:
                switch_count += len(old_keys.symmetric_difference(new_keys))
            equity_start = equity
            equity = max(0.01, equity * (1 + week_ret))
            # Scale carried current-capital references to portfolio end value.
            denom = sum(x["amount"] for x in current.values()) or 1.0
            for x in current.values():
                x["amount"] = equity * x["amount"] / denom
            weeks.append({"date": decision.isoformat(), "return": week_ret, "return_pct": round(week_ret * 100, 3), "equity_start": round(equity_start, 4), "equity_end": round(equity, 4), "allocations": compact_allocs})
            curve.append({"date": (decision + timedelta(days=7)).isoformat(), "equity": round(equity, 6)})
            previous = current
            week_no += 1
            if week_no % 26 == 0:
                log(f"Semana {week_no}: {decision.date()} | equity={equity:.2f} USDT")
            decision += timedelta(days=7)

        if not weeks:
            raise RuntimeError("No se generaron semanas de backtest")
        first_dt = datetime.fromisoformat(weeks[0]["date"])
        last_dt = datetime.fromisoformat(weeks[-1]["date"]) + timedelta(days=7)
        years = max((last_dt - first_dt).days / 365.25, 1 / 365.25)
        total_return = equity / 100.0 - 1.0
        cagr = (equity / 100.0) ** (1 / years) - 1 if equity > 0 else -1.0
        weekly_returns = [float(w["return"]) for w in weeks]
        avg_w = statistics.fmean(weekly_returns)
        sd_w = statistics.stdev(weekly_returns) if len(weekly_returns) > 1 else 0.0
        neg = [x for x in weekly_returns if x < 0]
        downside = math.sqrt(statistics.fmean([x * x for x in neg])) if neg else 0.0
        sharpe = avg_w / sd_w * math.sqrt(52) if sd_w else 0.0
        sortino = avg_w / downside * math.sqrt(52) if downside else 0.0
        dd = max_drawdown(curve)

        # BTC buy-and-hold benchmark over the same executed window.
        btc = stores["BTC/USDT"]
        a0 = int(first_dt.timestamp() * 1000); b0 = int(last_dt.timestamp() * 1000)
        btc_rows = between_rows(btc, a0, b0)
        btc_final = 100.0 * (btc_rows[-1][4] / btc_rows[0][4]) if len(btc_rows) >= 2 else None
        btc_cagr = ((btc_final / 100.0) ** (1 / years) - 1) if btc_final else None

        annual = compounded_groups(weeks, "%Y")
        monthly = compounded_groups(weeks, "%Y-%m")
        best = max(weeks, key=lambda x: x["return"])
        worst = min(weeks, key=lambda x: x["return"])
        result = {
            "status": "complete",
            "engine": "OKX Bot Analyzer v1.4 scoring/risk/allocation imported from current Render runtime",
            "period": {"requested_start": START.date().isoformat(), "requested_end": TARGET_END.date().isoformat(), "executed_start": first_dt.date().isoformat(), "executed_end": last_dt.date().isoformat(), "weeks": len(weeks), "years": round(years, 3)},
            "initial_capital": 100.0,
            "final_capital": round(equity, 2),
            "total_return_pct": round(total_return * 100, 2),
            "cagr_pct": round(cagr * 100, 2),
            "avg_weekly_return_pct": round(avg_w * 100, 3),
            "avg_monthly_return_pct_approx": round(((1 + avg_w) ** (52 / 12) - 1) * 100, 3),
            "annualized_weekly_volatility_pct": round(sd_w * math.sqrt(52) * 100, 2),
            "sharpe_rf0": round(sharpe, 3),
            "sortino_rf0": round(sortino, 3),
            "positive_weeks_pct": round(sum(1 for x in weekly_returns if x > 0) / len(weekly_returns) * 100, 1),
            "max_drawdown": dd,
            "best_week": {"date": best["date"], "return_pct": best["return_pct"]},
            "worst_week": {"date": worst["date"], "return_pct": worst["return_pct"]},
            "switch_events": switch_count,
            "selection_counts": dict(selection_counter.most_common()),
            "pair_selection_counts": dict(pair_counter.most_common()),
            "regime_counts": dict(regime_counter.most_common()),
            "annual_returns_pct": annual,
            "monthly_returns_pct": monthly,
            "btc_buy_hold": {"final_capital": round(btc_final, 2) if btc_final else None, "total_return_pct": round((btc_final / 100 - 1) * 100, 2) if btc_final else None, "cagr_pct": round(btc_cagr * 100, 2) if btc_cagr is not None else None},
            "methodology": {
                "decision_frequency": "Semanal, lunes 00:00 UTC; indicadores solo usan velas anteriores a la decisión.",
                "market_data": "Binance Vision spot 1H; 4H y 1D resampleados. Funding de Binance USD-M para Smart Arbitrage.",
                "timeframes": "1H/4H/1D históricos reales; 15m se aproxima con 1H por disponibilidad/volumen de archivo.",
                "news": "Neutralizado a 50/100 para evitar look-ahead; v1.4 usa noticias principalmente como overlay de riesgo bajista.",
                "execution": "Proxies explícitos: Grid de 12 niveles, DCA con 6 tramos, Recurring Buy diario y arbitraje delta-neutral por funding. Incluye fees/slippage conservadores.",
                "survivorship": "Universo fijo de los 10 pares V1; cada activo solo entra después de >=205 velas diarias de historia, por lo que listings tardíos no existen antes de tiempo.",
                "limitations": "No reproduce fills exactos de bots privados OKX, mínimos históricos variables, noticias point-in-time ni microestructura 15m. Es backtest del motor de decisión con modelos de ejecución reproducibles, no prueba de rentabilidad futura.",
            },
            "data_coverage": {p: {"hourly_rows": len(stores[p]["1H"]), "funding_rows": len(stores[p]["funding"]), "first": datetime.fromtimestamp(stores[p]["ts1H"][0] / 1000, tz=timezone.utc).date().isoformat(), "last": datetime.fromtimestamp(stores[p]["ts1H"][-1] / 1000, tz=timezone.utc).date().isoformat()} for p in stores},
            "weeks_detail": weeks,
            "equity_curve": curve,
        }
        with LOCK:
            RESULT = result
        log(f"COMPLETO final={equity:.2f} retorno={total_return*100:.2f}% CAGR={cagr*100:.2f}% MDD={dd['max_drawdown_pct']:.2f}% BTC={btc_final:.2f if btc_final else 0}")
        summary = {k: result[k] for k in ["status", "period", "initial_capital", "final_capital", "total_return_pct", "cagr_pct", "avg_weekly_return_pct", "avg_monthly_return_pct_approx", "annualized_weekly_volatility_pct", "sharpe_rf0", "sortino_rf0", "positive_weeks_pct", "max_drawdown", "best_week", "worst_week", "switch_events", "selection_counts", "pair_selection_counts", "annual_returns_pct", "btc_buy_hold", "data_coverage"]}
        print("BACKTEST_RESULT_SUMMARY=" + json.dumps(summary, ensure_ascii=False, separators=(",", ":")), flush=True)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        with LOCK:
            RESULT = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
        print("BACKTEST_ERROR=" + json.dumps(RESULT, ensure_ascii=False), flush=True)


app = FastAPI(title="OKX Bot Analyzer v1.4 Backtest")


@app.on_event("startup")
def startup() -> None:
    t = threading.Thread(target=run_backtest, daemon=True)
    t.start()


@app.get("/")
def root() -> JSONResponse:
    with LOCK:
        payload = {k: v for k, v in RESULT.items() if k not in {"weeks_detail", "equity_curve", "monthly_returns_pct"}}
    return JSONResponse(payload)


@app.get("/result")
def full_result() -> JSONResponse:
    with LOCK:
        return JSONResponse(RESULT)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))
