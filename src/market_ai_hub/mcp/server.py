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

from market_ai_hub.config.settings import project_root

_LOG_DIR = project_root() / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    filename=str(_LOG_DIR / "mcp.log"),
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
    """整體健康檢查：models / providers / 環境 / build fingerprint。"""
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
    from market_ai_hub.services.build_info import build_fingerprint

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
        "build": build_fingerprint(),
    }


@mcp.tool()
def get_system_info() -> dict:
    """Python / GPU / CUDA / models（role + task + dual status）/ ensemble / MCP tools / gates / build fingerprint。"""
    info = _torch_info()
    cards = _model_cards()
    gates = _research_gates(cards)
    from market_ai_hub.services.build_info import build_fingerprint

    return {
        "python": platform.python_version(),
        "os": platform.platform(),
        **info,
        "project_path": r"D:\MARKET_AI_HUB",
        "models": {
            n: {
                "model_role": c.role,
                "model_task": c.model_task,
                "engineering_status": c.engineering_status,
                "predictive_validation_status": c.predictive_validation_status,
                "eligible_for_price_reference": c.eligible_for_price_reference,
                "eligible_for_direction_vote": c.eligible_for_direction_vote,
                "eligible_for_ensemble_weighting": c.eligible_for_ensemble_weighting,
            }
            for n, c in cards.items()
        },
        "ensemble_composition": {
            "method": "EQUAL_WEIGHT_RESEARCH",
            "experimental": True,
            "base_models": ["chronos-2", "timesfm-3.0", "xgboost", "lightgbm"],
            "price_ensemble": ["chronos-2", "timesfm-3.0"],
            "direction_ensemble": ["xgboost", "lightgbm"],
            "ensemble_role": "ENSEMBLE (not an independent model)",
        },
        "mcp_tools": sorted(_tool_names()),
        "research_gates": gates,
        "build": build_fingerprint(),
    }


def _model_cards():
    from market_ai_hub.services.model_catalog import live_model_cards

    return live_model_cards()


def _research_gates(cards):
    from market_ai_hub.services.model_catalog import compute_research_gates

    return compute_research_gates(cards)


def _tool_names() -> list[str]:
    import asyncio

    return asyncio.run(_async_tool_names())


async def _async_tool_names() -> list[str]:
    tools = await mcp.list_tools()
    return [t.name for t in tools]


