"""Phase 2G — Scenario Engine（E/F/G）。

scenario 必須由 feature/regime rule 或 model distribution 產生，不得由 LLM 隨意編數字。
scenario_weight 未經 OOS calibration 只能稱 scenario_weight + UNVALIDATED_WEIGHT。
"""
from __future__ import annotations

import numpy as np

from market_ai_hub.forecast.contract import CALIBRATED_PROBABILITY, UNVALIDATED_WEIGHT, ScenarioPath

# cross-asset 順序
ASSETS = ["NQ", "ES", "SOX", "USDJPY", "VIX", "US10Y", "^N225"]

# 每個 scenario type 的「整段 horizon」每資產 return shock（deterministic rule，非 LLM）
SCENARIO_SHOCKS: dict[str, dict[str, float]] = {
    "BASE":            {"NQ": 0.0, "ES": 0.0, "SOX": 0.0, "USDJPY": 0.0, "VIX": 0.0, "US10Y": 0.0, "^N225": 0.0},
    "RISK_ON":         {"NQ": 0.03, "ES": 0.02, "SOX": 0.04, "USDJPY": 0.02, "VIX": -0.15, "US10Y": 0.01, "^N225": 0.03},
    "RISK_OFF":        {"NQ": -0.03, "ES": -0.02, "SOX": -0.04, "USDJPY": -0.02, "VIX": 0.20, "US10Y": -0.01, "^N225": -0.03},
    "JPY_STRENGTHEN":  {"NQ": -0.01, "ES": -0.01, "SOX": -0.01, "USDJPY": -0.04, "VIX": 0.05, "US10Y": -0.005, "^N225": -0.02},
    "JPY_WEAKEN":      {"NQ": 0.01, "ES": 0.01, "SOX": 0.01, "USDJPY": 0.04, "VIX": -0.05, "US10Y": 0.005, "^N225": 0.02},
    "VOL_SHOCK":       {"NQ": -0.02, "ES": -0.02, "SOX": -0.03, "USDJPY": -0.01, "VIX": 0.35, "US10Y": -0.01, "^N225": -0.025},
    "RATES_SHOCK":     {"NQ": -0.02, "ES": -0.02, "SOX": -0.03, "USDJPY": 0.01, "VIX": 0.10, "US10Y": 0.05, "^N225": -0.015},
    "EVENT_SHOCK":     {"NQ": -0.04, "ES": -0.03, "SOX": -0.05, "USDJPY": -0.02, "VIX": 0.30, "US10Y": -0.02, "^N225": -0.04},
}

SCENARIO_TYPES = list(SCENARIO_SHOCKS.keys())


class ScenarioEngine:
    """由 current cross-asset state + regime + event + joint distribution 產生 ScenarioPath。

    權重預設 UNVALIDATED_WEIGHT；只有 OOS calibration 才 CALIBRATED_PROBABILITY。
    """

    def __init__(self, default_weight: float = 1.0, calibration: str = UNVALIDATED_WEIGHT) -> None:
        self.default_weight = default_weight
        self.calibration = calibration

    def generate(self, current_state: dict[str, float], scenario_types: list[str] | None = None,
                 horizon: int = 5, seed: int = 0) -> list[ScenarioPath]:
        types = scenario_types or SCENARIO_TYPES
        rng = np.random.default_rng(seed)
        paths: list[ScenarioPath] = []
        for st in types:
            shocks = SCENARIO_SHOCKS.get(st)
            if shocks is None:
                continue
            p = ScenarioPath(scenario_id=st, horizon=f"{horizon}d",
                             scenario_source="regime_rule", scenario_weight=self.default_weight,
                             weight_calibration_status=self.calibration)
            base = {a: float(current_state.get(a, 100.0)) for a in ASSETS}
            field_map = {"NQ": "NQ_path", "ES": "ES_path", "SOX": "SOX_path",
                         "USDJPY": "USDJPY_path", "VIX": "VIX_path", "US10Y": "rates_path"}
            for a in ASSETS:
                if a == "^N225":
                    continue
                total = shocks.get(a, 0.0)
                path = [base[a] * (1 + total * (s + 1) / horizon) for s in range(horizon)]
                setattr(p, field_map[a], path)
            # nikkei_distribution：確定性 terminal + 小 noise（可重現）
            nk = base["^N225"]
            nikkei_terms = [nk * (1 + shocks.get("^N225", 0.0) + rng.normal(0, 0.005)) for _ in range(20)]
            p.nikkei_distribution = [float(x) for x in nikkei_terms]
            paths.append(p)
        return paths
