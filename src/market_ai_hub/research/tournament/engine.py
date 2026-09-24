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
                try:
                    t0 = time.time()
                    res = a.forecast(train_df, steps)
                    run.runtime_seconds += time.time() - t0
                    run.peak_vram_mb = max(run.peak_vram_mb, self.gpu_guard.peak_vram())
                    if res.point is not None:
                        run.points.append(res.point)
                    else:
                        run.points.append(None)
                    run.p10.append(res.p10 if res.quantile_valid is True else None)
                    run.p90.append(res.p90 if res.quantile_valid is True else None)
                    run.directions.append(res.direction or _direction_of(res.point, origin_price)
                                         if res.direction or res.point is not None else "")
                    run.actuals.append(actual)
                    run.origin_prices.append(origin_price)
                    if res.warnings:
                        run.warnings.extend(res.warnings)
                except Exception as e:  # noqa: BLE001
                    run.failures += 1
                    run.points.append(None)
                    run.p10.append(None)
                    run.p90.append(None)
                    run.directions.append("")
                    run.actuals.append(actual)
                    run.origin_prices.append(origin_price)
                    run.warnings.append(f"{a.name} failed: {type(e).__name__}")
                finally:
                    a.release()

        summaries = {}
        for name, run in runs.items():
            summaries[name] = self._summarize(run, steps)
        return {
            "status": "OK",
            "exam": exam.exam_hash(),
            "target": exam.target,
            "horizon": exam.horizon,
            "n_origins": len(origins),
            "summaries": summaries,
        }

    def _summarize(self, run: ModelRun, steps: int) -> dict:
        n_attempts = len(run.actuals)
        n_fail = run.failures
        effective = n_attempts - n_fail
        out: dict = {
            "model": run.model, "task": run.task,
            "sample_size": n_attempts, "effective_sample_size": effective,
            "failure_rate": round(n_fail / n_attempts, 4) if n_attempts else None,
            "runtime_seconds": round(run.runtime_seconds, 3),
            "peak_vram_mb": run.peak_vram_mb,
            "warnings": run.warnings[:3],
        }
        # price metrics（僅有 point 的 model）
        pts = [p for p in run.points if p is not None]
        if pts:
            acts = [a for a, p in zip(run.actuals, run.points) if p is not None]
            naive = [op for op, p in zip(run.origin_prices, run.points) if p is not None]
            out.update(self._price_metrics(acts, pts, naive,
                                           [q for q, p in zip(run.p10, run.points) if p is not None],
                                           [q for q, p in zip(run.p90, run.points) if p is not None]))
        # direction metrics（有 direction 的 model）
        dirs = [d for d in run.directions if d]
        if dirs:
            acts = [a for a, d in zip(run.actuals, run.directions) if d]
            origin = [op for op, d in zip(run.origin_prices, run.directions) if d]
            out.update(self._direction_metrics(acts, dirs, origin))
        return out

    @staticmethod
    def _price_metrics(actual, forecast, naive, p10=None, p90=None) -> dict:
        actual = np.asarray(actual, float); forecast = np.asarray(forecast, float)
        naive = np.asarray(naive, float)
        err = actual - forecast
        mae = float(np.mean(np.abs(err)))
        rmse = float(np.sqrt(np.mean(err ** 2)))
        naive_mae = float(np.mean(np.abs(actual - naive)))
        mase = mae / naive_mae if naive_mae > 0 else float("nan")
        pinball = float(np.mean(np.where(err >= 0, 0.5 * err, -0.5 * err)))
        out = {"mae": mae, "rmse": rmse, "mase": mase, "pinball_loss": pinball}
        out.update(coverage=None, interval_width=None, calibration_error=None, interval_sample_size=0)
        if p10 is not None and p90 is not None and len(p10) == len(p90) == len(actual):
            lo = np.asarray(p10, float); hi = np.asarray(p90, float)
            valid = np.isfinite(actual) & np.isfinite(lo) & np.isfinite(hi) & (lo <= hi)
            if valid.any():
                observed, lower, upper = actual[valid], lo[valid], hi[valid]
                coverage = float(((observed >= lower) & (observed <= upper)).mean())
                width = (float(np.mean((upper - lower) / np.abs(observed)))
                         if np.all(observed != 0) else None)
                out.update(coverage=coverage, interval_width=width,
                           calibration_error=abs(coverage - 0.8),
                           interval_sample_size=int(valid.sum()))
        return out

    @staticmethod
    def _direction_metrics(actual, directions, origin) -> dict:
        from sklearn.metrics import balanced_accuracy_score, f1_score, matthews_corrcoef

        actual = np.asarray(actual, float); origin = np.asarray(origin, float)
        true = np.where(actual > origin, 1, np.where(actual < origin, -1, 0))
        pred = np.array([1 if d == "up" else (-1 if d == "down" else 0) for d in directions])
        acc = float((true == pred).mean())
        # 排除 flat 的方向命中考量（純方向 up/down）
        mask = true != 0
        if mask.sum() >= 2 and len(set(pred[mask])) >= 2:
            bal = float(balanced_accuracy_score(true[mask], pred[mask]))
            f1 = float(f1_score(true[mask], pred[mask], average="macro", zero_division=0))
            mcc = float(matthews_corrcoef(true[mask], pred[mask]))
        else:
            bal = f1 = mcc = float("nan")
        return {"direction_accuracy": acc, "balanced_accuracy": bal, "macro_f1": f1, "mcc": mcc}
