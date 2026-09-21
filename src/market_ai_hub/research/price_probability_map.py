"""Phase 3A.2 — Typed Evidence Contract + Calibration Safety Closure + Distribution Schema Consistency
+ Evaluation Provenance（versioned schema）。

RESEARCH ARCHITECTURE，不是 live strategy。核心：
- Enum input != evidence：EVALUATED 需 machine-verifiable evidence object，不能只靠 caller 填字串。
- Typed probability：terminal / touch / first_passage 各自 status / calibration / sample / reason。
- Available is not Validated：public 只有 machine contract 全通過才輸出百分比。
- Quantile boundary != Zone Probability。
- 不得預設 Gaussian；不得用 classifier calibration 替 price distribution 背書。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import Any

PRICE_PROBABILITY_MAP_VERSION = "3A.2"
ZONE_POLICY_VERSION = "3A.2"
REGIME_VERSION = "3A.2"
MODEL_FAILURE_RULE_VERSION = "3A.2"
BENCHMARK_REGISTRY_VERSION = "3A.2"

# ── §1 canonical distribution methods（含 runtime 實際使用的 NOT_ESTABLISHED / QUANTILES_ONLY）──
DISTRIBUTION_METHODS = (
    "NOT_ESTABLISHED", "QUANTILES_ONLY", "EMPIRICAL", "MODEL_DISTRIBUTION",
    "GAUSSIAN_BASELINE_DIAGNOSTIC",
)

# ── §2 canonical distribution capability ──
DISTRIBUTION_CAPABILITIES = ("NONE", "QUANTILES_ONLY", "TERMINAL_SAMPLES", "PATH_SAMPLES", "FULL_DISTRIBUTION")

# ── §3 capability matrix（caller 不需自己猜）──
CAPABILITY_MATRIX = {
    "NONE": {"terminal": False, "touch": False, "first_passage": False},
    "QUANTILES_ONLY": {"terminal": False, "touch": False, "first_passage": False},
    "TERMINAL_SAMPLES": {"terminal": True, "touch": False, "first_passage": False},
    "PATH_SAMPLES": {"terminal": True, "touch": True, "first_passage": True},
    "FULL_DISTRIBUTION": {"terminal": True, "touch": True, "first_passage": True},
}

# ── §15 canonical evaluation statuses ──
EVALUATION_STATUSES = ("NOT_EVALUATED", "UNVERIFIED", "EVALUATED", "INSUFFICIENT_EVIDENCE", "ERROR")

# ── §6 typed probability availability ──
PROBABILITY_STATUSES = (
    "AVAILABLE", "NOT_AVAILABLE_INSUFFICIENT_DISTRIBUTION", "NOT_AVAILABLE_UNCALIBRATED",
    "NOT_AVAILABLE_INSUFFICIENT_SAMPLE", "NOT_AVAILABLE_MISSING_PROVENANCE", "NOT_APPLICABLE",
)

# ── §27 reason codes ──
REASON_CODES = (
    "NO_DISTRIBUTION", "QUANTILES_ONLY", "UNCALIBRATED", "INSUFFICIENT_SAMPLE",
    "MISSING_PROVENANCE", "UNSUPPORTED_CAPABILITY", "TARGET_SCOPE_MISMATCH",
    "HORIZON_SCOPE_MISMATCH", "INVALID_VALUE", "NOT_EVALUATED",
)

# ── §23 calibration domain（price distribution vs direction classifier 分開）──
CALIBRATION_DOMAINS = ("PRICE_DISTRIBUTION", "DIRECTION_CLASSIFICATION")

# ── §15/§8 calibration statuses ──
CALIBRATION_STATUSES = ("UNCALIBRATED", "CALIBRATING", "CALIBRATED", "INSUFFICIENT_EVIDENCE")

# ── §9 sample sufficiency ──
SAMPLE_SUFFICIENCY = ("SUFFICIENT", "INSUFFICIENT", "NOT_EVALUATED")

# ── §25 calibration scope ──
CALIBRATION_SCOPES = ("SINGLE_INSTRUMENT", "PANEL", "GLOBAL")

# ── §B2/§B4/§B16 enums ──
MARKET_STATES = ("BUY_ZONE", "NEUTRAL_ZONE", "PROFIT_ZONE", "BREAKOUT", "BREAKDOWN", "MODEL_FAILURE")
REGIMES = ("RANGE_LOW_VOL", "BULL_TREND", "BEAR_TREND", "HIGH_VOL_EVENT", "ABNORMAL_MODEL_FAILURE")
MODEL_FAILURE_STATUSES = ("NORMAL", "COVERAGE_FAILURE", "PIT_DRIFT", "ERROR_REGIME_SHIFT",
                          "PERSISTENT_DISTRIBUTION_MISS", "MODEL_FAILURE")
DISTRIBUTION_METHODS_LEGACY = DISTRIBUTION_METHODS  # compat alias


def _valid_prob(p: Any) -> bool:
    """§7：0.0 <= p <= 1.0 且 finite（禁 NaN/inf）。"""
    try:
        f = float(p)
    except (TypeError, ValueError):
        return False
    return math.isfinite(f) and 0.0 <= f <= 1.0


def capability_supports(capability: str, probability_type: str) -> bool:
    """§3：capability matrix。probability_type ∈ terminal/touch/first_passage。"""
    return bool(CAPABILITY_MATRIX.get(capability, {}).get(probability_type, False))


# ── §9/§10/§11：provenance + evidence ──
@dataclass
class ProbabilityProvenance:
    model_id: str = ""
    model_version: str = ""
    dataset_version: str = ""
    feature_version: str = ""
    protocol_version: str = ""
    distribution_method: str = ""
    calibration_method: str = ""
    calibration_version: str = ""
    evaluation_window: str = ""
    generated_at: str = ""
    target_family: str = ""
    instrument: str = ""
    horizon: str = ""

    def is_complete(self) -> bool:
        required = ("model_id", "model_version", "dataset_version", "feature_version",
                    "protocol_version", "distribution_method", "calibration_method",
                    "calibration_version", "evaluation_window", "generated_at",
                    "target_family", "instrument", "horizon")
        return all(getattr(self, k) for k in required)

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass
class EvaluationEvidence:
    """§11：Market State / Regime / Model Failure 的 machine-verifiable evidence。"""

    status: str = "NOT_EVALUATED"  # EVALUATION_STATUSES
    method: str = ""
    method_version: str = ""
    data_version: str = ""
    sample_count: int = 0
    evaluated_at: str = ""
    source: str = ""
    notes: str = ""

    def is_valid(self) -> bool:
        return self.status in ("VALID", "ESTABLISHED", "EVALUATED") and bool(self.method) and self.sample_count > 0

    def model_dump(self) -> dict:
        return asdict(self)


# ── §4/§5/§6/§8/§9/§27：typed probability ──
@dataclass
class ProbabilityValue:
    """單一 typed probability（terminal / touch / first_passage 各自獨立）。"""

    value: float | None = None
    status: str = "NOT_APPLICABLE"                  # PROBABILITY_STATUSES
    calibration_status: str = "INSUFFICIENT_EVIDENCE"
    calibration_domain: str = "PRICE_DISTRIBUTION"  # §23
    sample_count: int = 0
    effective_sample_count: int = 0
    minimum_required_sample: int = 0
    sample_sufficiency_status: str = "NOT_EVALUATED"
    reason_codes: list[str] = field(default_factory=list)

    def is_public_available(self, *, map_calibration: str, capability: str, probability_type: str,
                            provenance: ProbabilityProvenance | None) -> bool:
        """§4/§26：public 只有所有 machine gate 通過才輸出。"""
        if not capability_supports(capability, probability_type):
            return False
        if self.status != "AVAILABLE":
            return False
        if self.value is None or not _valid_prob(self.value):
            return False
        if map_calibration != "CALIBRATED":
            return False
        if self.calibration_status != "CALIBRATED":
            return False
        if self.sample_sufficiency_status != "SUFFICIENT":
            return False
        if provenance is None or not provenance.is_complete():
            return False
        return True

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass
class ZoneProbability:
    """§5/§6：zone 的三種 probability 各自 typed。"""

    zone: str
    terminal: ProbabilityValue = field(default_factory=ProbabilityValue)
    touch: ProbabilityValue = field(default_factory=ProbabilityValue)
    first_passage: ProbabilityValue = field(default_factory=ProbabilityValue)
    # backward-compat（deprecated；不供新邏輯）
    availability_status: str = "NOT_AVAILABLE"
    calibration_status: str = "INSUFFICIENT_EVIDENCE"
    method: str = ""

    @property
    def terminal_probability(self):
        """compat alias（deprecated；canonical = terminal.value）。"""
        return self.terminal.value

    @property
    def touch_probability(self):
        """compat alias（deprecated）。"""
        return self.touch.value

    @property
    def first_passage_probability(self):
        """compat alias（deprecated）。"""
        return self.first_passage.value

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass
class DistributionRecord:
    """§1/§2/§9/§18/§19/§20：distribution 的 canonical record。"""

    method: str = "NOT_ESTABLISHED"
    capability: str = "NONE"
    is_full_distribution: bool = False
    sample_count: int = 0
    effective_sample_count: int = 0
    minimum_required_sample: int = 0
    sample_sufficiency_status: str = "NOT_EVALUATED"
    target_family: str = ""
    instrument: str = ""
    horizon: str = ""
    path_count: int = 0
    steps_per_path: int = 0
    target_market_calendar: str = ""
    session_semantics: str = ""
    bar_frequency: str = ""
    generation_method: str = ""

    def model_dump(self) -> dict:
        return asdict(self)


def quantiles_only_distribution(target_family: str = "", instrument: str = "",
                                horizon: str = "") -> DistributionRecord:
    """§18：p10/p50/p90 → QUANTILES_ONLY record（is_full_distribution=false, capability=QUANTILES_ONLY）。"""
    return DistributionRecord(
        method="QUANTILES_ONLY", capability="QUANTILES_ONLY", is_full_distribution=False,
        target_family=target_family, instrument=instrument, horizon=horizon,
    )


@dataclass
class ProbabilityMap:
    """§4/§26：Probability Map（versioned 3A.2）。public_view fail-closed。"""

    instrument: str
    target_family: str
    horizon: str
    zones: list[ZoneProbability] = field(default_factory=list)
    distribution: DistributionRecord = field(default_factory=DistributionRecord)
    calibration_status: str = "INSUFFICIENT_EVIDENCE"
    calibration_scope: str = "SINGLE_INSTRUMENT"  # §25
    provenance: ProbabilityProvenance | None = None
    version: str = PRICE_PROBABILITY_MAP_VERSION

    @property
    def distribution_method(self):
        """compat alias（deprecated；canonical = distribution.method）。"""
        return self.distribution.method

    def public_view(self) -> dict:
        out = {
            "instrument": self.instrument, "target_family": self.target_family,
            "horizon": self.horizon, "version": self.version,
            "calibration_status": self.calibration_status,
            "distribution_method": self.distribution.method,
            "distribution_capability": self.distribution.capability,
            "is_full_distribution": self.distribution.is_full_distribution,
            "zones": [],
        }
        for z in self.zones:
            zd: dict = {"zone": z.zone}
            for ptype, pv in (("terminal", z.terminal), ("touch", z.touch), ("first_passage", z.first_passage)):
                if pv.is_public_available(map_calibration=self.calibration_status,
                                          capability=self.distribution.capability,
                                          probability_type=ptype, provenance=self.provenance):
                    zd[f"{ptype}_probability"] = pv.value
                    zd[f"{ptype}_status"] = "AVAILABLE"
                else:
                    zd[f"{ptype}_status"] = pv.status if pv.status != "NOT_APPLICABLE" else "NOT_AVAILABLE"
                    zd[f"{ptype}_reason_codes"] = pv.reason_codes or ["NO_DISTRIBUTION"]
            out["zones"].append(zd)
        return out

    def model_dump(self) -> dict:
        d = asdict(self)
        return d


@dataclass
class ZonePolicy:
    policy_id: str = "default"
    version: str = ZONE_POLICY_VERSION
    buy_zone_upper_quantile: float = 0.25
    profit_zone_lower_quantile: float = 0.75
    note: str = "research parameter; not a hardcoded financial truth; quantile boundary != zone probability"

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass
class PriceMap:
    """§12-§14/§17：Price Map（versioned 3A.2）。state/regime/model_failure 需 evidence。"""

    instrument: str
    target_family: str
    horizon: str
    reference_price: float | None = None
    distribution_center: dict = field(default_factory=dict)
    zones: dict = field(default_factory=dict)
    zone_boundaries: dict = field(default_factory=dict)
    market_state: str | None = None
    market_state_status: str = "NOT_EVALUATED"
    market_state_evidence: EvaluationEvidence | None = None
    state_is_trade_instruction: bool = False
    regime: str | None = None
    regime_status: str = "NOT_EVALUATED"
    regime_evidence: EvaluationEvidence | None = None
    model_failure_state: str | None = None
    model_failure_evaluation_status: str = "NOT_EVALUATED"
    model_failure_evidence: EvaluationEvidence | None = None
    confirmation_status: str = "NOT_ESTABLISHED"
    data_provenance: dict = field(default_factory=dict)
    evidence_status: str = "NOT_YET_VALIDATED"
    distribution_diagnostics: "DistributionDiagnostics" = None  # set in __post_init__
    probability_map: ProbabilityMap | None = None
    reward_risk_reference: dict = field(default_factory=dict)
    actionability_status: str = "NOT_VALIDATED"
    strategy_candidate: str = "NONE"
    profile: dict = field(default_factory=dict)
    version: str = PRICE_PROBABILITY_MAP_VERSION

    def __post_init__(self):
        if self.distribution_diagnostics is None:
            self.distribution_diagnostics = DistributionDiagnostics()

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass
class DistributionDiagnostics:
    method: str = "NOT_ESTABLISHED"
    sample_size: int = 0
    skewness: float | None = None
    excess_kurtosis: float | None = None
    left_tail_mass: float | None = None
    right_tail_mass: float | None = None
    tail_asymmetry: float | None = None
    mode_count: int | None = None
    multimodality_status: str = "UNKNOWN"
    status: str = "INSUFFICIENT_EVIDENCE"

    def model_dump(self) -> dict:
        return asdict(self)


# ── profiles（3A.1 保留）──
PROFILES = {
    "TAIWAN_STOCK_PROFILE": {
        "target_family": "TAIWAN_STOCK", "version": "3A.2", "structural_asymmetry": True,
        "note": "equity: structural asymmetry research allowed; long/short not symmetric",
    },
    "TAIWAN_INDEX_PROFILE": {
        "target_family": "TAIWAN_INDEX", "version": "3A.2",
        "forecast_reference_target": "TAIEX", "execution_instruments": ["TX", "MTX", "TMF"],
        "cash_index_executable": False, "execution_validation": "NOT_ESTABLISHED",
        "structural_asymmetry": True,
        "note": "TAIEX cash index forecast/reference (non-executable); execution via TX/MTX/TMF; "
                "equity-index semantics, asymmetric",
    },
    "OSAKA_MICRO_PROFILE": {
        "target_family": "OSAKA_MICRO", "version": "3A.2", "structural_asymmetry": False,
        "note": "futures: long/short more symmetric research assumption allowed",
    },
}

UNKNOWN_PROFILE = {"target_family": "UNKNOWN", "version": "3A.2", "status": "NOT_ESTABLISHED",
                   "actionability": "NOT_VALIDATED", "note": "unknown target_family; no family-specific assumptions"}

_FAMILY_TO_PROFILE = {"TAIWAN_STOCK": "TAIWAN_STOCK_PROFILE", "TAIWAN_INDEX": "TAIWAN_INDEX_PROFILE",
                      "OSAKA_MICRO": "OSAKA_MICRO_PROFILE"}


def profile_for(target_family: str) -> dict:
    name = _FAMILY_TO_PROFILE.get(target_family)
    if name is None:
        raise ValueError(f"unknown target_family: {target_family!r} (no cross-family fallback)")
    return dict(PROFILES[name])


STRATEGY_SWITCHING = {
    "RANGE_LOW_VOL": "mean_reversion_candidate",
    "BULL_TREND": "breakout_momentum_candidate",
    "BEAR_TREND": "breakout_momentum_candidate",
    "HIGH_VOL_EVENT": "risk_reduction_candidate",
    "ABNORMAL_MODEL_FAILURE": "suspend_model_candidate",
}


def strategy_candidate_for(regime: str | None, regime_status: str = "NOT_EVALUATED",
                           regime_evidence: EvaluationEvidence | None = None) -> dict:
    """§16：只有 regime_status=EVALUATED 且 evidence valid 才產生 candidate。"""
    valid = regime_status == "EVALUATED" and regime is not None and (
        regime_evidence is not None and regime_evidence.is_valid())
    if not valid:
        return {"regime": regime, "regime_status": regime_status, "candidate": "NONE",
                "is_instruction": False, "note": "regime not evaluated/verified; no candidate"}
    return {"regime": regime, "regime_status": regime_status,
            "candidate": STRATEGY_SWITCHING.get(regime, "NONE"), "is_instruction": False,
            "note": "research candidate only; not a trade instruction"}


def _evaluated_status(value: str | None, evidence: EvaluationEvidence | None) -> str:
    """§12-§15：有值但無 valid evidence → UNVERIFIED；無值 → NOT_EVALUATED。"""
    if value is None:
        return "NOT_EVALUATED"
    if evidence is not None and evidence.is_valid():
        return "EVALUATED"
    return "UNVERIFIED"


def six_state_research_view(
    target_family: str,
    instrument: str,
    horizon: str,
    reference_price: float | None,
    distribution_center: dict | None = None,
    zone_boundaries: dict | None = None,
    market_state: str | None = None,
    market_state_evidence: EvaluationEvidence | None = None,
    regime: str | None = None,
    regime_evidence: EvaluationEvidence | None = None,
    model_failure_state: str | None = None,
    model_failure_evidence: EvaluationEvidence | None = None,
    diagnostics: DistributionDiagnostics | None = None,
) -> PriceMap:
    """建立 research PriceMap。enum 字串 != evidence：EVALUATED 需 valid evidence。"""
    if market_state is not None and market_state not in MARKET_STATES:
        raise ValueError(f"unknown market_state: {market_state}")
    if regime is not None and regime not in REGIMES:
        raise ValueError(f"unknown regime: {regime}")
    if model_failure_state is not None and model_failure_state not in MODEL_FAILURE_STATUSES:
        raise ValueError(f"unknown model_failure_state: {model_failure_state}")

    ms_status = _evaluated_status(market_state, market_state_evidence)
    rg_status = _evaluated_status(regime, regime_evidence)
    mf_status = _evaluated_status(model_failure_state, model_failure_evidence)

    return PriceMap(
        instrument=instrument, target_family=target_family, horizon=horizon,
        reference_price=reference_price, distribution_center=distribution_center or {},
        zone_boundaries=zone_boundaries or {},
        market_state=market_state, market_state_status=ms_status, market_state_evidence=market_state_evidence,
        state_is_trade_instruction=False,
        regime=regime, regime_status=rg_status, regime_evidence=regime_evidence,
        model_failure_state=model_failure_state, model_failure_evaluation_status=mf_status,
        model_failure_evidence=model_failure_evidence,
        distribution_diagnostics=diagnostics or DistributionDiagnostics(),
        strategy_candidate=strategy_candidate_for(regime, rg_status, regime_evidence)["candidate"],
        profile=profile_for(target_family),
    )


def empty_price_map(instrument: str, target_family: str, horizon: str,
                    reference_price: float | None = None) -> PriceMap:
    return six_state_research_view(target_family=target_family, instrument=instrument,
                                   horizon=horizon, reference_price=reference_price)


BENCHMARK_REGISTRY = {
    "version": BENCHMARK_REGISTRY_VERSION,
    "benchmarks": [
        {"id": "A", "name": "Buy & Hold"}, {"id": "B", "name": "Moving Average"},
        {"id": "C", "name": "Breakout"}, {"id": "D", "name": "Mean Reversion"},
        {"id": "E", "name": "Momentum"}, {"id": "F", "name": "Price Forecast Only"},
        {"id": "G", "name": "Six-State Regime Strategy"},
    ],
    "note": "research hypothesis; OOS validation required; no BEST/OPTIMAL/PROVEN claim",
    "metrics": ["net_return", "sharpe", "sortino", "max_drawdown", "calmar", "profit_factor",
                "win_rate", "expectancy", "tail_risk", "turnover", "costs", "slippage"],
}


def benchmark_registry() -> dict:
    return dict(BENCHMARK_REGISTRY)


def probability_from_quantiles_only(zones: list[str], instrument: str = "", target_family: str = "",
                                    horizon: str = "") -> ProbabilityMap:
    """§18：只靠 p10/p50/p90 → 全部 probability NOT_AVAILABLE（QUANTILES_ONLY）。"""
    def _pv() -> ProbabilityValue:
        return ProbabilityValue(status="NOT_AVAILABLE_INSUFFICIENT_DISTRIBUTION",
                                calibration_status="INSUFFICIENT_EVIDENCE",
                                sample_sufficiency_status="NOT_EVALUATED",
                                reason_codes=["QUANTILES_ONLY"])

    return ProbabilityMap(
        instrument=instrument, target_family=target_family, horizon=horizon,
        zones=[ZoneProbability(zone=z, terminal=_pv(), touch=_pv(), first_passage=_pv(),
                               availability_status="NOT_AVAILABLE", method="QUANTILES_ONLY")
               for z in zones],
        distribution=quantiles_only_distribution(target_family, instrument, horizon),
        calibration_status="INSUFFICIENT_EVIDENCE",
    )


# ── §22 calibration metrics interface（不 fit）──
def calibration_metrics_contract() -> dict:
    return {
        "domain": "PRICE_DISTRIBUTION",
        "metrics": ["coverage_calibration", "pit_diagnostics", "brier_score",
                    "log_score", "reliability_bins", "calibration_error"],
        "status": "INTERFACE_ONLY_NOT_FITTED",
    }
