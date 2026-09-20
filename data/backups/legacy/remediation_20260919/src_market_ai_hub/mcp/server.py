"""MARKET_AI_HUB MCP stdio server（spec §25）。mcp>=2 使用 MCPServer API。

Tools：health_check / get_system_info / get_data_source_status / get_market_data /
predict_chronos / predict_timesfm / predict_ensemble / get_model_performance /
backtest / analyze_osaka_nikkei / analyze_taiwan_stock
"""
from __future__ import annotations

import json
import logging
import platform
from datetime import datetime, timezone

from mcp.server.mcpserver import MCPServer

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    filename=r"D:\MARKET_AI_HUB\logs\mcp.log",
)

mcp = MCPServer("market-ai-hub")


def _torch_info() -> dict:
    try:
        import torch

        return {
            "cuda_available": torch.cuda.is_available(),
            "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "none",
            "torch": torch.__version__,
        }
    except Exception as e:
        return {"cuda_available": False, "gpu": "none", "torch": "unavailable", "error": str(e)}


def _model_statuses() -> dict:
    out = {}
    try:
        from market_ai_hub.models.chronos_model import ChronosAdapter

        out["chronos"] = ChronosAdapter().status()
    except Exception as e:
        out["chronos"] = f"unavailable: {e}"
    try:
        from market_ai_hub.models.timesfm_model import TimesFM3Adapter

        out["timesfm"] = TimesFM3Adapter().status()
    except Exception as e:
        out["timesfm"] = f"unavailable: {e}"
    try:
        from market_ai_hub.models.fincast_model import FinCastAdapter

        out["fincast"] = FinCastAdapter().status()
    except Exception as e:
        out["fincast"] = f"unavailable: {e}"
    return out


