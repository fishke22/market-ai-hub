"""Phase 2G — Regime Model Router（K/L）。

不能只選歷史最高分模型；需考量 sample_size / confidence / global shrinkage。
小樣本（如 VOL_HIGH 只有 4 obs）→ REGIME_EVIDENCE_INSUFFICIENT → 回退 global。
"""
from __future__ import annotations

from market_ai_hub.forecast.weights import compute_weights

MIN_REGIME_SAMPLE = 30


class RegimeModelRouter:
    def __init__(self, min_regime_sample: int = MIN_REGIME_SAMPLE, shrinkage_k: float = 20.0) -> None:
        self.min_regime_sample = min_regime_sample
        self.shrinkage_k = shrinkage_k

    def route(self, target: str, horizon: str, current_regime: str,
              performance: list[dict]) -> dict:
        """performance: list of {model, regime, sample_size, loss, calibration_error, failure_rate}
        每模型需含 regime=current_regime 與 regime='ALL'（global）兩種記錄。

        回傳 {eligible_models, model_weights, fallback_model, evidence_state}。
        """
        per_model: dict[str, dict] = {}
        for r in performance:
            m = r.get("model")
            if m is None:
                continue
            per_model.setdefault(m, {})
            per_model[m][r.get("regime", "ALL")] = r

        stats: list[dict] = []
        evidence: dict[str, str] = {}
        for m, recs in per_model.items():
            regime_rec = recs.get(current_regime)
            global_rec = recs.get("ALL") or regime_rec
            if regime_rec is None and global_rec is None:
                continue
            n = (regime_rec or {}).get("sample_size") or 0
            if regime_rec is not None and n >= self.min_regime_sample:
                src = regime_rec
                evidence[m] = "OK"
            else:
                # 回退 global + shrinkage（不給 100% 權重）
                src = global_rec
                evidence[m] = "REGIME_EVIDENCE_INSUFFICIENT"
            stats.append({
                "model": m,
                "loss": src.get("loss"),
                "calibration_error": src.get("calibration_error"),
                "failure_rate": src.get("failure_rate"),
                "sample_size": src.get("sample_size"),
            })

        weights = compute_weights(stats, shrinkage_k=self.shrinkage_k)
        fallback = max(stats, key=lambda s: (s.get("sample_size") or 0))["model"] if stats else None
        return {
            "target": target, "horizon": horizon, "current_regime": current_regime,
            "eligible_models": sorted(weights.keys()),
            "model_weights": weights,
            "fallback_model": fallback,
            "evidence_state": evidence,
        }
