"""Phase 2D — Model Tournament CLI。

python -m market_ai_hub.research.tournament run [--targets ^N225,3706.TW] [--horizons 1d,2d,5d,10d]
python -m market_ai_hub.research.tournament leaderboard [--target] [--horizon]
python -m market_ai_hub.research.tournament inspect --model MODEL
python -m market_ai_hub.research.tournament compare MODEL_A MODEL_B
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402

from market_ai_hub.research.forward import _fetch_frame  # noqa: E402
from market_ai_hub.research.tournament.engine import ExamSpec, TournamentEngine  # noqa: E402
from market_ai_hub.research.tournament.performance_store import PerformanceStore  # noqa: E402

REVISIONS = {
    "chronos-2": "29ec3766d36d6f73f0696f85560a422f50e8498c",
    "timesfm-3.0": "43046b85ec22d584a13f8098c2ed39c889e129c2",
    "fincast": "2d7d90b159db8961d27c2cf165d51195902ef92b",
    "xgboost": "3.4.1", "lightgbm": "4.7.0",
    "nhits": "3.2.2", "nbeatsx": "3.2.2",
}

BASELINE_NAMES = {
    "last_price_naive", "random_walk", "drift", "moving_average", "seasonal_naive",
    "majority_class", "always_flat", "ridge", "var", "dynamic_factor", "kalman_local_level",
}
MODEL_NAMES = {
    "chronos-2", "timesfm-3.0", "fincast", "xgboost", "lightgbm", "nhits", "nbeatsx",
}


def build_adapters():
    from market_ai_hub.research.tournament.baselines import all_baseline_adapters
    from market_ai_hub.research.tournament.challengers import NBEATSxAdapter, NHITSAdapter
    from market_ai_hub.research.tournament.v1_adapters import (
        ChronosAdapter, FinCastAdapter, LightGBMAdapter, TimesFMAdapter, XGBoostAdapter,
    )

    return ([ChronosAdapter(), TimesFMAdapter(), FinCastAdapter(), XGBoostAdapter(), LightGBMAdapter(),
             NHITSAdapter(), NBEATSxAdapter()]
            + all_baseline_adapters())


def _best_baseline_and_model(summaries: dict) -> dict:
    base = [s for s in summaries.values() if s["model"] in BASELINE_NAMES and s.get("mae") is not None]
    models = [s for s in summaries.values() if s["model"] in MODEL_NAMES and s.get("mae") is not None]
    out = {"best_baseline": None, "best_baseline_mae": None, "best_model": None,
           "best_model_mae": None, "model_vs_best_baseline_delta": None}
    if base:
        b = min(base, key=lambda s: s["mae"])
        out["best_baseline"] = b["model"]
        out["best_baseline_mae"] = b["mae"]
    if models:
        m = min(models, key=lambda s: s["mae"])
        out["best_model"] = m["model"]
        out["best_model_mae"] = m["mae"]
    if out["best_baseline_mae"] and out["best_model_mae"]:
        out["model_vs_best_baseline_delta"] = round(
            (out["best_model_mae"] - out["best_baseline_mae"]) / out["best_baseline_mae"], 4
        )
    return out


def _regime_tag(df) -> str:
    closes = df.sort_values("timestamp_utc")["close"]
    rets = closes.pct_change().dropna()
    vol = float(rets.tail(20).std() * np.sqrt(252)) if len(rets) >= 20 else float("nan")
    if vol != vol:
        return "unknown"
    return "low" if vol < 0.15 else ("normal" if vol < 0.30 else "high")


def _print_leaderboard(result: dict) -> None:
    print(f"\n=== {result['target']} / {result['horizon']} (n_forecast_origins={result['n_origins']}) ===")
    rows = sorted(result["summaries"].values(), key=lambda s: (s.get("mae") is None, s.get("mae") or 1e9))
    print(f"{'model':<20} {'task':<10} {'MAE':>10} {'RMSE':>10} {'MASE':>8} {'cov':>6} {'dir_acc':>8} {'fail%':>6}")
    for s in rows:
        mae = f"{s['mae']:.4f}" if s.get("mae") is not None else "-"
        rmse = f"{s['rmse']:.4f}" if s.get("rmse") is not None else "-"
        mase = f"{s['mase']:.3f}" if s.get("mase") is not None else "-"
        cov = f"{s['coverage']:.3f}" if s.get("coverage") is not None else "-"
        da = f"{s['direction_accuracy']:.3f}" if s.get("direction_accuracy") is not None else "-"
        fr = f"{s['failure_rate']:.2f}" if s.get("failure_rate") is not None else "-"
        print(f"{s['model']:<20} {s['task']:<10} {mae:>10} {rmse:>10} {mase:>8} {cov:>6} {da:>8} {fr:>6}")
    bm = _best_baseline_and_model(result["summaries"])
    print(f"  BEST_BASELINE={bm['best_baseline']} (MAE={bm['best_baseline_mae']}) | "
          f"BEST_MODEL={bm['best_model']} (MAE={bm['best_model_mae']}) | "
          f"MODEL_VS_BEST_BASELINE_DELTA={bm['model_vs_best_baseline_delta']}")


def cmd_run(args) -> int:
    from market_ai_hub.research.tournament.data_quality import TargetDataQualityValidator

    engine = TournamentEngine()
    store = PerformanceStore()
    validator = TargetDataQualityValidator()
    targets = [t.strip() for t in args.targets.split(",") if t.strip()]
    horizons = [h.strip() for h in args.horizons.split(",") if h.strip()]
    for target in targets:
        try:
            df = _fetch_frame(target)
        except Exception as e:
            print(f"[{target}] data fetch failed: {e}")
            continue
        q = validator.validate(df)
        print(f"[{target}] data quality: {q['status']} ({q['evaluation_gate']}) "
              f"unique_close={q['metrics']['unique_price_count']} std={q['metrics']['price_std']:.4f}")
        if not q["eligible_for_evaluation"]:
            print(f"[{target}] SKIP ranking: {q['reasons']}")
            continue
        regime = _regime_tag(df)
        window = (str(df["timestamp_utc"].min()), str(df["timestamp_utc"].max()))
        for horizon in horizons:
            exam = ExamSpec(target, horizon, "v1", "base-v1", min_train=args.min_train, n_origins=args.n_origins)
            r = engine.run(exam, df, build_adapters())
            if r["status"] != "OK":
                print(f"[{target}/{horizon}] {r['status']} (n={r.get('n')})")
                continue
            for name, s in r["summaries"].items():
                store.save(exam.exam_hash(), target, horizon, regime, window,
                           REVISIONS.get(name, ""), s)
            _print_leaderboard(r)
    return 0


def cmd_leaderboard(args) -> int:
    store = PerformanceStore()
    for row in store.leaderboard(target=args.target or None, horizon=args.horizon or None):
        mae = f"{row['mae']:.4f}" if row.get("mae") is not None else "-"
        da = f"{row['direction_accuracy']:.3f}" if row.get("direction_accuracy") is not None else "-"
        print(f"{row['target']:<10} {row['horizon']:<5} {row['model']:<20} MAE={mae:>10} "
              f"dir_acc={da:>8} n={row['sample_size']} fail%={row['failure_rate']}")
    return 0


def cmd_inspect(args) -> int:
    store = PerformanceStore()
    rows = store.inspect(args.model)
    if not rows:
        print(f"no results for {args.model}")
        return 1
    for r in rows:
        print(f"{r['target']}/{r['horizon']} mae={r['mae']} rmse={r['rmse']} mase={r['mase']} "
              f"dir_acc={r['direction_accuracy']} coverage={r['coverage']} "
              f"runtime={r['runtime_seconds']}s vram={r['peak_vram_mb']}MB")
    return 0


def cmd_compare(args) -> int:
    store = PerformanceStore()
    a = {r["horizon"]: r for r in store.inspect(args.model_a)}
    b = {r["horizon"]: r for r in store.inspect(args.model_b)}
    for h in sorted(set(a) | set(b)):
        ra, rb = a.get(h), b.get(h)
        ma = f"{ra['mae']:.4f}" if ra and ra.get("mae") is not None else "-"
        mb = f"{rb['mae']:.4f}" if rb and rb.get("mae") is not None else "-"
        print(f"{h:<5} {args.model_a}={ma:<10} {args.model_b}={mb:<10}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="market_ai_hub.research.tournament")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("--targets", default="^N225,3706.TW")
    p.add_argument("--horizons", default="1d,2d,5d,10d")
    p.add_argument("--n-origins", type=int, default=5)
    p.add_argument("--min-train", type=int, default=120)
    p.set_defaults(fn=cmd_run)
    p = sub.add_parser("leaderboard"); p.add_argument("--target", default=None); p.add_argument("--horizon", default=None); p.set_defaults(fn=cmd_leaderboard)
    p = sub.add_parser("inspect"); p.add_argument("--model", required=True); p.set_defaults(fn=cmd_inspect)
    p = sub.add_parser("compare"); p.add_argument("model_a"); p.add_argument("model_b"); p.set_defaults(fn=cmd_compare)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
