"""Phase 2A Forward Paper Test CLI。

用法：
  python -m market_ai_hub.research.forward run [--symbols ^N225,3706.TW] [--horizon 1d] [--mlflow]
  python -m market_ai_hub.research.forward settle [--forecast-id ID | --all]
  python -m market_ai_hub.research.forward status [--model X]
  python -m market_ai_hub.research.forward leaderboard

原則：
- forecast 建立當下即永久保存（不可變）；不得用事後資料重建後冒充 Forward Test。
- 所有 forecast 帶 information_cutoff；任何 available_at > cutoff 的資料不得進模型。
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from market_ai_hub.research.registry import PredictionRegistry  # noqa: E402
from market_ai_hub.research.schemas import (  # noqa: E402
    OutcomeRecord,
    PredictionRecord,
    SettleNotReadyError,
)

SUPPORTED = {"^N225", "3706.TW"}


def _market_of(symbol: str) -> str:
    return "TSE" if symbol == "^N225" else "TWSE"


def _fetch_frame(symbol: str) -> pd.DataFrame:
    """抓 symbol 日線統一 schema df（含 open/high/low/close/volume）。"""
    if symbol == "^N225":
        from market_ai_hub.providers.yfinance_provider import YFinanceProvider

        return YFinanceProvider().fetch(symbol, period="1y", interval="1d")

    from market_ai_hub.providers.twse import TWSEProvider

    end = datetime.now(timezone.utc).strftime("%Y%m%d")
    start = (datetime.now(timezone.utc) - pd.Timedelta(days=180)).strftime("%Y%m%d")
    try:
        return TWSEProvider().fetch_symbol_daily(symbol.split(".")[0], start, end)
    except Exception:
        from market_ai_hub.providers.yfinance_provider import YFinanceProvider

        return YFinanceProvider().fetch(symbol, period="1y", interval="1d")


def _closes(df: pd.DataFrame) -> pd.Series:
    return df.sort_values("timestamp_utc").set_index("timestamp_utc")["close"].dropna()


def build_forecasts(symbol: str, horizon: str = "1d") -> list[PredictionRecord]:
    """用既有 V1 模型產生 forecasts 並轉成 PredictionRecord（不可變）。"""
    from market_ai_hub.ensemble.ensemble import ensemble_equal_weight
    from market_ai_hub.features.features import build_features
    from market_ai_hub.models.baseline_ml import BaselineClassifier, baseline_forecast
    from market_ai_hub.models.chronos_model import chronos_forecast
    from market_ai_hub.models.timesfm_model import timesfm_forecast
    from market_ai_hub.services.horizon import parse_horizon
    from market_ai_hub.services.model_runtime import get_chronos, get_timesfm

    df = _fetch_frame(symbol)
    closes = _closes(df)
    origin_price = float(closes.iloc[-1])
    steps = parse_horizon(horizon, "1d").effective_horizon_steps

    fos = []
    try:
        fos.append(chronos_forecast(get_chronos(), symbol, closes, horizon=horizon, horizon_steps=steps))
    except Exception:
        pass
    try:
        fos.append(timesfm_forecast(get_timesfm(), symbol, closes, horizon=horizon, horizon_steps=steps))
    except Exception:
        pass
    feat = build_features(df)
    for name in ("xgb", "lgbm"):
        try:
            fos.append(baseline_forecast(BaselineClassifier(name), symbol, feat, horizon=horizon))
        except Exception:
            pass
    if fos:
        try:
            fos.append(ensemble_equal_weight(fos, symbol, horizon))
        except Exception:
            pass

    return [prediction_record_from_forecast(fo, symbol, origin_price) for fo in fos]


def prediction_record_from_forecast(fo, symbol: str, origin_price: float | None = None) -> PredictionRecord:
    from market_ai_hub.services.build_info import build_fingerprint

    origin = pd.Timestamp(fo.forecast_origin).to_pydatetime() if fo.forecast_origin else None
    # ensemble 只填 legacy forecast_dates，未填 forecast_target_dates → fallback
    target_dates = list(fo.forecast_target_dates) or list(fo.forecast_dates)
    return PredictionRecord(
        forecast_id=str(uuid4()),
        created_at=datetime.now(timezone.utc),
        information_cutoff=origin or datetime.now(timezone.utc),
        market=_market_of(symbol),
        target=symbol,
        instrument=symbol,
        contract="index" if symbol == "^N225" else "equity",
        horizon=fo.horizon,
        forecast_origin=origin,
        forecast_target_dates=target_dates,
        exchange_calendar=fo.target_calendar,
        model_name=fo.model,
        model_task=fo.model_task,
        model_revision=fo.model_revision,
        model_build_id=fo.model_build_id or build_fingerprint()["build_id"],
        training_cutoff=origin,
        input_data_hash=fo.input_data_hash,
        dataset_version=f"{_market_of(symbol)}:{symbol}",
        feature_version="base-v1",
        forecast_config_hash=fo.forecast_config_hash,
        inference_seed=fo.inference_seed,
        sampling_config=fo.sampling_config,
        deterministic_mode=fo.deterministic_mode,
        point_forecast=fo.point_forecast,
        p10=fo.quantiles.get("p10"),
        p50=fo.quantiles.get("p50"),
        p90=fo.quantiles.get("p90"),
        origin_price=origin_price,
        direction=fo.direction,
        raw_class_scores=fo.class_probabilities,
        probability_calibrated=bool(fo.probability_calibrated),
        engineering_status=fo.engineering_status,
        predictive_validation_status=fo.predictive_validation_status,
        regime_as_known_at_prediction_time="UNKNOWN",
        data_quality_state=fo.data_grade.value if hasattr(fo.data_grade, "value") else str(fo.data_grade),
        raw_output_reference="",
    )


def compute_outcome(rec: PredictionRecord, actual: float,
                    actual_timestamp: datetime | None = None) -> OutcomeRecord:
    """純函式：由 forecast + 實際值計算 OutcomeRecord。"""
    fc = rec.point_forecast
    abs_err = abs(actual - fc)
    sq_err = abs_err ** 2
    scaled_err = None
    if rec.origin_price is not None:
        denom = abs(actual - rec.origin_price)
        scaled_err = abs_err / denom if denom > 1e-12 else None

    direction_result = ""
    if rec.origin_price is not None:
        move = actual - rec.origin_price
        if rec.direction == "up":
            direction_result = "correct" if move > 0 else "incorrect"
        elif rec.direction == "down":
            direction_result = "correct" if move < 0 else "incorrect"
        elif rec.direction == "flat":
            direction_result = "correct" if abs(move) <= 1e-9 else "incorrect"

    interval_hit = None
    if rec.p10 is not None and rec.p90 is not None:
        interval_hit = bool(rec.p10 <= actual <= rec.p90)

    pinball = None
    if rec.p50 is not None:
        pinball = 0.5 * (rec.p50 - actual) if actual <= rec.p50 else 0.5 * (actual - rec.p50)

    return OutcomeRecord(
        forecast_id=rec.forecast_id,
        actual=actual,
        actual_timestamp=actual_timestamp,
        absolute_error=abs_err,
        squared_error=sq_err,
        scaled_error=scaled_err,
        direction_result=direction_result,
        interval_hit=interval_hit,
        pinball_loss=pinball,
    )


def settle_forecast(registry: PredictionRegistry, forecast_id: str,
                    actual: float, actual_timestamp: datetime | None = None) -> OutcomeRecord:
    rec = registry.get(forecast_id)
    outcome = compute_outcome(PredictionRecord(**rec), actual, actual_timestamp)
    registry.settle(outcome)
    return outcome


def _fetch_actual(symbol: str, target_date: str) -> float:
    """結算用的 actual close（best-effort）。target_date 未到 → SettleNotReadyError。"""
    target = pd.Timestamp(target_date).tz_localize("UTC")
    today = pd.Timestamp.now("UTC").normalize()
    if target > today:
        raise SettleNotReadyError(f"target date {target_date} 尚未到達，無法結算")
    from market_ai_hub.providers.yfinance_provider import YFinanceProvider

    df = YFinanceProvider().fetch(symbol, period="3mo", interval="1d")
    row = df[df["timestamp_utc"].dt.tz_convert("UTC").dt.normalize() >= target]
    if row.empty:
        raise SettleNotReadyError(f"no actual data available for {symbol} on/after {target_date}")
    return float(row.iloc[0]["close"])


def cmd_run(args) -> int:
    registry = PredictionRegistry()
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    symbols = [s for s in symbols if s in SUPPORTED] or sorted(SUPPORTED)
    for sym in symbols:
        try:
            records = build_forecasts(sym, args.horizon)
        except Exception as e:
            print(f"[{sym}] forecast build failed: {e}")
            continue
        for rec in records:
            registry.register(rec)
            print(f"registered {rec.forecast_id}  model={rec.model_name}  symbol={sym}  "
                  f"horizon={rec.horizon}  targets={rec.forecast_target_dates}")
        if args.mlflow:
            from market_ai_hub.research.mlflow_tracker import sanitize_params, start_run

            for rec in records:
                start_run("forward", sanitize_params({
                    "model": rec.model_name, "symbol": sym, "horizon": rec.horizon,
                    "revision": rec.model_revision, "dataset_version": rec.dataset_version,
                    "feature_version": rec.feature_version, "seed": rec.inference_seed,
                }), {"point_forecast": rec.point_forecast}, artifact_ref=rec.forecast_id)
    registry.export_parquet()
    return 0


def cmd_settle(args) -> int:
    registry = PredictionRegistry()
    if not args.forecast_id and not args.all:
        print("請指定 --forecast-id 或 --all")
        return 1
    ids = [args.forecast_id] if args.forecast_id else [
        r["forecast_id"] for r in registry.list_predictions(settled=False, limit=10000)
    ]
    for fid in ids:
        rec = registry.get(fid)
        target = rec["forecast_target_dates"][-1] if rec["forecast_target_dates"] else None
        if not target:
            print(f"[{fid}] no target date, skip")
            continue
        try:
            actual = _fetch_actual(rec["target"], target)
            outcome = settle_forecast(registry, fid, actual)
            print(f"[{fid}] settled actual={actual:.4f} abs_err={outcome.absolute_error:.6f} "
                  f"dir={outcome.direction_result}")
        except SettleNotReadyError as e:
            print(f"[{fid}] not settleable: {e}")
        except Exception as e:
            print(f"[{fid}] settle error: {e}")
    registry.export_parquet()
    return 0


def cmd_status(args) -> int:
    registry = PredictionRegistry()
    rows = registry.list_predictions(model_name=args.model or None, settled=None, limit=args.limit)
    for r in rows:
        st = "settled" if r.get("settled") else "open"
        print(f"{r['forecast_id'][:8]}  {st:<7} model={r['model_name']:<16} "
              f"symbol={r['target']:<10} horizon={r['horizon']:<5} targets={r['forecast_target_dates']}")
    print(f"total shown: {len(rows)}")
    return 0


def cmd_leaderboard(args) -> int:
    registry = PredictionRegistry()
    for row in registry.leaderboard():
        print(f"model={row['model_name']:<16} n={row['n']} mae={row['mae']:.6f} "
              f"rmse={row['rmse']:.6f} dir_acc={row['direction_accuracy']:.4f} "
              f"cov={row['interval_coverage']:.4f} pinball={row['pinball']:.6f}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="market_ai_hub.research.forward")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run"); p.add_argument("--symbols", default="^N225,3706.TW"); p.add_argument("--horizon", default="1d"); p.add_argument("--mlflow", action="store_true"); p.set_defaults(fn=cmd_run)
    p = sub.add_parser("settle"); p.add_argument("--forecast-id", default=None); p.add_argument("--all", action="store_true"); p.set_defaults(fn=cmd_settle)
    p = sub.add_parser("status"); p.add_argument("--model", default=None); p.add_argument("--limit", type=int, default=50); p.set_defaults(fn=cmd_status)
    p = sub.add_parser("leaderboard"); p.set_defaults(fn=cmd_leaderboard)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