@mcp.tool()
def get_research_gates() -> dict:
    """Research validation gates：ENGINEERING_GATE / DATA_GATE / MODEL_PREDICTIVE_GATE / TRADING_EDGE_GATE。

    每次評估基於 current runtime（singleton 載入），帶 evaluated_at / build_id / evidence。"""
    cards = _model_cards()
    gates = _research_gates(cards)
    return {
        "gates": gates,
        "note": "MODEL_PREDICTIVE_GATE=UNPROVEN 指 GENERAL_PRODUCTION_MODEL_GATE_UNPROVEN（非 NO_OOS_TEST_EXISTS）；"
                "TRADING_EDGE_GATE.result=NO_ECONOMIC_EDGE：Phase2 cost/slippage strategy validation completed",
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
    """Chronos-2 多步預測。horizon "Nd" = N trading bars（1d/2d/5d/10d）。含 build fingerprint。"""
    from market_ai_hub.models.chronos_model import chronos_forecast
    from market_ai_hub.providers.yfinance_provider import YFinanceProvider
    from market_ai_hub.services.build_info import build_fingerprint
    from market_ai_hub.services.forecast_cache import forecast_cache_key, get_cached, set_cached
    from market_ai_hub.services.horizon import HorizonUnsupportedError, parse_horizon
    from market_ai_hub.services.model_runtime import get_chronos
    from market_ai_hub.services.perf_trace import trace

    with trace("predict_chronos") as t:
        spec = parse_horizon(horizon, "1d")
        if not spec.supported:
            return {
                "status": "UNSUPPORTED_WITH_CURRENT_DATA",
                "requested_horizon": horizon,
                "data_frequency": "1d",
                "reason": spec.reason,
                "build": build_fingerprint(),
            }
        df = YFinanceProvider().fetch(symbol, period=period)
        closes = df.sort_values("timestamp_utc").set_index("timestamp_utc")["close"].dropna()
        fp = build_fingerprint()
        key = forecast_cache_key("chronos-2", symbol, horizon, closes, fp["build_id"])
        cached = get_cached(key)
        if cached is not None:
            cached["cache_hit"] = True
            if isinstance(t, dict):
                t["cache_hit"] = True
            return cached
        try:
            t0 = __import__("time").perf_counter()
            fo = chronos_forecast(get_chronos(), symbol, closes, horizon, spec.effective_horizon_steps)
            if isinstance(t, dict):
                t["model_inference_ms"] = round((__import__("time").perf_counter() - t0) * 1000, 2)
                t["cache_hit"] = False
            d = fo.model_dump()
            d["build"] = fp
            d["cache_hit"] = False
            set_cached(key, d)
            return d
        except HorizonUnsupportedError as e:
            return {"status": "UNSUPPORTED_WITH_CURRENT_DATA", "requested_horizon": horizon, "reason": str(e), "build": fp}


@mcp.tool()
def predict_timesfm(symbol: str, period: str = "6mo", horizon: str = "1d") -> dict:
    """TimesFM-3.0 多步預測（weights 非商業授權）。含 build fingerprint。"""
    from market_ai_hub.models.timesfm_model import timesfm_forecast
    from market_ai_hub.providers.yfinance_provider import YFinanceProvider
    from market_ai_hub.services.build_info import build_fingerprint
    from market_ai_hub.services.forecast_cache import forecast_cache_key, get_cached, set_cached
    from market_ai_hub.services.horizon import HorizonUnsupportedError, parse_horizon
    from market_ai_hub.services.model_runtime import get_timesfm
    from market_ai_hub.services.perf_trace import trace

    with trace("predict_timesfm") as t:
        spec = parse_horizon(horizon, "1d")
        if not spec.supported:
            return {
                "status": "UNSUPPORTED_WITH_CURRENT_DATA",
                "requested_horizon": horizon,
                "data_frequency": "1d",
                "reason": spec.reason,
                "build": build_fingerprint(),
            }
        df = YFinanceProvider().fetch(symbol, period=period)
        closes = df.sort_values("timestamp_utc").set_index("timestamp_utc")["close"].dropna()
        fp = build_fingerprint()
        key = forecast_cache_key("timesfm-3.0", symbol, horizon, closes, fp["build_id"])
        cached = get_cached(key)
        if cached is not None:
            cached["cache_hit"] = True
            if isinstance(t, dict):
                t["cache_hit"] = True
            return cached
        try:
            t0 = __import__("time").perf_counter()
            fo = timesfm_forecast(get_timesfm(), symbol, closes, horizon, spec.effective_horizon_steps)
            if isinstance(t, dict):
                t["model_inference_ms"] = round((__import__("time").perf_counter() - t0) * 1000, 2)
                t["cache_hit"] = False
            d = fo.model_dump()
            d["build"] = fp
            d["cache_hit"] = False
            set_cached(key, d)
            return d
        except HorizonUnsupportedError as e:
            return {"status": "UNSUPPORTED_WITH_CURRENT_DATA", "requested_horizon": horizon, "reason": str(e), "build": fp}


@mcp.tool()
def predict_ensemble(symbol: str, period: str = "6mo", horizon: str = "1d") -> dict:
    """Chronos + TimesFM + XGBoost + LightGBM ensemble。

    V1.1 語義：price_ensemble（PRICE_FORECAST 真 quantile）與
    direction_ensemble（DIRECTION_CLASSIFICATION）分層；legacy 欄位標 legacy_research_only。"""
    from market_ai_hub.ensemble.ensemble import ensemble_equal_weight, independent_vote_summary
    from market_ai_hub.features.features import build_features
    from market_ai_hub.models.baseline_ml import BaselineClassifier, baseline_forecast
    from market_ai_hub.models.chronos_model import chronos_forecast
    from market_ai_hub.models.timesfm_model import timesfm_forecast
    from market_ai_hub.providers.yfinance_provider import YFinanceProvider
    from market_ai_hub.services.build_info import build_fingerprint
    from market_ai_hub.services.horizon import parse_horizon
    from market_ai_hub.services.model_runtime import get_chronos, get_timesfm

    spec = parse_horizon(horizon, "1d")
    if not spec.supported:
        return {
            "status": "UNSUPPORTED_WITH_CURRENT_DATA",
            "requested_horizon": horizon,
            "data_frequency": "1d",
            "reason": spec.reason,
            "build": build_fingerprint(),
        }
    steps = spec.effective_horizon_steps
    df = YFinanceProvider().fetch(symbol, period=period)
    closes = df.sort_values("timestamp_utc").set_index("timestamp_utc")["close"].dropna()
    feat = build_features(df)
    models: list = []
    out: dict = {"symbol": symbol, "horizon": horizon, "data_frequency": "1d"}

    def _try(key, fn):
        try:
            fo = fn()
            out[key] = fo.model_dump()
            models.append(fo)
        except Exception as e:
            out[key] = {"status": "unavailable", "error": str(e)}

    _try("chronos", lambda: chronos_forecast(get_chronos(), symbol, closes, horizon, steps))
    _try("timesfm", lambda: timesfm_forecast(get_timesfm(), symbol, closes, horizon, steps))
    for n in ("xgb", "lgbm"):
        _try(n, lambda n=n: baseline_forecast(BaselineClassifier(n), symbol, feat, horizon))

    if models:
        ens = ensemble_equal_weight(models, symbol, horizon)
        out["ensemble"] = ens.model_dump()
        out["ensemble_result"] = ens.model_dump()
        out["used_ensemble"] = True
        mm = ens.model_metadata
        out["price_forecast_ensemble"] = mm.get("price_ensemble", {})
        out["direction_classification_ensemble"] = mm.get("direction_ensemble", {})
        out["ensemble_validation_level"] = mm.get("validation_level", "RESEARCH")
        out["legacy_research_only"] = mm.get("legacy_research_only", True)
        # 頂層 horizon integrity
        out["requested_horizon"] = ens.requested_horizon
        out["effective_horizon_steps"] = ens.effective_horizon_steps
        out["terminal_forecast"] = ens.terminal_forecast
        out["forecast_dates"] = ens.forecast_dates
        out["forecast_path"] = ens.forecast_path
        out["target_calendar"] = ens.target_calendar
        out["calendar_grade"] = ens.calendar_grade
    else:
        out["ensemble"] = {"status": "NO_MODELS_AVAILABLE"}
        out["used_ensemble"] = False

    vote = independent_vote_summary(models)
    out.update(vote)
    out["used_base_models"] = [f.model for f in models]
    out["build"] = build_fingerprint()
    return out


@mcp.tool()
def get_model_performance(model: str = "", limit: int = 20) -> dict:
    """讀取歷史 backtest 績效（model 空白 = 全部）。

    分類指標不再硬用 50% 門檻：baseline_threshold = max(majority_class_baseline, uniform_random_baseline)。
    沒有資料的欄位回 null（不是 0）。
    """
    from market_ai_hub.storage.performance import PerformanceStore

    records = PerformanceStore().list(model=model or None, limit=int(limit))
    return {
        "records": records,
        "baseline_note": "classification gate threshold = max(majority_class_baseline_accuracy, uniform_random_baseline_accuracy=1/3); 50% 不再是通用門檻",
    }


@mcp.tool()
def backtest(symbol: str = "^N225", period: str = "1y", n_splits: int = 5, model: str = "lgbm") -> dict:
    """walk-forward backtest（yfinance 資料 + baseline 分類器）。

    輸出含分類指標（accuracy/balanced_accuracy/macro_f1/mcc）與 baselines
    （uniform_random=1/3、majority_class_baseline、naive direction baseline）。
    """
    from datetime import datetime, timezone as _tz

    import pandas as pd

    from market_ai_hub.backtest.walk_forward import (
        classification_metrics,
        compute_metrics,
        walk_forward_splits,
    )
    from market_ai_hub.features.features import build_features, future_return_k
    from market_ai_hub.models.baseline_ml import FLAT_THRESHOLD, FEATURE_INPUT, BaselineClassifier
    from market_ai_hub.providers.yfinance_provider import YFinanceProvider
    from market_ai_hub.schemas.backtest import BacktestRecord
    from market_ai_hub.storage.performance import PerformanceStore

    df = YFinanceProvider().fetch(symbol, period=period)
    feat = build_features(df)
    valid = feat[FEATURE_INPUT].notna().all(axis=1) & feat["future_return_1"].notna()
    X = feat.loc[valid, FEATURE_INPUT]
    y = (feat.loc[valid, "future_return_1"] > FLAT_THRESHOLD).astype(int) - (feat.loc[valid, "future_return_1"] < -FLAT_THRESHOLD).astype(int)
    data = pd.concat([X, y.rename("label")], axis=1)
    splits = walk_forward_splits(data, n_splits=int(n_splits))
    actual_all, pred_all, dirs, train_labels_all = [], [], [], []
    for sp in splits:
        if sp.train.empty or sp.test.empty:
            continue
        m = BaselineClassifier(model)
        m.fit(sp.train[FEATURE_INPUT], sp.train["label"].to_numpy())
        preds = m.predict(sp.test[FEATURE_INPUT])
        dirs += ["up" if p == 1 else ("down" if p == -1 else "flat") for p in preds]
        actual_all += sp.test["label"].tolist()
        pred_all += [p for p in preds]
        train_labels_all += sp.train["label"].tolist()
    if not actual_all:
        return {"status": "INSUFFICIENT_DATA"}

    # label 是 -1/0/1；報酬近似（threshold ±0.5% 當方向報酬 proxy）沿用 v1 指標
    act_ret = [FLAT_THRESHOLD if a == 1 else (-FLAT_THRESHOLD if a == -1 else 0.0) for a in actual_all]
    metrics = compute_metrics(act_ret, pred_all, dirs)

    cm = classification_metrics(actual_all, pred_all, train_labels_all)

    # naive direction baseline：always predict majority class（train 分佈）
    from collections import Counter

    majority_class = Counter(train_labels_all).most_common(1)[0][0] if train_labels_all else 0
    naive_dir_preds = [majority_class] * len(actual_all)
    naive_cm = classification_metrics(actual_all, naive_dir_preds, train_labels_all)

    # 以 OOS 是否超越 baseline 決定 validation status / eligibility
    beat = bool(cm["beats_majority_baseline"])
    val_status = "EXPERIMENTAL" if beat else "DEGRADED"

    rec = BacktestRecord(
        model=model, model_version="2", data_version="yfinance-live",
        symbol=symbol, period=period, horizon="1d", feature_set="base-v1",
        timestamp=datetime.now(_tz.utc),
        task_type="classification",
        classes=[-1, 0, 1],
        flat_threshold=FLAT_THRESHOLD,
        accuracy=cm["accuracy"],
        balanced_accuracy=cm["balanced_accuracy"],
        macro_f1=cm["macro_f1"],
        mcc=cm["mcc"],
        mase=None,
        class_distribution=cm["class_distribution"],
        uniform_random_baseline_accuracy=cm["uniform_random_baseline_accuracy"],
        majority_class_baseline_accuracy=cm["majority_class_baseline_accuracy"],
        baseline_threshold=cm["baseline_threshold"],
        beats_majority_baseline=beat,
        engineering_status="PASS",
        predictive_validation_status=val_status,
        eligible_for_direction_vote=beat,
        baseline_results={
            "naive_majority_class_model": naive_cm,
            "last_price_naive_mae": None,
        },
        sample_size=len(actual_all),
        date_range={"start": str(df["timestamp_utc"].min()), "end": str(df["timestamp_utc"].max())},
        brier_score=None,
        **metrics,
    )
    PerformanceStore().save(rec)
    out = rec.model_dump()
    out["naive_majority_class_baseline"] = naive_cm
    out["note"] = "50% 不是通用門檻；判定用 baseline_threshold = max(majority, uniform)"
    return out


@mcp.tool()
def run_ts_validation(symbol: str = "^N225", period: str = "1y", n_folds: int = 5, model: str = "chronos-2") -> dict:
    """時間序列模型 rolling-origin OOS 驗證（V1.1 pipeline）。

    - 多 rolling origins、no look-ahead、每 fold 預測下一 bar
    - 比較 last-price naive / drift / moving-average baselines（MAE/RMSE/MASE）
    - interval coverage：p10-p90 nominal 80% 的實測覆蓋率 + calibration error
    - deterministic promotion（services/validation.PROMOTION_RULES），結果持久化
    """
    from market_ai_hub.providers.yfinance_provider import YFinanceProvider
    from market_ai_hub.services.model_runtime import get_chronos, get_timesfm
    from market_ai_hub.services.validation import (
        TsValidationStore,
        determine_validation_status,
        run_ts_oos_validation,
    )

    df = YFinanceProvider().fetch(symbol, period=period)
    closes = df.sort_values("timestamp_utc").set_index("timestamp_utc")["close"].dropna()

    if model == "chronos-2":
        adapter = get_chronos()
    elif model == "timesfm-3.0":
        adapter = get_timesfm()
    else:
        return {"status": "UNSUPPORTED_MODEL", "model": model}

    result = run_ts_oos_validation(adapter, model, symbol, closes, n_origins=int(n_folds))
    if result.get("status") != "OK":
        return result

    status, reasons = determine_validation_status(result)
    TsValidationStore().save(result, status)
    result["predictive_validation_status"] = status
    result["promotion_reasons"] = reasons
    result["promotion_rules"] = {
        "UNVALIDATED_TO_EXPERIMENTAL": {
            "min_rolling_origins": 3, "min_oos_samples": 10, "must_beat": "last_price_naive (MAE)",
        },
        "EXPERIMENTAL_TO_VALIDATED": {
            "min_rolling_origins": 8, "min_oos_samples": 50, "must_beat": "last_price_naive + drift",
            "mase_max": 1.0, "min_windows": 2,
        },
    }
    return result


@mcp.tool()
def analyze_osaka_nikkei(horizon: str = "1d", requested_dates: str = "") -> dict:
    """大阪日經 PROXY 分析（^N225 index + 跨市場；非 OSE micro 即時）。

    requested_dates（可選）："YYYY-MM-DD..YYYY-MM-DD"。^N225 依 TSE 日曆交易；
    若窗口含 TSE 休市日（OSE futures 可能 Holiday Trading）→ CALENDAR_TARGET_MISMATCH。"""
    from market_ai_hub.services.analysis import analyze_osaka_nikkei as run

    return run(horizon, requested_dates)


@mcp.tool()
def analyze_taiwan_stock(stock: str, horizon: str = "1d") -> dict:
    """台股分析（如 2330 / 3706.TW / 華邦電）。只回傳 structured evidence。"""
    from market_ai_hub.services.analysis import analyze_taiwan_stock as run

    return run(stock, horizon)


@mcp.tool()
def get_analysis_packet(market: str = "osaka", target: str = "OSE_NIKKEI225_MICRO_FUTURES",
                        horizon: str = "1d", detail_level: str = "compact",
                        save_analysis: bool = True) -> dict:
    """正式分析封包（backend 先完成大部分工作）。

    market: osaka | taiwan。target 例：OSE_NIKKEI225_MICRO_FUTURES / 3706.TW。
    horizon: 1d/2d/5d/10d。detail_level: compact | normal | audit。
    ^N225 只能是 PROXY/REFERENCE，不得當 execution target。
    """
    from market_ai_hub.packet.builder import build_analysis_packet

    return build_analysis_packet(market=market, target=target, horizon=horizon,
                                 detail_level=detail_level, save_analysis=save_analysis)


@mcp.tool()
def get_data_coverage() -> dict:
    """大阪微型日經各 factor 資料覆蓋摘要（LIVE_VERIFIED/CONTRACT_ONLY/NEEDS_CONFIG/...）。不得隱藏缺口。"""
    from market_ai_hub.targets.coverage import LiveCoverageAuditor, LIVE_VERIFIED

    overrides = {
        "Micro settlement": {"status": LIVE_VERIFIED, "source": "JPX settlement CSV"},
        "VIX": {"status": LIVE_VERIFIED, "source": "Cboe official"},
        "CPI": {"status": LIVE_VERIFIED, "source": "BLS API v2"},
        "NFP": {"status": LIVE_VERIFIED, "source": "BLS API v2"},
    }
    recs = LiveCoverageAuditor().audit_osaka(overrides)
    return {"factors": [r.model_dump() for r in recs],
            "summary": LiveCoverageAuditor().summary([r for r in recs])}


@mcp.tool()
def get_event_calendar(days: int = 14, top_n: int = 10) -> dict:
    """近期重要官方事件日曆（BOJ/Fed/CPI/NFP/PCE/GDP/MOF），只回 Top-N。"""
    from market_ai_hub.packet.builder import _event_snapshot

    return {"events": _event_snapshot(top_n=top_n), "days": days}


@mcp.tool()
def get_official_release_snapshot() -> dict:
    """官方 macro 來源狀態快照（LIVE_VERIFIED / NEEDS_CONFIG / CONTRACT_ONLY）。"""
    from market_ai_hub.targets.macro import PROVIDER_STATUS

    return {"providers": PROVIDER_STATUS}


@mcp.tool()
def get_target_instrument_state() -> dict:
    """真正交易標的狀態（OSE_NIKKEI225_MICRO_FUTURES）+ Micro settlement + 角色標記。"""
    from market_ai_hub.targets.contract import TargetInstrumentContract, role_of
    from market_ai_hub.packet.builder import _load_latest_micro_settlement

    contract = TargetInstrumentContract()
    micro = _load_latest_micro_settlement()
    return {
        "contract": contract.model_dump(),
        "latest_micro_settlement": micro,
        "roles": {
            "OSE_NIKKEI225_MICRO_FUTURES": role_of("OSE_NIKKEI225_MICRO_FUTURES"),
            "^N225": role_of("^N225"),
            "NIKKEI_SPOT": role_of("NIKKEI_SPOT"),
        },
        "note": "^N225 為 PROXY，非 Micro 成交價",
    }


@mcp.tool()
def get_model_leaderboard(target: str = "", horizon: str = "") -> dict:
    """模型 leaderboard（§10）：target / dataset_semantics / sample_n / evidence_layer 分層。

    ^N225 n=4 與 Direct Micro substantial OOS 不得混成單一 headline ranking；
    n < MIN_SAMPLE → INSUFFICIENT_SAMPLE（不得標 stable/best validated/winner）。"""
    from market_ai_hub.research.tournament.performance_store import PerformanceStore
    from market_ai_hub.services.research_truth import mase_wording

    rows = PerformanceStore().leaderboard(target=target or None, horizon=horizon or None)
    MIN_SAMPLE = 30
    scoped = []
    for r in rows:
        n = r.get("sample_size") or 0
        mase = r.get("mase")
        scoped.append({
            "model": r.get("model"),
            "target": r.get("target"),
            "dataset_semantics": (
                "PROXY_INDEX" if r.get("target") == "^N225" else "DIRECT_MICRO_CONTINUOUS"
                if "micro" in str(r.get("target", "")).lower() or "nikkei" in str(r.get("target", "")).lower()
                else "UNSPECIFIED"
            ),
            "sample_n": n,
            "evidence_layer": "HISTORICAL_OOS",
            "sample_status": "INSUFFICIENT_SAMPLE" if n < MIN_SAMPLE else "OK",
            "mase": mase,
            "mase_wording": mase_wording(mase),
            "direction_accuracy": r.get("direction_accuracy"),
            "balanced_accuracy": r.get("balanced_accuracy"),
            "mcc": r.get("mcc"),
            "horizon": r.get("horizon"),
        })
    return {
        "records": scoped,
        "note": (
            "target/dataset 分層；n < MIN_SAMPLE 標 INSUFFICIENT_SAMPLE，"
            "不宣稱 stable/best validated/winner；MASE≈1 = baseline-level error，非 random guessing"
        ),
    }


@mcp.tool()
def get_forward_test_status() -> dict:
    """Forward test 統一計數（§14）：registry_records_total / model_forecast_records /
    baseline_records / pending_records / settled_model_forecasts / settled_baselines /
    forward_evidence_n / task_breakdown。所有 packet 引用同一來源。"""
    from market_ai_hub.research.registry import PredictionRegistry

    reg = PredictionRegistry()
    summary = reg.forward_summary()
    summary["note"] = "forward paper 累積中；forward_evidence_n = settled model forecasts（非 registered/pending）"
    return summary


@mcp.tool()
def get_analysis_archive_status() -> dict:
    """Analysis Archive 狀態（不可變分析 / append-only outcome / reanalysis）。"""
    from market_ai_hub.automation.archive import AnalysisArchive

    a = AnalysisArchive()
    unsettled = a.unsettled_ids()
    return {
        "unsettled_count": len(unsettled),
        "unsettled_ids": unsettled[:20],
        "note": "archive 不可變；outcome append-only；reanalysis 以 supersedes 記錄",
    }


def main_sync() -> None:
    import asyncio

    asyncio.run(mcp.run_stdio_async())


if __name__ == "__main__":
    main_sync()
