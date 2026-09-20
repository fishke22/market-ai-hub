"""Analysis service：analyze_osaka_nikkei / analyze_taiwan_stock 共用邏輯（spec §25）。

只回傳 structured evidence（JSON 事實），自然語言分析交給 Cherry Studio LLM。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pandas as pd

from market_ai_hub.config.settings import load_symbols
from market_ai_hub.models.baseline_ml import BaselineClassifier, baseline_forecast
from market_ai_hub.models.chronos_model import ChronosAdapter, chronos_forecast
from market_ai_hub.models.timesfm_model import TimesFM3Adapter, timesfm_forecast
from market_ai_hub.providers.finmind import FinMindProvider
from market_ai_hub.providers.twse import TWSEProvider
from market_ai_hub.providers.yfinance_provider import YFinanceProvider
from market_ai_hub.ensemble.ensemble import ensemble_equal_weight

log = logging.getLogger(__name__)

HORIZON_ALIASES = {"5m": 1, "15m": 1, "30m": 1, "60m": 1, "1d": 1}


def _daily_closes(df: pd.DataFrame) -> pd.Series:
    return df.sort_values("timestamp_utc")["close"].dropna()


def analyze_osaka_nikkei(horizon: str = "1d") -> dict:
    """大阪日經：第一階段為 PROXY 骨架（^N225 + 跨市場），不是 OSE micro 即時模型。

    data_grade 一律 RESEARCH_PROXY，明確不得宣稱 exchange-grade。
    """
    yf = YFinanceProvider()
    symbols = [s["symbol"] for s in load_symbols() if s["provider"] == "yfinance"]
    data: dict[str, pd.DataFrame] = {}
    warnings: list[str] = []
    for sym in symbols:
        try:
            data[sym] = yf.fetch(sym, period="1y", interval="1d")
        except Exception as e:
            warnings.append(f"{sym}: {e}")

    target_sym = "^N225"
    if target_sym not in data:
        return {
            "status": "PROXY_DATA_UNAVAILABLE",
            "data_grade": "RESEARCH_PROXY",
            "message": "yfinance ^N225 取得失敗（此為 Nikkei 225 INDEX proxy，非 OSE micro futures）",
            "warnings": warnings,
        }

    closes = _daily_closes(data[target_sym])
    horizon_steps = 1 if horizon in ("5m", "15m", "30m", "60m") else 7

    results: dict = {"symbol": target_sym, "horizon": horizon, "as_of": datetime.now(timezone.utc).isoformat()}
    models: list = []

    # Chronos
    try:
        chronos = ChronosAdapter()
        fo = chronos_forecast(chronos, target_sym, closes, horizon=horizon, horizon_steps=horizon_steps)
        results["chronos"] = fo.model_dump()
        models.append(fo)
    except Exception as e:
        log.warning("chronos failed in osaka analysis: %s", e)
        results["chronos"] = {"status": "unavailable", "error": str(e)}
        warnings.append(f"chronos: {e}")

    # TimesFM
    try:
        timesfm = TimesFM3Adapter()
        fo = timesfm_forecast(timesfm, target_sym, closes, horizon=horizon, horizon_steps=horizon_steps)
        results["timesfm"] = fo.model_dump()
        models.append(fo)
    except Exception as e:
        log.warning("timesfm failed in osaka analysis: %s", e)
        results["timesfm"] = {"status": "unavailable", "error": str(e)}
        warnings.append(f"timesfm: {e}")

    # baseline ML
    from market_ai_hub.features.features import build_features

    feat = build_features(data[target_sym])
    for name in ("xgb", "lgbm"):
        try:
            fo = baseline_forecast(BaselineClassifier(name), target_sym, feat, horizon=horizon)
            results[name] = fo.model_dump()
            models.append(fo)
        except Exception as e:
            log.warning("%s failed in osaka analysis: %s", name, e)
            results[name] = {"status": "unavailable", "error": str(e)}
            warnings.append(f"{name}: {e}")

    if models:
        ens = ensemble_equal_weight(models, target_sym, horizon)
        results["ensemble"] = ens.model_dump()
    else:
        results["ensemble"] = {"status": "NO_MODELS_AVAILABLE"}

    cross = {}
    for sym, df in data.items():
        if sym != target_sym and len(df) > 2:
            c = _daily_closes(df)
            cross[sym] = {
                "last": float(c.iloc[-1]),
                "return_1d": float(c.pct_change().iloc[-1]),
            }
    results["cross_market"] = cross

    results["status"] = "OK"
    results["data_grade"] = "RESEARCH_PROXY"
    results["disclaimer"] = (
        "^N225 為 Nikkei 225 INDEX 代理資料（RESEARCH_PROXY/DELAYED），"
        "非 OSE Nikkei 225 micro futures 即時行情。無 free exchange-grade OSE micro 資料源。"
    )
    results["warnings"] = warnings
    return results


def analyze_taiwan_stock(stock: str, horizon: str = "1d") -> dict:
    """台股分析：優先 FinMind（OFFICIAL_DAILY），fallback TWSE OpenAPI，再 fallback yfinance。"""
    warnings: list[str] = []
    df: pd.DataFrame | None = None
    provider_name = ""
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc) - timedelta(days=730)).strftime("%Y-%m-%d")

    fm = FinMindProvider()
    if fm.status().status.value in ("ok", "needs_config"):
        try:
            df = fm.fetch_price(stock, start, end)
            provider_name = "finmind"
        except Exception as e:
            warnings.append(f"finmind: {e}")

    if df is None:
        twse = TWSEProvider()
        try:
            # TWSE fallback 只取最近 180 天（STOCK_DAY_ALL 逐日迭代，太長會太慢）
            twse_start = (datetime.now(timezone.utc) - timedelta(days=180)).strftime("%Y%m%d")
            df = twse.fetch_symbol_daily(stock, twse_start, end.replace("-", ""))
            provider_name = "twse"
        except Exception as e:
            warnings.append(f"twse: {e}")

    if df is None or df.empty:
        return {"status": "DATA_UNAVAILABLE", "symbol": stock, "warnings": warnings,
                "message": "FinMind 與 TWSE 皆無法取得資料（FinMind 需要 FINMIND_TOKEN）"}

    closes = _daily_closes(df)
    horizon_steps = 1 if horizon in ("5m", "15m", "30m", "60m") else 7
    results: dict = {"symbol": stock, "provider": provider_name, "horizon": horizon,
                     "as_of": datetime.now(timezone.utc).isoformat()}
    models: list = []

    try:
        fo = chronos_forecast(ChronosAdapter(), stock, closes, horizon=horizon, horizon_steps=horizon_steps,
                              data_grade="OFFICIAL_DAILY")
        results["chronos"] = fo.model_dump()
        models.append(fo)
    except Exception as e:
        results["chronos"] = {"status": "unavailable", "error": str(e)}
        warnings.append(f"chronos: {e}")

    try:
        fo = timesfm_forecast(TimesFM3Adapter(), stock, closes, horizon=horizon, horizon_steps=horizon_steps,
                              data_grade="OFFICIAL_DAILY")
        results["timesfm"] = fo.model_dump()
        models.append(fo)
    except Exception as e:
        results["timesfm"] = {"status": "unavailable", "error": str(e)}
        warnings.append(f"timesfm: {e}")

    from market_ai_hub.features.features import build_features

    feat = build_features(df)
    for name in ("xgb", "lgbm"):
        try:
            fo = baseline_forecast(BaselineClassifier(name), stock, feat, horizon=horizon,
                                   data_grade="OFFICIAL_DAILY")
            results[name] = fo.model_dump()
            models.append(fo)
        except Exception as e:
            results[name] = {"status": "unavailable", "error": str(e)}
            warnings.append(f"{name}: {e}")

    results["ensemble"] = ensemble_equal_weight(models, stock, horizon).model_dump() if models else {"status": "NO_MODELS_AVAILABLE"}
    results["status"] = "OK"
    results["data_grade"] = "OFFICIAL_DAILY"
    results["warnings"] = warnings
    return results
