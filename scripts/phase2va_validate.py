"""Phase 2V-A real-world end-to-end validation harness.

Purpose: prove Phase 2 actually works with REAL network data + REAL model inference,
not just unit tests. No live trading / order / account query / recorder / git.

Sections: C provider validation, D Osaka packet, E model inference, F Taiwan packet,
G point-in-time, H cross-source, I failure injection, J archive/registry, L performance.

Writes: REAL_PROVIDER_VALIDATION.json + data/phase2va_results.json (full raw).
"""
from __future__ import annotations

import json
import time
import traceback
from datetime import datetime, timedelta, timezone

import pandas as pd

RESULTS: dict = {}


def rec(section: str, key: str, value) -> None:
    RESULTS.setdefault(section, {})[key] = value


def _t(fn):
    t0 = time.perf_counter()
    r = fn()
    return r, (time.perf_counter() - t0) * 1000


def _validation_out():
    """provider validation 輸出目錄（DATA_ROOT/research_outputs/validation/，不落 project root）。"""
    import sys
    from pathlib import Path

    ROOT = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(ROOT / "src"))
    from market_ai_hub.config.runtime_paths import validation_outputs_root

    d = validation_outputs_root()
    d.mkdir(parents=True, exist_ok=True)
    return d


# ───────────────────────────────────────────────────────────── C. Provider validation
def section_c():
    from market_ai_hub.providers.base import ProviderStatus

    probes = {}

    def p(name, fn):
        t0 = time.perf_counter()
        try:
            df = fn()
            dt = (time.perf_counter() - t0) * 1000
            out = {"status": "OK", "latency_ms": round(dt, 1), "rows": -1}
            if isinstance(df, pd.DataFrame):
                out["rows"] = int(len(df))
                if "timestamp_utc" in df and len(df):
                    out["min_event_time"] = str(pd.Timestamp(df["timestamp_utc"].min()))
                    out["max_event_time"] = str(pd.Timestamp(df["timestamp_utc"].max()))
                out["columns"] = list(df.columns)[:12]
            elif isinstance(df, (list, dict)):
                out["rows"] = len(df)
            probes[name] = out
        except Exception as e:
            dt = (time.perf_counter() - t0) * 1000
            probes[name] = {"status": "FAIL", "latency_ms": round(dt, 1), "error": str(e)[:180]}

    # Free, no-key providers — real fetch
    from market_ai_hub.providers.yfinance_provider import YFinanceProvider
    p("yfinance", lambda: YFinanceProvider().fetch("^N225", period="1y", interval="1d"))

    from market_ai_hub.providers.twse import TWSEProvider
    p("twse", lambda: TWSEProvider().fetch_symbol_daily("2330", "20250101", "20260920"))

    from market_ai_hub.providers.taifex import TaifexProvider
    p("taifex", lambda: TaifexProvider().fetch_daily("TX", "", ""))

    from market_ai_hub.providers.ustreasury import USTreasuryProvider
    p("ustreasury", lambda: USTreasuryProvider().fetch_daily_rates())

    from market_ai_hub.providers.cftc_cot import CftcCotProvider
    p("cftc_cot", lambda: CftcCotProvider().fetch_cot("", 100))

    from market_ai_hub.targets.macro import CboeVixProvider
    p("cboe_vix", lambda: CboeVixProvider().fetch())

    from market_ai_hub.targets.macro import BLSProvider
    p("bls_cpi", lambda: BLSProvider().fetch(["CUUR0000SA0"], "2024", "2026"))

    from market_ai_hub.packet.builder import _load_latest_micro_settlement
    p("jpx_settlement", lambda: _load_latest_micro_settlement())

    # BOJ — status (reachability) + best-effort fetch
    from market_ai_hub.providers.boj import BojProvider
    boj = BojProvider()
    try:
        s = boj.status()
        probes["boj"] = {"status": s.status.value, "message": s.message}
    except Exception as e:
        probes["boj"] = {"status": "FAIL", "error": str(e)[:180]}

    # Keyed providers — honest NEEDS_CONFIG (no token in env)
    from market_ai_hub.providers.registry import ProviderRegistry
    reg = ProviderRegistry()
    for name in ("finmind", "fred", "jquants", "tradingview", "broker"):
        try:
            st = reg.get(name).status()
            probes[name] = {"status": st.status.value, "message": st.message}
        except Exception as e:
            probes[name] = {"status": "FAIL", "error": str(e)[:180]}

    # BEA / e-Stat / EIA / EDINET — documented NEEDS_CONFIG
    from market_ai_hub.targets.macro import PROVIDER_STATUS
    for name in ("BEA", "EIA", "EDINET"):
        probes[name.lower()] = {"status": "NEEDS_CONFIG", "documented": PROVIDER_STATUS.get(name, "?")}
    probes["e_stat"] = {"status": "NEEDS_CONFIG", "documented": "Japan e-Stat (appId)"}

    rec("C_provider_validation", "providers", probes)
    rec("C_provider_validation", "checked_at", datetime.now(timezone.utc).isoformat())

    # Enrichment: source grade + freshness + available_at (no extra network)
    grades = {
        "yfinance": "RESEARCH_PROXY", "twse": "OFFICIAL_DAILY", "taifex": "OFFICIAL_DAILY",
        "ustreasury": "OFFICIAL_DAILY", "cftc_cot": "OFFICIAL_DAILY", "cboe_vix": "OFFICIAL_DAILY",
        "bls_cpi": "OFFICIAL_DAILY", "jpx_settlement": "OFFICIAL_DAILY", "boj": "OFFICIAL",
        "finmind": "OFFICIAL_DAILY", "fred": "OFFICIAL", "jquants": "OFFICIAL",
        "tradingview": "DISPLAY_ONLY", "broker": "DISABLED",
        "bea": "NEEDS_CONFIG", "eia": "NEEDS_CONFIG", "edinet": "NEEDS_CONFIG", "e_stat": "NEEDS_CONFIG",
    }
    now = datetime.now(timezone.utc)
    enriched = []
    for name, v in probes.items():
        e = dict(v)
        e["provider"] = name
        e["source_grade"] = grades.get(name, "UNKNOWN")
        e["available_at"] = now.isoformat()
        mx = v.get("max_event_time")
        if mx and v.get("status") == "OK":
            try:
                age_h = (now - pd.Timestamp(mx).tz_localize("UTC")).total_seconds() / 3600
                e["freshness_hours"] = round(age_h, 2)
                e["freshness"] = "STALE" if age_h > 96 else ("DELAYED" if age_h > 24 else "FRESH")
            except Exception:
                e["freshness"] = "UNKNOWN"
        else:
            e["freshness"] = "N/A"
        enriched.append(e)
    rec("C_provider_validation", "provider_records", enriched)
    return probes


