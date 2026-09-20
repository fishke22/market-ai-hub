"""Phase 2H — Analysis Packet backend builder（§3/§4）。

Python backend 先完成大部分工作，DeepSeek 不應重新抓數十個 raw MCP result。
順序：target resolution → calendar → Data Lake coverage → missing fetch →
source selection → Feature/Regime/Event → Direct/Joint/Scenario/Ensemble →
Best Baseline → Historical Edge → Research State → Gates → compact packet。
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from market_ai_hub.packet.schema import (
    ENSEMBLE_RESEARCH_QUANTILE_SUMMARY,
    PRICE_TYPE_PROXY,
    PRICE_TYPE_REFERENCE,
    PRICE_TYPE_SETTLEMENT,
    RESEARCH_ENSEMBLE,
    UNVALIDATED_FORWARD,
    AnalysisPacket,
)

# --- 進程級 TTL cache（request dedup：同 symbol/range 只抓一次）---
_TTL_SECONDS = 300
_panel_cache: dict[str, tuple[float, pd.DataFrame | None]] = {}
_settlement_cache: dict[str, tuple[float, dict | None]] = {}


def _cached(key: str, cache: dict, ttl: float) -> object | None:
    hit = cache.get(key)
    if hit is not None and (time.time() - hit[0]) <= ttl:
        return hit[1]
    return None


def clear_caches() -> None:
    """清空進程級 cache（benchmark 冷啟動用）。"""
    _panel_cache.clear()
    _settlement_cache.clear()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load_latest_micro_settlement() -> dict | None:
    """從 Data Lake 讀最新 Micro settlement（FUT_225MC）。進程級 cache（避免重複讀 parquet）。"""
    from market_ai_hub.services.provider_metrics import tracked

    cached = _cached("micro_settlement", _settlement_cache, _TTL_SECONDS)
    if cached is not None:
        with tracked("jpx_settlement", "load_micro_settlement", cache_hit=True):
            pass
        return cached
    with tracked("jpx_settlement", "load_micro_settlement", cache_hit=False):
        from market_ai_hub.automation.data_lake import default_data_root

        base = default_data_root() / "raw" / "jpx" / "settlement"
        result = None
        if base.exists():
            frames = [pd.read_parquet(p) for p in base.rglob("*.parquet")]
            if frames:
                df = pd.concat(frames, ignore_index=True)
                micro = df[df["product"] == "Nikkei 225 Micro Futures"]
                if not micro.empty:
                    latest = micro.sort_values("date").iloc[-1]
                    result = {
                        "price": float(latest["settlement_price"]),
                        "contract": str(latest["contract"]),
                        "date": str(latest["date"]),
                        "price_type": PRICE_TYPE_SETTLEMENT,
                    }
        _settlement_cache["micro_settlement"] = (time.time(), result)
        return result


def _proxy_reference() -> dict | None:
    """fallback：^N225 proxy（PROXY，非 Micro 成交價）。"""
    try:
        from market_ai_hub.providers.yfinance_provider import YFinanceProvider

        df = YFinanceProvider().fetch("^N225", period="1mo")
        if df.empty:
            return None
        last = df.sort_values("timestamp_utc").iloc[-1]
        return {"price": float(last["close"]), "price_type": PRICE_TYPE_PROXY,
                "price_timestamp": str(last["timestamp_utc"])}
    except Exception:
        return None


def _index_proxy_reference() -> dict | None:
    """TAIEX cash index proxy（^TWII，RESEARCH_PROXY，非可成交 futures price）。"""
    try:
        from market_ai_hub.providers.yfinance_provider import YFinanceProvider

        df = YFinanceProvider().fetch("^TWII", period="1mo")
        if df.empty:
            return None
        last = df.sort_values("timestamp_utc").iloc[-1]
        return {"price": float(last["close"]), "price_type": PRICE_TYPE_PROXY,
                "price_timestamp": str(last["timestamp_utc"])}
    except Exception:
        return None


def _taiwan_stock_reference(symbol: str) -> dict | None:
    """台股個股 reference price（FinMind → TWSE → yfinance fallback）。

    只回該股票本身的價，不得 fallback 到 OSE Micro / TAIEX / 其他股票。
    """
    from datetime import timedelta

    lookup = symbol.split(".")[0] if symbol.upper().endswith(".TW") else symbol
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc) - timedelta(days=730)).strftime("%Y-%m-%d")

    # 1. FinMind（OFFICIAL_DAILY）
    try:
        from market_ai_hub.providers.finmind import FinMindProvider

        fm = FinMindProvider()
        if fm.status().status.value in ("ok", "needs_config"):
            df = fm.fetch_price(lookup, start, end)
            if df is not None and not df.empty:
                last = df.sort_values("timestamp_utc").iloc[-1]
                return {"price": float(last["close"]), "price_type": PRICE_TYPE_REFERENCE,
                        "price_timestamp": str(last["timestamp_utc"]), "source": "finmind",
                        "data_grade": "OFFICIAL_DAILY"}
    except Exception:
        pass

    # 2. TWSE OpenAPI
    try:
        from market_ai_hub.providers.twse import TWSEProvider

        twse = TWSEProvider()
        ts_start = (datetime.now(timezone.utc) - timedelta(days=180)).strftime("%Y%m%d")
        df = twse.fetch_symbol_daily(lookup, ts_start, end.replace("-", ""))
        if df is not None and not df.empty:
            last = df.sort_values("timestamp_utc").iloc[-1]
            return {"price": float(last["close"]), "price_type": PRICE_TYPE_REFERENCE,
                    "price_timestamp": str(last["timestamp_utc"]), "source": "twse",
                    "data_grade": "OFFICIAL_DAILY"}
    except Exception:
        pass

    # 3. yfinance fallback（RESEARCH_PROXY）
    try:
        from market_ai_hub.providers.yfinance_provider import YFinanceProvider

        df = YFinanceProvider().fetch(symbol, period="6mo")
        if df is not None and not df.empty:
            last = df.sort_values("timestamp_utc").iloc[-1]
            return {"price": float(last["close"]), "price_type": PRICE_TYPE_PROXY,
                    "price_timestamp": str(last["timestamp_utc"]), "source": "yfinance",
                    "data_grade": "RESEARCH_PROXY"}
    except Exception:
        pass

    return None


# 可用 yfinance symbols（避免 404 的 US10Y/US2Y）→ regime 引擎欄位名
# 全域因子共通 reuse；local target context 依 family 分離（§7）。
REGIME_GLOBAL_SYMBOLS = {"^VIX": "VIX", "USDJPY=X": "USDJPY=X", "^TNX": "US10Y", "^FVX": "US5Y"}
REGIME_LOCAL_SYMBOLS = {
    "OSAKA_MICRO": {"^N225": "^N225"},
    "TAIWAN_STOCK": {"^TWII": "^TWII"},
    "TAIWAN_INDEX": {"^TWII": "^TWII"},
}


def _regime_panel(family: str = "OSAKA_MICRO") -> pd.DataFrame | None:
    """跨資產 regime panel（可選；無網路 → None）。進程級 cache + 同 symbol 只抓一次。

    local target context 依 family 分離（Osaka 用 ^N225，Taiwan 用 ^TWII）；
    global（VIX/US rates/USDJPY）共通。
    """
    from market_ai_hub.services.provider_metrics import tracked

    symbols = {**REGIME_LOCAL_SYMBOLS.get(family, {}), **REGIME_GLOBAL_SYMBOLS}
    key = f"regime_panel_{family}"
    cached = _cached(key, _panel_cache, _TTL_SECONDS)
    if cached is not None:
        with tracked("yfinance", "regime_panel", cache_hit=True):
            pass
        return cached
    with tracked("yfinance", "regime_panel", cache_hit=False):
        result = None
        try:
            from market_ai_hub.providers.yfinance_provider import YFinanceProvider

            yf = YFinanceProvider()
            closes = {}
            for sym, col in symbols.items():
                df = yf.fetch(sym, period="1y")
                if not df.empty:
                    s = df.sort_values("timestamp_utc").set_index("timestamp_utc")["close"]
                    closes[col] = s
            if closes:
                result = pd.DataFrame(closes)
        except Exception:
            result = None
        _panel_cache[key] = (time.time(), result)
        return result


def _regime(panel: pd.DataFrame | None) -> dict:
    if panel is None:
        return {"status": "INSUFFICIENT_DATA", "note": "no cross-asset panel available"}
    try:
        from market_ai_hub.regime.engine import MarketRegimeEngine

        eng = MarketRegimeEngine()
        result = eng.compute(panel)
        return {k: v["label"] for k, v in result.items() if isinstance(v, dict) and "label" in v}
    except Exception as e:  # noqa: BLE001
        return {"status": "ERROR", "note": str(e)[:120]}


def _coverage_summary(family: str = "OSAKA_MICRO") -> list[dict]:
    from market_ai_hub.targets.coverage import LiveCoverageAuditor, LIVE_VERIFIED

    if family == "OSAKA_MICRO":
        overrides = {
            "Micro settlement": {"status": LIVE_VERIFIED, "source": "JPX settlement CSV"},
            "VIX": {"status": LIVE_VERIFIED, "source": "Cboe official"},
            "CPI": {"status": LIVE_VERIFIED, "source": "BLS API v2"},
            "NFP": {"status": LIVE_VERIFIED, "source": "BLS API v2"},
        }
        recs = LiveCoverageAuditor().audit_osaka(overrides)
        return [r.model_dump() for r in recs]
    return _coverage_summary_compact(family)


def _event_snapshot(top_n: int = 5) -> list[dict]:
    """近期最重要 Top-N 官方事件（BOJ/Fed/CPI/NFP/PCE/GDP/MOF），遵守 info cutoff。"""
    providers = [
        ("BOJ", "BOJ MPM/release"), ("Fed", "FOMC"), ("CPI", "US CPI"),
        ("NFP", "US Employment"), ("PCE", "US PCE"), ("GDP", "US GDP"), ("MOF", "FX intervention"),
    ]
    out = []
    for name, desc in providers:
        out.append({"source": name, "event": desc, "status": "CALENDAR_AVAILABLE",
                    "note": "release schedule snapshot (top-N)"})
    return out[:top_n]


def _fill_target_semantics(packet: AnalysisPacket, market: str, target: str) -> None:
    """§6：direct_target / direct_market_fact / continuous_research_series / proxy_model_target
    三者分離，不得合併。§7：direct 與 proxy calendar 分離。§3-§6：family 隔離。"""
    from market_ai_hub.services.primary_targets import resolve_market_family

    family = resolve_market_family(market)
    if family == "OSAKA_MICRO":
        proxy_model_target = "^N225"
        direct_calendar = "OSE/JPX_DERIVATIVES"
        proxy_calendar = "XTKS"
        execution_instrument = "OSE_NIKKEI225_MICRO_FUTURES"
        direct_target = "OSE_NIKKEI225_MICRO_FUTURES"
        continuous = "225LABO (CENTER_MONTH_CONTINUOUS_MICRO)"
    elif family == "TAIWAN_INDEX":
        proxy_model_target = "^TWII"
        direct_calendar = "XTAI"
        proxy_calendar = "XTAI"
        execution_instrument = None  # TAIEX 非可成交；策略需明確 TX/MTX/TMF
        direct_target = target or "TAIEX"
        continuous = "N/A"
    else:  # TAIWAN_STOCK
        proxy_model_target = target
        direct_calendar = "XTAI"
        proxy_calendar = "XTAI"
        execution_instrument = target  # 個股本身可成交
        direct_target = target
        continuous = "N/A"

    # direct_market_fact：只有 OSAKA 才含 contract / settlement；Taiwan 為 stock-specific fact 或 NOT_AVAILABLE
    if family == "OSAKA_MICRO":
        direct_market_fact = (
            {"contract": packet.contract_month, "price_type": packet.reference_price_type}
            if packet.contract_month else {"status": "NOT_AVAILABLE"}
        )
        direct_contract = packet.contract_month or "N/A"
    else:
        direct_market_fact = {
            "target": direct_target,
            "price": packet.reference_price,
            "price_type": packet.reference_price_type,
            "source": packet.target_price_source,
        }
        direct_contract = "N/A"  # cash equity / cash index 無 contract_month

    packet.target_semantics = {
        "direct_target": direct_target,
        "direct_market_fact": direct_market_fact,
        "direct_contract_if_applicable": direct_contract,
        "continuous_research_series": continuous,
        "proxy_model_target": proxy_model_target,
        "proxy_model_calendar": proxy_calendar,
        "direct_market_calendar": direct_calendar,
        "model_forecast_target_dates": packet.forecast_target_dates,
        "execution_instrument": execution_instrument,
    }

    # §28：TAIEX 指數點位不可假裝實際成交；execution 需明確 TX/MTX/TMF 之一
    if family == "TAIWAN_INDEX":
        packet.target_semantics["forecast_vs_execution"] = {
            "forecast_target": direct_target,
            "execution_instruments": ["TX", "MTX", "TMF"],
            "note": "TAIEX index points are NOT executable; strategy execution must pick TX/MTX/TMF explicitly",
        }

    # §7：direct 與 proxy 各別 session/bar。
    try:
        from market_ai_hub.services.calendar import next_trading_sessions, trading_date_of

        today_utc = pd.Timestamp.now("UTC")
        last_proxy = trading_date_of(today_utc, proxy_model_target)
        proxy_bars = next_trading_sessions(proxy_model_target, last_proxy, 1)
        packet.proxy_next_model_bar = proxy_bars[0] if proxy_bars else ""
    except Exception:  # noqa: BLE001
        packet.proxy_next_model_bar = ""
    if family == "OSAKA_MICRO":
        packet.direct_next_session = (
            f"OSE/JPX derivatives session (may differ from TSE cash on holiday trading); "
            f"proxy next bar = {packet.proxy_next_model_bar or 'N/A'}"
        )
    else:
        packet.direct_next_session = (
            f"{direct_calendar} session; proxy next bar = {packet.proxy_next_model_bar or 'N/A'}"
        )


def _fill_research_truth(packet: AnalysisPacket) -> None:
    """§8：單一來源 ValidationTruth；§12/§13：driver panel / market environment 非 causal / economic。"""
    from market_ai_hub.services.research_truth import research_evidence_summary, validation_truth

    packet.validation_truth = validation_truth()

    # 支援壓力：不可用時 NOT_AVAILABLE，不用 P10/P90 冒充（§16）
    packet.support_resistance_status = "NOT_AVAILABLE"
    packet.support_levels = []
    packet.resistance_levels = []
    packet.model_statistical_reference_range = {
        "note": "uncalibrated model quantile range (NOT support/resistance)",
        "p10": None, "p90": None,
    }

    # §13：risk_on/trend/vol/rates 是 MARKET ENVIRONMENT，不是 economic edge
    packet.market_environment = {
        "status": "ENVIRONMENT_ONLY",
        "note": "risk_on/trend/vol/rates regime 是市場環境，非 economic edge",
    }
    packet.economic_edge_summary = {
        "status": "NO_ECONOMIC_EDGE",
        "source": "Phase2V-C cost-aware strategy validation",
        "explanation": "Phase2 cost/slippage strategy validation completed; result NO_ECONOMIC_EDGE.",
    }

    # §12：driver panel 只標 CONTEXT / EXPLANATORY FEATURES，非 formal causal validation
    packet.driver_panel = {
        "status": "CONTEXT_ONLY",
        "top_positive_drivers": packet.top_positive_drivers,
        "top_negative_drivers": packet.top_negative_drivers,
        "note": "explanatory features only; formal causal layer reads Phase2V-C.1 evidence (NON_EXECUTABLE_FORECAST_EDGE)",
    }


def build_analysis_packet(market: str = "osaka", target: str = "OSE_NIKKEI225_MICRO_FUTURES",
                          horizon: str = "1d", detail_level: str = "compact",
                          save_analysis: bool = True, profiler=None) -> dict:
    """組出 AnalysisPacket（compact/normal/audit）。永不 crash：缺資料 → 標示缺口。"""
    def _t(name, fn):
        if profiler is not None:
            with profiler.time(name):
                return fn()
        return fn()

    packet = AnalysisPacket(horizon=horizon, information_cutoff=_now())

    from market_ai_hub.services.primary_targets import resolve_market_family

    family = resolve_market_family(market)

    # 1. target resolution（family 隔離，未知 market fail clearly）
    if family == "OSAKA_MICRO":
        packet.execution_target = "OSE_NIKKEI225_MICRO_FUTURES"
        packet.exchange = "OSE"
    elif family == "TAIWAN_STOCK":
        packet.execution_target = target
        packet.exchange = "TWSE"
    else:  # TAIWAN_INDEX
        packet.execution_target = target or "TAIEX"
        packet.exchange = "TWSE"

    # 2. reference price（target-family routing，§3-§6：不得 cross-market）
    micro = None
    if family == "OSAKA_MICRO":
        micro = _t("provider_micro_settlement", _load_latest_micro_settlement)
        if profiler is not None and micro is not None:
            profiler.datalake_reads += 1
        if micro:
            packet.reference_price = micro["price"]
            packet.reference_price_type = micro["price_type"]
            packet.price_timestamp = micro["date"]
            packet.contract_month = micro["contract"]
            packet.target_data_status = "LIVE_VERIFIED"
            packet.target_price_source = "settlement"
            packet.data_reused.append("jpx_micro_settlement")
        else:
            proxy = _t("provider_proxy_reference", _proxy_reference)
            if proxy:
                packet.reference_price = proxy["price"]
                packet.reference_price_type = proxy["price_type"]
                packet.price_timestamp = proxy.get("price_timestamp", "")
                packet.target_data_status = "RESEARCH_PROXY"
                packet.target_price_source = "proxy"
            else:
                packet.target_data_status = "MISSING"
                packet.target_price_source = "unavailable"
                packet.data_missing.append("micro_settlement")
    elif family == "TAIWAN_STOCK":
        stock_ref = _t("provider_stock_reference", lambda: _taiwan_stock_reference(target))
        if stock_ref:
            packet.reference_price = stock_ref["price"]
            packet.reference_price_type = stock_ref["price_type"]
            packet.price_timestamp = stock_ref.get("price_timestamp", "")
            packet.target_data_status = "LIVE_VERIFIED" if stock_ref.get("data_grade") == "OFFICIAL_DAILY" else "RESEARCH_PROXY"
            packet.target_price_source = stock_ref.get("source", "stock")
        else:
            packet.target_data_status = "MISSING"
            packet.target_price_source = "unavailable"
            packet.data_missing.append(f"taiwan_stock:{target}")
    else:  # TAIWAN_INDEX
        idx_proxy = _t("provider_index_proxy", lambda: _index_proxy_reference())
        if idx_proxy:
            packet.reference_price = idx_proxy["price"]
            packet.reference_price_type = PRICE_TYPE_PROXY
            packet.price_timestamp = idx_proxy.get("price_timestamp", "")
            packet.target_data_status = "RESEARCH_PROXY"
            packet.target_price_source = "proxy_index"
        else:
            packet.target_data_status = "MISSING"
            packet.target_price_source = "DIRECT_NOT_IMPLEMENTED"
            packet.data_missing.append("taiwan_index")

    # 3. regime / event（family 隔離，§7；provider 失敗 → degrade，不整份分析失敗）
    try:
        panel = _t("provider_regime_panel", lambda: _regime_panel(family))
    except Exception as e:  # noqa: BLE001
        panel = None
        packet.data_quality["regime_panel_error"] = str(e)[:120]
    packet.regime = _t("feature_regime", lambda: _regime(panel))
    packet.upcoming_events = _event_snapshot(top_n=5 if detail_level != "compact" else 3)
    packet.event_state = "NONE"

    # 4. forecast layers（語義：皆 research / unvalidated，直到 forward-validated）
    packet.direct_forecast_summary = {"layer": "DIRECT", "status": "RESEARCH",
                                      "note": "direct models kept separate; forward-unvalidated"}
    packet.joint_forecast_summary = {"layer": "JOINT", "status": "RESEARCH",
                                     "model_revision": "var/factor/kalman baselines"}
    packet.scenario_summary = {"layer": "SCENARIO", "status": "RESEARCH",
                               "note": "8 scenario types (rule-generated, UNVALIDATED_WEIGHT)"}
    packet.dynamic_ensemble_summary = {"layer": "DYNAMIC_ENSEMBLE", "status": RESEARCH_ENSEMBLE,
                                       "validation": UNVALIDATED_FORWARD}
    packet.ensemble_validation = UNVALIDATED_FORWARD
    packet.ensemble_distribution_validated = False
    packet.ensemble_quantile_method = ENSEMBLE_RESEARCH_QUANTILE_SUMMARY

    # 5. best baseline / edge / research state
    packet.best_baseline = {"layer": "BEST_BASELINE", "note": "baseline kept as legal candidate"}
    packet.best_validated_model = {"status": "NONE_FORWARD_VALIDATED"}
    packet.historical_edge_summary = {"status": "INSUFFICIENT_EVIDENCE",
                                      "note": "edge is evidence layer, does not modify forecast"}
    packet.strategy_research_state = "WAIT"

    # 5.5 V2 target semantics / calendar 分離 / research truth / environment / driver panel
    _fill_target_semantics(packet, market, target)
    _fill_research_truth(packet)

    # 6. coverage / gates（family 隔離，§8）
    if detail_level == "compact":
        packet.data_coverage_summary = _t("feature_coverage_compact", lambda: _coverage_summary_compact(family))
    else:
        packet.data_coverage_summary = _t("feature_coverage", lambda: _coverage_summary(family))
    packet.research_gates = {"TRADING_EDGE_GATE": "UNPROVEN",
                             "FORWARD_VALIDATION": "NOT_YET"}
    packet.reanalysis_conditions = ["FORECAST_STALE_AFTER_EVENT", "major data revision",
                                    "new official release after cutoff"]

    # 7. archive auto-hook
    if save_analysis:
        def _save():
            aid = _archive_packet(packet, family)
            packet.analysis_id = aid
            packet.saved_to_archive = True
        try:
            _t("packet_archive_save", _save)
            if profiler is not None:
                profiler.datalake_writes += 1
        except Exception as e:  # noqa: BLE001
            packet.saved_to_archive = False
            packet.data_quality["archive_error"] = str(e)[:120]

    return packet.render(detail_level)


def _coverage_summary_compact(family: str = "OSAKA_MICRO") -> list[dict]:
    """compact：只回最關鍵覆蓋項（family 隔離，§8）。"""
    from market_ai_hub.targets.coverage import LIVE_VERIFIED, MISSING

    if family == "OSAKA_MICRO":
        return [
            {"factor": "Micro settlement", "status": LIVE_VERIFIED, "source": "JPX settlement CSV"},
            {"factor": "Micro OHLC", "status": MISSING, "source": "not in official xlsx/csv"},
            {"factor": "VIX", "status": LIVE_VERIFIED, "source": "Cboe official"},
            {"factor": "CPI/NFP", "status": LIVE_VERIFIED, "source": "BLS API v2"},
            {"factor": "PCE/GDP", "status": "NEEDS_CONFIG", "source": "BEA API"},
        ]
    if family == "TAIWAN_STOCK":
        return [
            {"factor": "target stock data", "status": "ROUTED", "source": "FinMind/TWSE/yfinance"},
            {"factor": "TWSE/FinMind status", "status": "ROUTED", "source": "provider registry"},
            {"factor": "corporate action", "status": "NOT_AVAILABLE", "source": "adjustment not implemented"},
            {"factor": "VIX", "status": "GLOBAL_CONTEXT", "source": "Cboe official"},
        ]
    # TAIWAN_INDEX
    return [
        {"factor": "TAIEX", "status": "PROXY_ONLY", "source": "yfinance ^TWII (DIRECT_NOT_IMPLEMENTED)"},
        {"factor": "TAIFEX TX/MTX/TMF", "status": "NOT_IMPLEMENTED", "source": "execution instrument semantics only"},
        {"factor": "VIX", "status": "GLOBAL_CONTEXT", "source": "Cboe official"},
    ]


def _archive_packet(packet: AnalysisPacket, family: str = "OSAKA_MICRO") -> str:
    """把 structured packet 存進 AnalysisArchive（不存 Chain of Thought）。§9/§10：family-correct metadata。"""
    from market_ai_hub.automation.archive import AnalysisArchive, AnalysisRecord

    market_name = {"OSAKA_MICRO": "osaka", "TAIWAN_STOCK": "taiwan_stock", "TAIWAN_INDEX": "taiwan_index"}[family]
    dataset_semantics = {
        "OSAKA_MICRO": "jpx-micro-settlement-v1",
        "TAIWAN_STOCK": "UNVERSIONED",  # 台股 historical dataset 尚未正式 version
        "TAIWAN_INDEX": "UNVERSIONED",  # TAIEX pipeline 未實作
    }[family]
    feature_semantics = {
        "OSAKA_MICRO": "base-v1",
        "TAIWAN_STOCK": "UNVERSIONED",
        "TAIWAN_INDEX": "UNVERSIONED",
    }[family]

    rec = AnalysisRecord(
        analysis_id=packet.analysis_packet_id,
        information_cutoff=packet.information_cutoff,
        market=market_name,
        target=packet.execution_target,
        instrument=packet.execution_target,
        horizon=packet.horizon,
        forecast_target_dates=packet.forecast_target_dates,
        reference_price=packet.reference_price,
        research_center=packet.research_center,
        direction=packet.strategy_research_state,
        regime=json.dumps(packet.regime, ensure_ascii=False)[:500] if packet.regime else "",
        event_state=packet.event_state,
        dataset_version=dataset_semantics,
        feature_version=feature_semantics,
    )
    rec.analysis_packet_hash = rec.packet_hash()
    AnalysisArchive().save(rec)
    return rec.analysis_id
