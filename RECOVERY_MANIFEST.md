# OKX Bot Analyzer — Recovery Manifest

Recovery date: 2026-10-06

This file exists so the project no longer depends on chat history for its requirements or evolution.

## Source of truth recovered

The original project specification remains preserved in the ChatGPT Project as `Pasted text.txt` / `SPECIFICATION_V1.txt` and describes the decision-support philosophy, supported assets, bot taxonomy, risk model, scoring, screenshots, weekly history, auditability, WAIT/NO_TRADE behavior, and UI requirements.

Core principles to preserve:

- Do not force a trade because the user runs an analysis.
- `WAIT`, `NO NEW POSITION`, and maintaining reserve are valid recommendations.
- Analyze existing bots before proposing new ones.
- Favor continuity and apply switching cost; small score differences must not trigger needless changes.
- Preserve capital and risk-adjusted returns over raw return.
- Do not invent market data, news, minimums, or guarantees.
- Use multi-timeframe analysis; do not base decisions on one timeframe only.
- Futures and Spot must have different risk rules.
- Keep history and original recommendation snapshots auditable.
- Private OKX information is entered manually / via confirmed screenshots; no automatic private-account trading.
- Public market data may be used from reliable providers.

Supported V1 universe: BTC/USDT, ETH/USDT, SOL/USDT, XRP/USDT, DOGE/USDT, BNB/USDT, SUI/USDT, LINK/USDT, ADA/USDT, LTC/USDT.

## Repository history recovered

Initial Render/GitHub deployment began 2026-09-16. Important surviving milestones:

- `62660ef` — initialize repository
- `c16cf5e` … `5201cda` — upload the 8-part runtime bundle
- `0729406` — add bootstrap
- `792ef40` — add requirements
- `7223cbf` — human-readable source links
- `d16a039` — real OpenAI assistant responses
- `806f13f` — apply AI/source patches at runtime
- `9841ab1` / `e52f95f` — live assistant/key verification work
- `f301582` — route assistant through Gemini free tier
- `1a0eb79` / `8bfea40` — remove obsolete OpenAI gating
- `0aaf329` — keep readable source links
- `f8eadea` — bump public app to v1.2
- `cdb577a` — UI v1.2 / remove AI button
- `f0bd205` — v1.3 dynamic bot selection and news sentiment
- `5090925` — repair v1.3 frontend JS output
- `77bee1e` — run frontend repair before startup (last known repaired v1.3 baseline)
- `abc556b` / `2b7ea34` — v1.4 analysis and dynamic allocation

## Recovery diagnosis

The v1.3 repair in `runtime_js_fix.py` converted literal `\\n` fragments in generated JavaScript into real newlines. The v1.4 activation reused/overwrote `runtime_js_fix.py` for a much larger patch and removed that exact parser repair. This can leave the HTML/CSS rendered while `app.js` fails to parse, making navigation/buttons appear dead.

## Safe recovery branches

- `recovery-v13-20261006`: exact branch from `77bee1e` (last known repaired v1.3 baseline).
- `recovery-v14-ui-20261006`: current v1.4 plus a recovery launcher that reapplies the lost JS parser fix after the v1.4 patch.
- `backtest-v14-20261006`: isolated historical backtest work; never use this branch as production without review.

## Production recovery policy

1. Never force-push or replace `main` before a recovery build is tested on a separate Render URL.
2. Keep the original production domain so browser localStorage can remain accessible.
3. Before changing production, export browser-local data if possible.
4. Validate all primary UI interactions: sidebar, Analyze market, capital registration, bot creation/edit/close, Results, History, Library, source links, backup/export.
5. Only after validation, promote the repaired code to the original Render service.
6. Preserve this manifest and future change logs in Git.

## Backtesting note

The isolated v1.4 replay from 2021-10-11 to 2026-10-05 using 100 USDT finished at 65.36 USDT (-34.64%) with -55.51% max drawdown. That test exposed risk-policy problems and should be treated as a diagnostic of v1.4, not as a reason to discard recovered UI/functionality or the original project requirements.