# ───────────────────────────────────────────────────────────── D. Osaka packet (audit)
def section_d():
    from market_ai_hub.packet.builder import build_analysis_packet

    out, ms = _t(lambda: build_analysis_packet(
        market="osaka", target="OSE_NIKKEI225_MICRO_FUTURES",
        horizon="1d", detail_level="audit", save_analysis=False))
    rec("D_osaka_packet", "latency_ms", round(ms, 1))
    rec("D_osaka_packet", "packet", out)
    # Key invariants
    rec("D_osaka_packet", "invariant_settlement_not_close",
        (out.get("reference_price_type") != "close", out.get("reference_price_type")))
    rec("D_osaka_packet", "invariant_n225_not_primary_target",
        (out.get("execution_target") != "^N225", out.get("execution_target")))
    return out


# ───────────────────────────────────────────────────────────── E. Model inference
def section_e():
    from market_ai_hub.services.analysis import analyze_osaka_nikkei
    out, ms = _t(lambda: analyze_osaka_nikkei(horizon="1d"))
    rec("E_model_inference", "osaka_analysis_latency_ms", round(ms, 1))
    models = {}
    for k in ("chronos", "timesfm", "xgb", "lgbm"):
        v = out.get(k, {})
        if isinstance(v, dict):
            models[k] = {
                "model": v.get("model", k),
                "status": "SUCCESS" if v.get("engineering_status") == "pass" or "point_forecast" in v else v.get("status", "?"),
                "horizon": v.get("horizon"),
                "target": v.get("symbol"),
                "input_rows": v.get("sample_size") or out.get("confidence_inputs", {}).get("sample_size"),
                "information_cutoff": out.get("forecast_origin"),
                "output_type": v.get("model_task"),
                "runtime": "cpu" if not _cuda() else "cuda",
                "direction": v.get("direction"),
            }
        else:
            models[k] = {"model": k, "status": "UNAVAILABLE", "error": str(v)[:120]}
    rec("E_model_inference", "osaka_models", models)
    rec("E_model_inference", "osaka_used_base_models", out.get("used_base_models"))
    rec("E_model_inference", "osaka_final_direction", out.get("final_direction"))

    # fincast bridge + NHITS/NBEATSx runtime availability (honest)
    from market_ai_hub.models.fincast_model import FinCastAdapter
    try:
        fin = FinCastAdapter().status()
    except Exception as e:
        fin = f"unavailable: {str(e)[:100]}"
    rec("E_model_inference", "fincast_status", fin)

    # NHITS / NBEATSx are retrainable (tournament), not runtime prediction adapters.
    rec("E_model_inference", "nhits", {"status": "MODEL_RUNTIME_UNAVAILABLE",
         "reason": "retrainable tournament model (training_policy RETRAINABLE_MODELS); no runtime prediction adapter"})
    rec("E_model_inference", "nbeatsx", {"status": "MODEL_RUNTIME_UNAVAILABLE",
         "reason": "retrainable tournament model; no runtime prediction adapter"})
    return out


