"""Phase 3A — Price Map + Probability Map + Market State research foundation（versioned）。

RESEARCH ARCHITECTURE，不是 live strategy。所有 state / zone / probability 都是 research 語義；
`state_is_trade_instruction=false`，不得轉成 personalized order / stop / target。

核心原則：
- 底層模型負責計算；LLM / 主腦負責白話解讀，不得自己計算不存在的 probability。
- 不得預設 Gaussian（Gaussian 只能 BASELINE_DIAGNOSTIC）。
- terminal / touch / first_passage probability 必須分開。
- probability 必須帶 calibration_status；uncalibrated → public 不得稱 probability。
- model failure != 簡單 stop loss。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

PRICE_PROBABILITY_MAP_VERSION = "3A.1"
ZONE_POLICY_VERSION = "3A.1"
REGIME_VERSION = "3A.1"
MODEL_FAILURE_RULE_VERSION = "3A.1"
BENCHMARK_REGISTRY_VERSION = "3A.1"

# ── §B2：六個 research market states（不是 trade instruction）──
MARKET_STATES = (
    "BUY_ZONE", "NEUTRAL_ZONE", "PROFIT_ZONE",
    "BREAKOUT", "BREAKDOWN", "MODEL_FAILURE",
)

# ── §B4：regime layer ──
REGIMES = ("RANGE_LOW_VOL", "BULL_TREND", "BEAR_TREND", "HIGH_VOL_EVENT", "ABNORMAL_MODEL_FAILURE")

# ── §B15：calibration status ──
CALIBRATION_STATUSES = ("UNCALIBRATED", "CALIBRATING", "CALIBRATED", "INSUFFICIENT_EVIDENCE")

# ── §B9-B11：probability availability ──
PROBABILITY_AVAILABILITY = (
    "AVAILABLE",
    "NOT_AVAILABLE_INSUFFICIENT_DISTRIBUTION",
    "NOT_AVAILABLE",
)

# ── §B16：model failure status ──
MODEL_FAILURE_STATUSES = (
    "NORMAL", "COVERAGE_FAILURE", "PIT_DRIFT", "ERROR_REGIME_SHIFT",
    "PERSISTENT_DISTRIBUTION_MISS", "MODEL_FAILURE",
)

# ── §B12：distribution method（Gaussian 只能 baseline diagnostic）──
DISTRIBUTION_METHODS = ("EMPIRICAL", "MODEL_DISTRIBUTION", "GAUSSIAN_BASELINE_DIAGNOSTIC")


@dataclass
class DistributionDiagnostics:
    """§B13/§3A.1 §7：分布診斷。sample 不足 → INSUFFICIENT_EVIDENCE。

    method default = NOT_ESTABLISHED（sample_size=0 不得叫 EMPIRICAL）。
    """

    method: str = "NOT_ESTABLISHED"  # NOT_ESTABLISHED / EMPIRICAL / MODEL_DISTRIBUTION / GAUSSIAN_BASELINE_DIAGNOSTIC
    sample_size: int = 0
    skewness: float | None = None
    excess_kurtosis: float | None = None
    left_tail_mass: float | None = None
    right_tail_mass: float | None = None
    tail_asymmetry: float | None = None
    mode_count: int | None = None
    multimodality_status: str = "UNKNOWN"  # SINGLE_MODE / MULTIMODAL / UNKNOWN
    status: str = "INSUFFICIENT_EVIDENCE"

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass
class ZoneProbability:
    """§B8：zone probability。terminal / touch / first_passage 分開，各自 availability。"""

    zone: str
    terminal_probability: float | None = None
    touch_probability: float | None = None
    first_passage_probability: float | None = None
    availability_status: str = "NOT_AVAILABLE"
    method: str = ""
    calibration_status: str = "UNCALIBRATED"
    sample_count: int = 0
    uncertainty: dict = field(default_factory=dict)

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass
class ProbabilityMap:
    """§B8/§B9-§B11：Probability Map（versioned）。

    3A.1：無 distribution → calibration_status=INSUFFICIENT_EVIDENCE、distribution_method=NOT_ESTABLISHED。
    """

    instrument: str
    target_family: str
    horizon: str
    zones: list[ZoneProbability] = field(default_factory=list)
    calibration_status: str = "INSUFFICIENT_EVIDENCE"  # 無 distribution 時非 UNCALIBRATED
    distribution_method: str = "NOT_ESTABLISHED"
    version: str = PRICE_PROBABILITY_MAP_VERSION

    def public_view(self) -> dict:
        """public：uncalibrated → 不得輸出百分比（只給 availability）。"""
        out = {
            "instrument": self.instrument, "target_family": self.target_family,
            "horizon": self.horizon, "calibration_status": self.calibration_status,
            "distribution_method": self.distribution_method, "version": self.version,
            "zones": [],
        }
        calibrated = self.calibration_status == "CALIBRATED"
        for z in self.zones:
            d = {"zone": z.zone, "availability_status": z.availability_status}
            if calibrated and z.availability_status == "AVAILABLE":
                d["terminal_probability"] = z.terminal_probability
                d["touch_probability"] = z.touch_probability
                d["first_passage_probability"] = z.first_passage_probability
            else:
                d["note"] = "uncalibrated or insufficient distribution; no percentage provided"
            out["zones"].append(d)
        return out

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass
class ZonePolicy:
    """§B18：zone boundaries 是 versioned research parameter（可 OOS comparison），非金融真理。"""

    policy_id: str = "default"
    version: str = ZONE_POLICY_VERSION
    buy_zone_upper_quantile: float = 0.25
    profit_zone_lower_quantile: float = 0.75
    note: str = "research parameter; not a hardcoded financial truth; OOS comparison required"

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass
class PriceMap:
    """§B17：Price Map（versioned）。"""

    instrument: str
    target_family: str
    horizon: str
    reference_price: float | None = None
    distribution_center: dict = field(default_factory=dict)  # predictive_mean/median/mode
    zones: dict = field(default_factory=dict)
    zone_boundaries: dict = field(default_factory=dict)
    # 3A.1 §4-§6/§11：fail-closed defaults（未評估 ≠ NEUTRAL/RANGE/NORMAL）
    market_state: str | None = None
    market_state_status: str = "NOT_EVALUATED"  # NOT_EVALUATED / EVALUATED
    state_is_trade_instruction: bool = False  # §B2
    regime: str | None = None
    regime_status: str = "NOT_EVALUATED"  # NOT_EVALUATED / EVALUATED
    model_failure_state: str | None = None
    model_failure_evaluation_status: str = "NOT_EVALUATED"  # NOT_EVALUATED / EVALUATED
    confirmation_status: str = "NOT_ESTABLISHED"  # §B3
    data_provenance: dict = field(default_factory=dict)
    evidence_status: str = "NOT_YET_VALIDATED"
    distribution_diagnostics: DistributionDiagnostics = field(default_factory=DistributionDiagnostics)
    probability_map: ProbabilityMap | None = None
    reward_risk_reference: dict = field(default_factory=dict)
    actionability_status: str = "NOT_VALIDATED"  # §B19
    strategy_candidate: str = "NONE"  # §12：regime 未評估 → NONE
    profile: dict = field(default_factory=dict)
    version: str = PRICE_PROBABILITY_MAP_VERSION

    def model_dump(self) -> dict:
        d = asdict(self)
        return d


# ── §B5/§3A.1 §2：三個 first-class profiles（不得跨 family fallback）──
PROFILES = {
    "TAIWAN_STOCK_PROFILE": {
        "target_family": "TAIWAN_STOCK",
        "version": "3A.1",
        "structural_asymmetry": True,
        "note": "equity: structural asymmetry research allowed; long/short not symmetric",
    },
    "TAIWAN_INDEX_PROFILE": {
        "target_family": "TAIWAN_INDEX",
        "version": "3A.1",
        "forecast_reference_target": "TAIEX",
        "execution_instruments": ["TX", "MTX", "TMF"],
        "cash_index_executable": False,
        "execution_validation": "NOT_ESTABLISHED",
        "structural_asymmetry": True,
        "note": "TAIEX cash index forecast/reference (non-executable); execution via TX/MTX/TMF; "
                "equity-index semantics, asymmetric",
    },
    "OSAKA_MICRO_PROFILE": {
        "target_family": "OSAKA_MICRO",
        "version": "3A.1",
        "structural_asymmetry": False,
        "note": "futures: long/short more symmetric research assumption allowed",
    },
}

UNKNOWN_PROFILE = {
    "target_family": "UNKNOWN",
    "version": "3A.1",
    "status": "NOT_ESTABLISHED",
    "actionability": "NOT_VALIDATED",
    "note": "unknown target_family; no family-specific assumptions",
}

_FAMILY_TO_PROFILE = {
    "TAIWAN_STOCK": "TAIWAN_STOCK_PROFILE",
    "TAIWAN_INDEX": "TAIWAN_INDEX_PROFILE",
    "OSAKA_MICRO": "OSAKA_MICRO_PROFILE",
}


def profile_for(target_family: str) -> dict:
    """§3A.1 §1-§3：target-family 明確映射；未知 family → fail closed（不 fallback 大阪）。"""
    name = _FAMILY_TO_PROFILE.get(target_family)
    if name is None:
        raise ValueError(f"unknown target_family: {target_family!r} (no cross-family fallback)")
    return dict(PROFILES[name])


# ── §B20：strategy switching（candidate，不是 instruction）──
STRATEGY_SWITCHING = {
    "RANGE_LOW_VOL": "mean_reversion_candidate",
    "BULL_TREND": "breakout_momentum_candidate",
    "BEAR_TREND": "breakout_momentum_candidate",
    "HIGH_VOL_EVENT": "risk_reduction_candidate",
    "ABNORMAL_MODEL_FAILURE": "suspend_model_candidate",
}


def strategy_candidate_for(regime: str | None, regime_status: str = "NOT_EVALUATED") -> dict:
    """§12：regime 未評估 → NONE（不得因 default regime 給 mean_reversion_candidate）。"""
    if regime_status != "EVALUATED" or regime is None:
        return {"regime": regime, "regime_status": regime_status, "candidate": "NONE",
                "is_instruction": False, "note": "regime not evaluated; no candidate"}
    return {
        "regime": regime,
        "regime_status": regime_status,
        "candidate": STRATEGY_SWITCHING.get(regime, "NONE"),
        "is_instruction": False,
        "note": "research candidate only; not a trade instruction",
    }


# ── §B21：strategy competition framework（versioned benchmark registry；不宣稱 best）──
BENCHMARK_REGISTRY = {
    "version": BENCHMARK_REGISTRY_VERSION,
    "benchmarks": [
        {"id": "A", "name": "Buy & Hold"},
        {"id": "B", "name": "Moving Average"},
        {"id": "C", "name": "Breakout"},
        {"id": "D", "name": "Mean Reversion"},
        {"id": "E", "name": "Momentum"},
        {"id": "F", "name": "Price Forecast Only"},
        {"id": "G", "name": "Six-State Regime Strategy"},
    ],
    "note": "research hypothesis; OOS validation required; no BEST/OPTIMAL/PROVEN claim",
    "metrics": ["net_return", "sharpe", "sortino", "max_drawdown", "calmar", "profit_factor",
                "win_rate", "expectancy", "tail_risk", "turnover", "costs", "slippage"],
}


def six_state_research_view(
    target_family: str,
    instrument: str,
    horizon: str,
    reference_price: float | None,
    distribution_center: dict | None = None,
    zone_boundaries: dict | None = None,
    market_state: str | None = None,
    regime: str | None = None,
    model_failure_state: str | None = None,
    diagnostics: DistributionDiagnostics | None = None,
) -> PriceMap:
    """建立 research PriceMap（不含任何 trade instruction / 個人化下單）。

    3A.1：omitted argument → 保持 NOT_EVALUATED（不自動 NEUTRAL/RANGE/NORMAL）。
    只有明確傳入才驗證 enum 並標 EVALUATED。
    """
    if market_state is not None and market_state not in MARKET_STATES:
        raise ValueError(f"unknown market_state: {market_state}")
    if regime is not None and regime not in REGIMES:
        raise ValueError(f"unknown regime: {regime}")
    if model_failure_state is not None and model_failure_state not in MODEL_FAILURE_STATUSES:
        raise ValueError(f"unknown model_failure_state: {model_failure_state}")
    regime_status = "EVALUATED" if regime is not None else "NOT_EVALUATED"
    return PriceMap(
        instrument=instrument,
        target_family=target_family,
        horizon=horizon,
        reference_price=reference_price,
        distribution_center=distribution_center or {},
        zone_boundaries=zone_boundaries or {},
        market_state=market_state,
        market_state_status="EVALUATED" if market_state is not None else "NOT_EVALUATED",
        state_is_trade_instruction=False,
        regime=regime,
        regime_status=regime_status,
        model_failure_state=model_failure_state,
        model_failure_evaluation_status="EVALUATED" if model_failure_state is not None else "NOT_EVALUATED",
        distribution_diagnostics=diagnostics or DistributionDiagnostics(),
        strategy_candidate=strategy_candidate_for(regime, regime_status)["candidate"],
        profile=profile_for(target_family),
    )


def empty_price_map(
    instrument: str,
    target_family: str,
    horizon: str,
    reference_price: float | None = None,
) -> PriceMap:
    """§9：canonical fail-closed PriceMap（只有 instrument/family/horizon/reference price）。"""
    return six_state_research_view(
        target_family=target_family, instrument=instrument, horizon=horizon,
        reference_price=reference_price,
    )


def benchmark_registry() -> dict:
    return dict(BENCHMARK_REGISTRY)


def probability_from_quantiles_only(zones: list[str], instrument: str = "", target_family: str = "",
                                    horizon: str = "") -> ProbabilityMap:
    """§B9：只靠 p10/p50/p90 不得推導完整 zone probability。

    回 ProbabilityMap，所有 zone 標 NOT_AVAILABLE_INSUFFICIENT_DISTRIBUTION。
    """
    return ProbabilityMap(
        instrument=instrument, target_family=target_family, horizon=horizon,
        zones=[ZoneProbability(zone=z, availability_status="NOT_AVAILABLE_INSUFFICIENT_DISTRIBUTION",
                               calibration_status="INSUFFICIENT_EVIDENCE", method="QUANTILES_ONLY")
               for z in zones],
        calibration_status="INSUFFICIENT_EVIDENCE",
        distribution_method="QUANTILES_ONLY",
    )