@mcp.tool()
def health_check() -> dict:
    """整體健康檢查：models / providers / 環境。"""
    torch_info = _torch_info()
    ms = _model_statuses()
    try:
        from market_ai_hub.storage.duckdb_store import MarketStore

        MarketStore().init_schema()
        duckdb_status = "ok"
    except Exception as e:
        duckdb_status = f"error: {e}"
    try:
        from market_ai_hub.providers.registry import ProviderRegistry

        ps = {k: v.status.value for k, v in ProviderRegistry().status_all().items()}
    except Exception as e:
        ps = {"error": str(e)}
    return {
        "service": "market-ai-hub",
        "status": "ok",
        "python": platform.python_version(),
        "cuda_available": torch_info.get("cuda_available", False),
        "gpu": torch_info.get("gpu", "none"),
        "chronos": ms.get("chronos", "unavailable"),
        "timesfm": ms.get("timesfm", "unavailable"),
        "fincast": ms.get("fincast", "not-installed"),
        "twse": ps.get("twse", "unknown"),
        "finmind": ps.get("finmind", "unknown"),
        "fred": ps.get("fred", "unknown"),
        "yfinance": ps.get("yfinance", "unknown"),
        "duckdb": duckdb_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@mcp.tool()
def get_system_info() -> dict:
    """Python / GPU / CUDA / 路徑資訊。"""
    info = _torch_info()
    return {
        "python": platform.python_version(),
        "os": platform.platform(),
        **info,
        "project_path": r"D:\MARKET_AI_HUB",
    }


@mcp.tool()
def get_data_source_status() -> dict:
    """各資料來源狀態（TWSE/FinMind/FRED/yfinance/JQuants/TradingView/Broker）。"""
    from market_ai_hub.providers.registry import ProviderRegistry

    reg = ProviderRegistry()
    return {k: {"status": v.status.value, "message": v.message} for k, v in reg.status_all().items()}


@mcp.tool()
def get_market_data(symbol: str, period: str = "6mo", interval: str = "1d") -> dict:
    """取市場資料（yfinance symbols，或數字代碼走台股流程）。僅回傳結構化資料。"""
    from market_ai_hub.providers.yfinance_provider import YFinanceProvider

    df = YFinanceProvider().fetch(symbol, period=period, interval=interval)
    df = df.tail(60)
    return {
        "symbol": symbol,
        "rows": len(df),
        "last": df.iloc[-1].to_dict(),
        "data_grade": "RESEARCH_PROXY",
        "tail": df.tail(5).to_dict("records"),
    }


@mcp.tool()
def predict_chronos(symbol: str, period: str = "6mo", horizon: str = "1d") -> dict:
    """Chronos-2 預測。"""
    from market_ai_hub.models.chronos_model import ChronosAdapter, chronos_forecast
    from market_ai_hub.providers.yfinance_provider import YFinanceProvider

    df = YFinanceProvider().fetch(symbol, period=period)
    closes = df.sort_values("timestamp_utc")["close"].dropna()
    steps = 1 if horizon in ("5m", "15m", "30m", "60m") else 7
    return chronos_forecast(ChronosAdapter(), symbol, closes, horizon, steps).model_dump()


@mcp.tool()
def predict_timesfm(symbol: str, period: str = "6mo", horizon: str = "1d") -> dict:
    """TimesFM-3.0 預測（weights 為非商業授權，僅研究用途）。"""
    from market_ai_hub.models.timesfm_model import TimesFM3Adapter, timesfm_forecast
    from market_ai_hub.providers.yfinance_provider import YFinanceProvider

    df = YFinanceProvider().fetch(symbol, period=period)
    closes = df.sort_values("timestamp_utc")["close"].dropna()
    steps = 1 if horizon in ("5m", "15m", "30m", "60m") else 7
    return timesfm_forecast(TimesFM3Adapter(), symbol, closes, horizon, steps).model_dump()


@mcp.tool()
def predict_ensemble(symbol: str, period: str = "6mo", horizon: str = "1d") -> dict:
    """Chronos + TimesFM + XGBoost + LightGBM 等權 ensemble。"""
    from market_ai_hub.ensemble.ensemble import ensemble_equal_weight
    from market_ai_hub.features.features import build_features
    from market_ai_hub.models.baseline_ml import BaselineClassifier, baseline_forecast
    from market_ai_hub.models.chronos_model import ChronosAdapter, chronos_forecast
    from market_ai_hub.models.timesfm_model import TimesFM3Adapter, timesfm_forecast
    from market_ai_hub.providers.yfinance_provider import YFinanceProvider

    df = YFinanceProvider().fetch(symbol, period=period)
    closes = df.sort_values("timestamp_utc")["close"].dropna()
    steps = 1 if horizon in ("5m", "15m", "30m", "60m") else 7
    feat = build_features(df)
    models: list = []
    out: dict = {"symbol": symbol, "horizon": horizon}

    def _try(key, fn):
        try:
            fo = fn()
            out[key] = fo.model_dump()
            models.append(fo)
        except Exception as e:
            out[key] = {"status": "unavailable", "error": str(e)}

    _try("chronos", lambda: chronos_forecast(ChronosAdapter(), symbol, closes, horizon, steps))
    _try("timesfm", lambda: timesfm_forecast(TimesFM3Adapter(), symbol, closes, horizon, steps))
    for n in ("xgb", "lgbm"):
        _try(n, lambda n=n: baseline_forecast(BaselineClassifier(n), symbol, feat, horizon))
    out["ensemble"] = ensemble_equal_weight(models, symbol, horizon).model_dump() if models else {"status": "NO_MODELS_AVAILABLE"}
    return out


@mcp.tool()
def get_model_performance(model: str = "", limit: int = 20) -> dict:
    """讀取歷史 backtest 績效（model 空白 = 全部）。"""
    from market_ai_hub.storage.performance import PerformanceStore

    return {"records": PerformanceStore().list(model=model or None, limit=int(limit))}


@mcp.tool()
def backtest(symbol: str = "^N225", period: str = "1y", n_splits: int = 5, model: str = "lgbm") -> dict:
    """walk-forward backtest（yfinance 資料 + baseline 分類器）。"""
    from datetime import datetime, timezone as _tz

    import pandas as pd

    from market_ai_hub.backtest.walk_forward import compute_metrics, walk_forward_splits
    from market_ai_hub.features.features import build_features
    from market_ai_hub.models.baseline_ml import FEATURE_INPUT, BaselineClassifier
    from market_ai_hub.providers.yfinance_provider import YFinanceProvider
    from market_ai_hub.schemas.backtest import BacktestRecord
    from market_ai_hub.storage.performance import PerformanceStore

    df = YFinanceProvider().fetch(symbol, period=period)
    feat = build_features(df)
    valid = feat[FEATURE_INPUT].notna().all(axis=1) & feat["future_return_1"].notna()
    X = feat.loc[valid, FEATURE_INPUT]
    y = (feat.loc[valid, "future_return_1"] > 0.005).astype(int) - (feat.loc[valid, "future_return_1"] < -0.005).astype(int)
    data = pd.concat([X, y.rename("label")], axis=1)
    splits = walk_forward_splits(data, n_splits=int(n_splits))
    actual_all, pred_all, dirs = [], [], []
    for sp in splits:
        if sp.train.empty or sp.test.empty:
            continue
        m = BaselineClassifier(model)
        m.fit(sp.train[FEATURE_INPUT], sp.train["label"].to_numpy())
        preds = m.predict(sp.test[FEATURE_INPUT])
        dirs += ["up" if p == 1 else ("down" if p == -1 else "flat") for p in preds]
        actual_all += sp.test["label"].tolist()
        pred_all += [p for p in preds]
    if not actual_all:
        return {"status": "INSUFFICIENT_DATA"}
    from market_ai_hub.backtest.walk_forward import compute_metrics as _cm

    # label 是 -1/0/1，轉成報酬近似（用 threshold ±0.005 當方向報酬 proxy）
    act_ret = [0.005 if a == 1 else (-0.005 if a == -1 else 0.0) for a in actual_all]
    metrics = _cm(act_ret, pred_all, dirs)
    rec = BacktestRecord(
        model=model, model_version="1", data_version="yfinance-live",
        symbol=symbol, period=period, horizon="1d", feature_set="base-v1",
        timestamp=datetime.now(_tz.utc), brier_score=None, **metrics,
    )
    PerformanceStore().save(rec)
    return rec.model_dump()


@mcp.tool()
def analyze_osaka_nikkei(horizon: str = "1d") -> dict:
    """大阪日經 PROXY 分析（^N225 index + 跨市場；非 OSE micro 即時）— 只回傳 structured evidence。"""
    from market_ai_hub.services.analysis import analyze_osaka_nikkei as run

    return run(horizon)


@mcp.tool()
def analyze_taiwan_stock(stock: str, horizon: str = "1d") -> dict:
    """台股分析（如 2330 / 華邦電）。只回傳 structured evidence。"""
    from market_ai_hub.services.analysis import analyze_taiwan_stock as run

    return run(stock, horizon)


def main_sync() -> None:
    import asyncio

    asyncio.run(mcp.run_stdio_async())


if __name__ == "__main__":
    main_sync()