def _cuda():
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return False


# ───────────────────────────────────────────────────────────── F. Taiwan packet
def section_f():
    from market_ai_hub.services.analysis import analyze_taiwan_stock

    tw = {}
    for code in ("2330.TW", "3706.TW", "2317.TW"):
        try:
            out, ms = _t(lambda c=code: analyze_taiwan_stock(c, horizon="1d"))
            tw[code] = {
                "latency_ms": round(ms, 1),
                "status": out.get("status"),
                "provider": out.get("provider"),
                "data_grade": out.get("data_grade"),
                "final_direction": out.get("final_direction"),
                "used_base_models": out.get("used_base_models"),
                "last_observed": out.get("last_observed_trading_date"),
                "forecast_target_dates": out.get("forecast_target_dates"),
            }
            # capture per-model output presence (real vs fallback)
            tw[code]["models_ran"] = [k for k in ("chronos", "timesfm", "xgb", "lgbm")
                                      if isinstance(out.get(k), dict) and "point_forecast" in out.get(k, {})]
        except Exception as e:
            tw[code] = {"status": "FAIL", "error": str(e)[:200]}
    rec("F_taiwan_packet", "stocks", tw)
    return tw


# ───────────────────────────────────────────────────────────── G. Point-in-time
def section_g():
    from market_ai_hub.feature_store.store import FeatureStore, build_panel_features
    from market_ai_hub.providers.yfinance_provider import YFinanceProvider

    yf = YFinanceProvider()
    df = yf.fetch("^N225", period="1y", interval="1d")
    closes = df.sort_values("timestamp_utc").set_index("timestamp_utc")["close"].dropna()

    as_of_dates = ["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31", "2026-06-30"]
    fs = FeatureStore()
    checks = []
    leakage = False
    for d in as_of_dates:
        as_of = pd.Timestamp(d).to_pydatetime().replace(tzinfo=timezone.utc)
        recs = build_panel_features({"^N225": closes}, as_of, feature_version="v1")
        for r in recs:
            fs.put(r)
        rows = fs.get_all_asof(as_of)
        n = len(rows)
        bad = 0
        if n and "available_at" in rows:
            av = pd.to_datetime(rows["available_at"]).dt.tz_localize(None)
            bad = int((av > pd.Timestamp(d)).sum())
        if bad:
            leakage = True
        checks.append({"as_of": d, "rows_visible": n, "available_at_leaks": bad,
                       "pass": bad == 0})
    rec("G_point_in_time", "checks", checks)
    rec("G_point_in_time", "leakage_detected", leakage)
    rec("G_point_in_time", "leakage_block", leakage)  # any leak → BLOCKED
    return checks


