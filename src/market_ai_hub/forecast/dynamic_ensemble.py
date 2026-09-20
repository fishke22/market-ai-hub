"""Phase 2G — Dynamic Ensemble（I/J/N）+ quantile 語義（P）。

- 權重只能程式計算（inverse normalized loss + calibration + reliability + sample shrinkage）。
- BEST_BASELINE 是合法候選；AI 打不贏 baseline 時允許 BASELINE_DOMINANT。
- model 失敗（timeout/OOM/missing dep/invalid quantile/data mismatch）→ 從本次 eligible set 移除，
  記錄 MODEL_SKIPPED_RUNTIME，不得整次分析失敗。
- 不得把 component P10/P50/P90 直接平均當 predictive quantile：
  只有 sample-level mixture 才回 validated quantile。
"""
from __future__ import annotations

import numpy as np

from market_ai_hub.forecast.contract import (
    ENSEMBLE_RESEARCH_QUANTILE_SUMMARY,
    SAMPLE_LEVEL_MIXTURE,
)
from market_ai_hub.forecast.weights import compute_weights


class DynamicEnsembleEngine:
    def __init__(self, shrinkage_k: float = 20.0) -> None:
        self.shrinkage_k = shrinkage_k

    def compute_weights(self, model_stats: list[dict]) -> dict[str, float]:
        return compute_weights(model_stats, shrinkage_k=self.shrinkage_k)

    def mixture_quantiles(self, samples_by_model: dict[str, list[float]],
                          weights: dict[str, float]) -> dict:
        """真正 sample-level mixture → validated predictive quantiles。"""
        rng = np.random.default_rng(0)
        pooled: list[float] = []
        for m, w in weights.items():
            samples = samples_by_model.get(m)
            if not samples:
                continue
            n = int(round(w * 10000))
            pooled.extend(rng.choice(samples, size=n, replace=True))
        if not pooled:
            return {"p50": None, "p10": None, "p90": None,
                    "method": SAMPLE_LEVEL_MIXTURE, "validated": True, "n_samples": 0}
        a = np.asarray(pooled, dtype=float)
        return {
            "p10": float(np.quantile(a, 0.10)), "p50": float(np.quantile(a, 0.50)),
            "p90": float(np.quantile(a, 0.90)), "n_samples": len(pooled),
            "method": SAMPLE_LEVEL_MIXTURE, "validated": True,
        }

    def quantile_summary(self, quantiles_by_model: dict[str, dict[str, float | None]],
                         weights: dict[str, float]) -> dict:
        """component quantile 加權平均 → 只算 summary，標 UNVALIDATED。"""
        acc = {"p10": 0.0, "p50": 0.0, "p90": 0.0}
        for m, w in weights.items():
            q = quantiles_by_model.get(m) or {}
            for k in ("p10", "p50", "p90"):
                v = q.get(k)
                acc[k] += (v if v is not None else 0.0) * w
        return {
            "p10": acc["p10"], "p50": acc["p50"], "p90": acc["p90"],
            "method": ENSEMBLE_RESEARCH_QUANTILE_SUMMARY, "validated": False,
        }

    def run_safe(self, components: list[dict], model_stats: list[dict]) -> dict:
        """components: list of {model, samples(list)} 或 {model, quantiles(dict)}。

        失敗的 component 會被 skip（MODEL_SKIPPED_RUNTIME）。
        回傳 {weights, mixture(validated), summary(unvalidated), skipped}。
        """
        weights = self.compute_weights(model_stats)
        samples_by_model: dict[str, list[float]] = {}
        quantiles_by_model: dict[str, dict] = {}
        skipped: list[dict] = []
        for c in components:
            m = c.get("model")
            if m is None or m not in weights:
                continue
            try:
                samples = c.get("samples")
                if samples is not None and len(samples) > 0:
                    samples_by_model[m] = [float(x) for x in samples]
                    continue
                quantiles = c.get("quantiles")
                if quantiles is not None:
                    quantiles_by_model[m] = quantiles
                    continue
                skipped.append({"model": m, "reason": "missing samples/quantiles"})
            except Exception as e:  # noqa: BLE001
                skipped.append({"model": m, "reason": f"MODEL_SKIPPED_RUNTIME: {str(e)[:100]}"})
        return {
            "weights": weights,
            "mixture": self.mixture_quantiles(samples_by_model, weights),
            "summary": self.quantile_summary(quantiles_by_model, weights),
            "skipped": skipped,
        }
