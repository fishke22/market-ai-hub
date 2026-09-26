"""Phase 2D — 公平 Model Tournament 引擎（same-exam walk-forward OOS）。

所有模型用同一 target / horizon / forecast origins / information_cutoff /
dataset version / feature version 才能進同一 leaderboard。
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from market_ai_hub.research.tournament.adapter import ModelAdapter
from market_ai_hub.services.horizon import parse_horizon


@dataclass(frozen=True)
class ExamSpec:
    target: str
    horizon: str
    dataset_version: str
    feature_version: str
    min_train: int
    n_origins: int

    def exam_hash(self) -> str:
        payload = json.dumps(self.__dict__, sort_keys=True).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:16]

    def same_as(self, other: "ExamSpec") -> bool:
        return self.exam_hash() == other.exam_hash()


def assert_same_exam(a: ExamSpec, b: ExamSpec) -> None:
    if not a.same_as(b):
        raise ValueError(f"different exam: {a} vs {b}")


def _direction_of(actual: float, origin_price: float) -> str:
    return "up" if actual > origin_price else ("down" if actual < origin_price else "flat")


def _finite_or_none(value) -> float | None:
    """Canonical metric boundary: finite float, else typed None (never NaN/±Inf)."""
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


@dataclass
class ModelRun:
    model: str
    task: str
    points: list[float | None] = field(default_factory=list)
    p10: list[float | None] = field(default_factory=list)
    p90: list[float | None] = field(default_factory=list)
    directions: list[str] = field(default_factory=list)
    actuals: list[float] = field(default_factory=list)
    origin_prices: list[float] = field(default_factory=list)
    origins: list[int] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)
    runtime_seconds: float = 0.0
    peak_vram_mb: float = 0.0
    failures: int = 0
    warnings: list[str] = field(default_factory=list)


class TournamentEngine:
    def __init__(self, gpu_guard=None) -> None:
        from market_ai_hub.research.tournament.gpu_guard import GpuGuard

        self.gpu_guard = gpu_guard or GpuGuard()

    def run(self, exam: ExamSpec, df: pd.DataFrame, adapters: list[ModelAdapter]) -> dict:
        steps = parse_horizon(exam.horizon, "1d").effective_horizon_steps
        closes = df.sort_values("timestamp_utc")["close"].reset_index(drop=True)
        n = len(closes)
        if n < exam.min_train + steps:
            return {"status": "INSUFFICIENT_DATA", "exam": exam.exam_hash(), "n": n}

        max_origin = n - steps
        origins = np.linspace(exam.min_train, max_origin, exam.n_origins, dtype=int)
        origins = sorted(set(int(o) for o in origins))

        runs: dict[str, ModelRun] = {a.name: ModelRun(model=a.name, task=a.task) for a in adapters}

        for origin in origins:
            train_df = df.sort_values("timestamp_utc").iloc[:origin]
            actual = float(closes.iloc[origin + steps - 1])
            origin_price = float(closes.iloc[origin - 1])
            for a in adapters:
                run = runs[a.name]
                run.origins.append(origin)
                run.actuals.append(actual)
                run.origin_prices.append(origin_price)
                try:
                    if not np.isfinite(actual) or not np.isfinite(origin_price):
                        run.points.append(None)
                        run.p10.append(None)
                        run.p90.append(None)
                        run.directions.append("")
                        run.statuses.append("INVALID_TARGET")
                        run.warnings.append(f"{a.name} invalid evaluation target")
                        continue

                    t0 = time.time()
                    res = a.forecast(train_df, steps)
                    run.runtime_seconds += time.time() - t0
                    run.peak_vram_mb = max(run.peak_vram_mb, self.gpu_guard.peak_vram())

                    point = None
                    status = "VALID"
                    if run.task == "price":
                        if res.point is None:
                            status = "ABSTAINED"
                        else:
                            try:
                                candidate = float(res.point)
                            except (TypeError, ValueError):
                                candidate = float("nan")
                            if np.isfinite(candidate):
                                point = candidate
                            else:
                                status = "NONFINITE"
                    elif res.direction not in {"up", "down", "flat"}:
                        status = "ABSTAINED"

                    run.points.append(point)
                    run.p10.append(res.p10 if status == "VALID" and res.quantile_valid is True else None)
                    run.p90.append(res.p90 if status == "VALID" and res.quantile_valid is True else None)
                    if status == "VALID":
                        direction = res.direction if res.direction in {"up", "down", "flat"} else (
                            _direction_of(point, origin_price) if point is not None else ""
                        )
                    else:
                        direction = ""
                    run.directions.append(direction)
                    run.statuses.append(status)
                    if res.warnings:
                        run.warnings.extend(res.warnings)
                except Exception as e:  # noqa: BLE001
                    run.failures += 1
                    run.points.append(None)
                    run.p10.append(None)
                    run.p90.append(None)
                    run.directions.append("")
                    run.statuses.append("FAILED")
                    run.warnings.append(f"{a.name} failed: {type(e).__name__}")
                finally:
                    a.release()

        summaries = {name: self._summarize(run, steps) for name, run in runs.items()}
        return {
            "status": "OK",
            "exam": exam.exam_hash(),
            "target": exam.target,
            "horizon": exam.horizon,
            "n_origins": len(origins),
            "summaries": summaries,
            "pairwise_comparisons": self._paired_comparisons(runs),
        }

    @staticmethod
    def _statuses(run: ModelRun) -> list[str]:
        if len(run.statuses) == len(run.actuals):
            return run.statuses
        statuses = []
        for i in range(len(run.actuals)):
            point = run.points[i] if i < len(run.points) else None
            direction = run.directions[i] if i < len(run.directions) else ""
            if run.task == "price":
                if point is None:
                    statuses.append("ABSTAINED")
                else:
                    try:
                        finite = np.isfinite(float(point))
                    except (TypeError, ValueError):
                        finite = False
                    statuses.append("VALID" if finite else "NONFINITE")
            else:
                statuses.append("VALID" if direction in {"up", "down", "flat"} else "ABSTAINED")
        return statuses

    def _summarize(self, run: ModelRun, steps: int) -> dict:
        statuses = self._statuses(run)
        n_attempts = len(run.actuals)
        counts = {s: statuses.count(s) for s in ("VALID", "FAILED", "ABSTAINED", "NONFINITE", "INVALID_TARGET")}
        effective = counts["VALID"]
        out: dict = {
            "model": run.model, "task": run.task,
            "sample_size": n_attempts, "effective_sample_size": effective,
            "failure_count": counts["FAILED"], "abstention_count": counts["ABSTAINED"],
            "nonfinite_count": counts["NONFINITE"], "invalid_target_count": counts["INVALID_TARGET"],
            "failure_rate": round(counts["FAILED"] / n_attempts, 4) if n_attempts else None,
            "coverage_rate": effective / n_attempts if n_attempts else None,
            "runtime_seconds": round(run.runtime_seconds, 3),
            "peak_vram_mb": run.peak_vram_mb,
            "warnings": run.warnings[:3],
        }
        valid = [s == "VALID" for s in statuses]
        if run.task == "price" and any(valid):
            pts = [p for p, ok in zip(run.points, valid) if ok]
            acts = [a for a, ok in zip(run.actuals, valid) if ok]
            naive = [op for op, ok in zip(run.origin_prices, valid) if ok]
            out.update(self._price_metrics(
                acts, pts, naive,
                [q for q, ok in zip(run.p10, valid) if ok],
                [q for q, ok in zip(run.p90, valid) if ok],
            ))
        dirs = [d for d, ok in zip(run.directions, valid) if ok and d]
        if dirs:
            acts = [a for a, d, ok in zip(run.actuals, run.directions, valid) if ok and d]
            origin = [op for op, d, ok in zip(run.origin_prices, run.directions, valid) if ok and d]
            out.update(self._direction_metrics(acts, dirs, origin))
        return out

    def _paired_comparisons(self, runs: dict[str, ModelRun]) -> list[dict]:
        names = list(runs)
        comparisons = []
        for i, name_a in enumerate(names):
            a = runs[name_a]
            status_a = self._statuses(a)
            for name_b in names[i + 1:]:
                b = runs[name_b]
                if a.task != b.task or len(a.actuals) != len(b.actuals):
                    continue
                status_b = self._statuses(b)
                common = [j for j, (sa, sb) in enumerate(zip(status_a, status_b))
                          if sa == "VALID" and sb == "VALID"]
                n = len(a.actuals)
                origins = a.origins if len(a.origins) == n else list(range(n))
                row = {
                    "model_a": name_a, "model_b": name_b, "task": a.task,
                    "common_origin_count": len(common),
                    "common_origin_coverage_rate": len(common) / n if n else None,
                    "model_a_coverage_rate": status_a.count("VALID") / n if n else None,
                    "model_b_coverage_rate": status_b.count("VALID") / n if n else None,
                    "common_origin_indices": [int(origins[j]) for j in common],
                }
                if not common:
                    row.update(metric=None, model_a_metric_common=None,
                               model_b_metric_common=None, delta_a_minus_b=None)
                elif a.task == "price":
                    actual = np.asarray([a.actuals[j] for j in common], dtype=float)
                    fa = np.asarray([a.points[j] for j in common], dtype=float)
                    fb = np.asarray([b.points[j] for j in common], dtype=float)
                    ma = float(np.mean(np.abs(actual - fa)))
                    mb = float(np.mean(np.abs(actual - fb)))
                    row.update(metric="mae", model_a_metric_common=ma,
                               model_b_metric_common=mb, delta_a_minus_b=ma - mb)
                else:
                    actual = np.asarray([a.actuals[j] for j in common], dtype=float)
                    origin = np.asarray([a.origin_prices[j] for j in common], dtype=float)
                    true = np.where(actual > origin, "up", np.where(actual < origin, "down", "flat"))
                    pa = np.asarray([a.directions[j] for j in common])
                    pb = np.asarray([b.directions[j] for j in common])
                    ma = float((true == pa).mean())
                    mb = float((true == pb).mean())
                    row.update(metric="direction_accuracy", model_a_metric_common=ma,
                               model_b_metric_common=mb, delta_a_minus_b=ma - mb)
                comparisons.append(row)
        return comparisons

    @staticmethod
    def _price_metrics(actual, forecast, naive, p10=None, p90=None) -> dict:
        actual = np.asarray(actual, float); forecast = np.asarray(forecast, float)
        naive = np.asarray(naive, float)
        err = actual - forecast
        mae = _finite_or_none(np.mean(np.abs(err)))
        rmse = _finite_or_none(np.sqrt(np.mean(err ** 2)))
        naive_mae = _finite_or_none(np.mean(np.abs(actual - naive)))
        # naive_mae == 0 -> MASE is not evaluable (typed None, never NaN)
        mase = _finite_or_none(mae / naive_mae) if (mae is not None and naive_mae) else None
        pinball = _finite_or_none(np.mean(np.where(err >= 0, 0.5 * err, -0.5 * err)))
        out = {"mae": mae, "rmse": rmse, "mase": mase, "pinball_loss": pinball}
        out.update(coverage=None, interval_width=None, calibration_error=None, interval_sample_size=0)
        if p10 is not None and p90 is not None and len(p10) == len(p90) == len(actual):
            lo = np.asarray(p10, float); hi = np.asarray(p90, float)
            valid = np.isfinite(actual) & np.isfinite(lo) & np.isfinite(hi) & (lo <= hi)
            if valid.any():
                observed, lower, upper = actual[valid], lo[valid], hi[valid]
                width = (float(np.mean((upper - lower) / np.abs(observed)))
                         if np.all(observed != 0) else None)
                out.update(coverage=_finite_or_none(((observed >= lower) & (observed <= upper)).mean()),
                           interval_width=_finite_or_none(width),
                           calibration_error=_finite_or_none(
                               abs(float(((observed >= lower) & (observed <= upper)).mean()) - 0.8)),
                           interval_sample_size=int(valid.sum()))
        return out

    @staticmethod
    def _direction_metrics(actual, directions, origin) -> dict:
        from sklearn.metrics import balanced_accuracy_score, f1_score, matthews_corrcoef

        actual = np.asarray(actual, float); origin = np.asarray(origin, float)
        true = np.where(actual > origin, 1, np.where(actual < origin, -1, 0))
        pred = np.array([1 if d == "up" else (-1 if d == "down" else 0) for d in directions])
        acc = _finite_or_none((true == pred).mean())
        # 跳過 flat 樣本讓方向更乾淨（beta 方向 up/down）
        mask = true != 0
        if mask.sum() >= 2 and len(set(pred[mask])) >= 2:
            bal = _finite_or_none(balanced_accuracy_score(true[mask], pred[mask]))
            f1 = _finite_or_none(f1_score(true[mask], pred[mask], average="macro", zero_division=0))
            mcc = _finite_or_none(matthews_corrcoef(true[mask], pred[mask]))
        else:
            # 樣本不足 -> NOT_EVALUATABLE（typed None，不得以 NaN 進排名）
            bal = f1 = mcc = None
        return {"direction_accuracy": acc, "balanced_accuracy": bal, "macro_f1": f1, "mcc": mcc}