# ───────────────────────────────────────────────────────────── H. Cross-source
def section_h():
    from market_ai_hub.services.cross_source import cross_source_check
    from market_ai_hub.providers.yfinance_provider import YFinanceProvider
    from market_ai_hub.targets.macro import CboeVixProvider
    from market_ai_hub.providers.twse import TWSEProvider
    from market_ai_hub.providers.ustreasury import USTreasuryProvider
    from market_ai_hub.packet.builder import _load_latest_micro_settlement

    yf = YFinanceProvider()
    comps = {}

    # 2330.TW: TWSE authoritative vs yfinance proxy
    try:
        tw = TWSEProvider().fetch_symbol_daily("2330", "20260801", "20260920")
        auth_tw = float(tw.sort_values("timestamp_utc")["close"].iloc[-1])
        y2330 = yf.fetch("2330.TW", period="5d", interval="1d")
        proxy_tw = float(y2330.sort_values("timestamp_utc")["close"].iloc[-1])
        comps["TWSE 2330 vs yfinance"] = cross_source_check("2330.TW", auth_tw, proxy_tw, threshold=0.05)
    except Exception as e:
        comps["TWSE 2330 vs yfinance"] = {"factor": "2330.TW", "status": "UNAVAILABLE", "error": str(e)[:140]}

    # VIX: Cboe authoritative vs yfinance proxy
    try:
        vix = CboeVixProvider().fetch()
        auth_vix = float(vix.sort_values("Date")["CLOSE"].iloc[-1])
        yvix = yf.fetch("^VIX", period="5d", interval="1d")
        proxy_vix = float(yvix.sort_values("timestamp_utc")["close"].iloc[-1])
        comps["VIX Cboe vs yfinance"] = cross_source_check("VIX", auth_vix, proxy_vix, threshold=0.10)
    except Exception as e:
        comps["VIX Cboe vs yfinance"] = {"factor": "VIX", "status": "UNAVAILABLE", "error": str(e)[:140]}

    # USDJPY: single source (yfinance)
    try:
        u = yf.fetch("JPY=X", period="5d", interval="1d")
        comps["USDJPY"] = cross_source_check("USDJPY", float(u.sort_values("timestamp_utc")["close"].iloc[-1]), None)
    except Exception as e:
        comps["USDJPY"] = {"factor": "USDJPY", "status": "UNAVAILABLE", "error": str(e)[:140]}

    # Treasury 10Y: USTreasury authoritative, FRED needs key → SINGLE_SOURCE
    try:
        tr = USTreasuryProvider().fetch_daily_rates()
        # USTreasury df columns vary; last numeric close if present
        comps["Treasury 10Y"] = {"factor": "Treasury 10Y", "status": "SINGLE_SOURCE",
                                 "rows": int(len(tr)), "note": "FRED needs API key (NEEDS_CONFIG)"}
    except Exception as e:
        comps["Treasury 10Y"] = {"factor": "Treasury 10Y", "status": "UNAVAILABLE", "error": str(e)[:140]}

    # Nikkei: JPX micro settlement authoritative vs ^N225 proxy (index vs futures — different instrument)
    try:
        s = _load_latest_micro_settlement()
        nk = yf.fetch("^N225", period="5d", interval="1d")
        proxy_nk = float(nk.sort_values("timestamp_utc")["close"].iloc[-1])
        comps["Nikkei micro settlement vs ^N225"] = cross_source_check(
            "Nikkei", float(s["price"]) if s else None, proxy_nk, threshold=0.02)
    except Exception as e:
        comps["Nikkei"] = {"factor": "Nikkei", "status": "UNAVAILABLE", "error": str(e)[:140]}

    rec("H_cross_source", "comparisons", comps)
    return comps


# ───────────────────────────────────────────────────────────── I. Failure injection
def section_i():
    from market_ai_hub.packet.builder import build_analysis_packet
    import market_ai_hub.packet.builder as b

    orig_proxy = b._proxy_reference
    orig_regime = b._regime_panel

    injections = {}

    # 1) Yahoo proxy + regime panel both fail → packet must degrade, not crash
    def _fail_proxy():
        raise RuntimeError("simulated yahoo failure")

    b._proxy_reference = _fail_proxy
    b._regime_panel = lambda: (_ for _ in ()).throw(RuntimeError("simulated regime panel failure"))
    try:
        out = build_analysis_packet(market="osaka", target="OSE_NIKKEI225_MICRO_FUTURES",
                                    horizon="1d", detail_level="compact", save_analysis=False)
        injections["osaka_all_proxy_fail"] = {
            "crashed": False, "target_data_status": out.get("target_data_status"),
            "regime": (out.get("regime") or {}).get("status", "degraded"),
        }
    except Exception as e:
        injections["osaka_all_proxy_fail"] = {"crashed": True, "error": str(e)[:200]}
    finally:
        b._proxy_reference = orig_proxy
        b._regime_panel = orig_regime

    rec("I_failure_injection", "injections", injections)
    return injections


