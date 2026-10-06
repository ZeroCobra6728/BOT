from __future__ import annotations

import os
from dataclasses import dataclass, field

APP_NAME = "OKX Bot Analyzer"
APP_VERSION = "1.4"

SUPPORTED_PAIRS = (
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT",
    "BNB/USDT", "SUI/USDT", "LINK/USDT", "ADA/USDT", "LTC/USDT",
)
TIMEFRAMES = ("15m", "1H", "4H", "1D")
OKX_BAR_MAP = {"15m": "15m", "1H": "1H", "4H": "4H", "1D": "1Dutc"}

SCORE_WEIGHTS = {
    "market": 0.16,
    "technical": 0.12,
    "trend": 0.10,
    "volatility": 0.12,
    "compatibility": 0.30,
    "performance": 0.17,
    "capital_efficiency": 0.03,
    "news_sentiment": 0.00,
    "confidence": 0.00,
}

SCORE_BANDS = (
    (0, 39, "Débil"),
    (40, 59, "Neutral / precaución"),
    (60, 74, "Aceptable"),
    (75, 89, "Favorable"),
    (90, 100, "Muy favorable"),
)

TIMEFRAME_WEIGHTS = {"15m": 0.10, "1H": 0.20, "4H": 0.35, "1D": 0.35}
TIMEFRAME_PERIODS_PER_YEAR = {"15m": 365 * 24 * 4, "1H": 365 * 24, "4H": 365 * 6, "1D": 365}

@dataclass(frozen=True)
class RiskConfig:
    target_allocation_pct: float = 1.0
    allocation_tolerance_pct: float = 0.0001
    max_asset_exposure_pct: float = 0.60
    max_single_bot_pct: float = 0.60
    max_total_futures_pct: float = 0.20
    max_leverage: float = 3.0
    min_reserve_pct: float = 0.0
    min_open_score: float = 58.0
    min_open_confidence: float = 45.0
    min_open_conviction: float = 58.0
    min_hold_conviction: float = 46.0
    min_switch_advantage: float = 9.0
    high_risk_cutoff: float = 70.0
    futures_ineligible_risk: float = 65.0
    enable_futures_dca_new_positions: bool = False
    min_recommended_bots: int = 2
    max_recommended_bots: int = 5
    min_practical_allocation_pct: float = 0.10
    continuity_bonus: float = 3.0

@dataclass(frozen=True)
class CacheConfig:
    market_seconds: int = 120
    indicators_seconds: int = 180
    news_seconds: int = 900
    docs_seconds: int = 86400
    minimums_seconds: int = 3600

@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/okx_bot_analyzer.db")
    data_mode: str = os.getenv("DATA_MODE", "REAL").upper()
    public_mode: bool = os.getenv("PUBLIC_MODE", "true").lower() in {"1", "true", "yes", "on"}
    okx_base_url: str = os.getenv("OKX_BASE_URL", "https://www.okx.com")
    coingecko_base_url: str = os.getenv("COINGECKO_BASE_URL", "https://api.coingecko.com/api/v3")
    request_timeout_seconds: float = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "10"))
    news_api_key: str | None = os.getenv("NEWS_API_KEY") or None
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY") or os.getenv("AI_API_KEY") or None
    ai_model: str = os.getenv("AI_MODEL", "gpt-5.6-luna")
    private_upload_dir: str = os.getenv("PRIVATE_UPLOAD_DIR", "./data/private/screenshots")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    risk: RiskConfig = field(default_factory=RiskConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)

settings = Settings()