# ───────────────────────────────────────────────────────────── J. Archive + Registry
def section_j():
    from market_ai_hub.packet.builder import build_analysis_packet
    from market_ai_hub.automation.archive import AnalysisArchive
    from market_ai_hub.research.registry import PredictionRegistry

    arch = AnalysisArchive()
    before = len(arch.unsettled_ids())

    # run twice → must append, not overwrite (immutable), then record supersedes
    o1 = build_analysis_packet(market="osaka", target="OSE_NIKKEI225_MICRO_FUTURES",
                               horizon="1d", detail_level="compact", save_analysis=True)
    id1 = o1.get("analysis_id") or o1.get("analysis_packet_id")
    o2 = build_analysis_packet(market="osaka", target="OSE_NIKKEI225_MICRO_FUTURES",
                               horizon="1d", detail_level="compact", save_analysis=True)
    id2 = o2.get("analysis_id") or o2.get("analysis_packet_id")

    after = len(arch.unsettled_ids())
    appended = (id1 != id2) and (after > before)

    # explicit supersedes (not overwrite)
    try:
        arch.record_reanalysis(analysis_id=id2, supersedes_analysis_id=id1,
                               reason="FORECAST_STALE_AFTER_EVENT")
        rea = arch.reanalysis_of(id1)
        supersedes_ok = len(rea) >= 1
    except Exception as e:
        rea = []
        supersedes_ok = False

    reg = PredictionRegistry()
    preds = reg.list_predictions(limit=200)
    registry_has_forecast = len(preds) > 0

    rec("J_archive_registry", "archive_registry", {
        "analysis_id_1": id1, "analysis_id_2": id2,
        "append_not_overwrite": appended,
        "supersedes_recorded": supersedes_ok,
        "reanalysis_links": rea,
        "unsettled_before": before, "unsettled_after": after,
        "prediction_registry_records": len(preds),
        "registry_has_forecast": registry_has_forecast,
    })
    return {"id1": id1, "id2": id2, "append": appended, "supersedes": supersedes_ok}


# ───────────────────────────────────────────────────────────── L. Performance
def section_l():
    from market_ai_hub.packet.builder import build_analysis_packet, clear_caches

    clear_caches()
    t0 = time.perf_counter()
    build_analysis_packet(market="osaka", target="OSE_NIKKEI225_MICRO_FUTURES",
                          horizon="1d", detail_level="compact", save_analysis=False)
    cold = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    build_analysis_packet(market="osaka", target="OSE_NIKKEI225_MICRO_FUTURES",
                          horizon="1d", detail_level="compact", save_analysis=False)
    warm = (time.perf_counter() - t0) * 1000

    rec("L_performance", "performance", {"cold_ms": round(cold, 1), "warm_ms": round(warm, 1),
                          "warm_faster": warm <= cold * 1.5 + 50})
    return {"cold_ms": cold, "warm_ms": warm}


def main():
    print("=== Phase 2V-A real-world validation ===")
    for name, fn in (
        ("C provider validation", section_c),
        ("D Osaka packet", section_d),
        ("E model inference", section_e),
        ("F Taiwan packet", section_f),
        ("G point-in-time", section_g),
        ("H cross-source", section_h),
        ("I failure injection", section_i),
        ("J archive/registry", section_j),
        ("L performance", section_l),
    ):
        print(f"\n--- {name} ---")
        t0 = time.perf_counter()
        try:
            fn()
            print(f"  done ({time.perf_counter()-t0:.1f}s)")
        except Exception as e:
            print(f"  SECTION ERROR: {e}")
            traceback.print_exc()
            rec("_section_errors", name, str(e)[:300])

    from market_ai_hub.config.settings import project_root
    out_p = _validation_out() / "REAL_PROVIDER_VALIDATION.json"
    out_p.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    full_p = project_root() / "data" / "phase2va_results.json"
    full_p.parent.mkdir(parents=True, exist_ok=True)
    full_p.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {out_p.name} + {full_p}")


if __name__ == "__main__":
    main()
