"""Phase 3A.2.1 — Adversarial Probability Contract Closure + Scope Enforcement + Sample Sufficiency
Enforcement + Status/Reason Consistency + Path Capability Semantics（versioned schema）。

RESEARCH ARCHITECTURE，不是 live strategy。核心：
- Scope enforced：provenance target_family/instrument/horizon 必須與 map 一致（canonical normalized）。
- Numeric sample gate：minimum_required_sample > 0 且 sample_count/effective_sample_count >= minimum。
- Public status 由 machine gates 推導（不 echo internal status）。
- Reason codes truthful（deterministic gate 順序 + 累積）。
- Terminal distribution != path distribution（touch/first_passage 需 path capability + metadata）。
- Evaluation enum 統一（VALID/ESTABLISHED normalize 到 EVALUATED；未知 reject）。
- Method-capability consistency enforced。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import Any

PRICE_PROBABILITY_MAP_VERSION = "3A.2.2"
ZONE_POLICY_VERSION = "3A.2.2"
REGIME_VERSION = "3A.2.2"
MODEL_FAILURE_RULE_VERSION = "3A.2.2"
BENCHMARK_REGISTRY_VERSION = "3A.2.2"

# ── canonical distribution methods ──
DISTRIBUTION_METHODS = (
    "NOT_ESTABLISHED", "QUANTILES_ONLY", "EMPIRICAL", "MODEL_DISTRIBUTION",
    "GAUSSIAN_BASELINE_DIAGNOSTIC",
)

# ── §16 canonical capability（terminal distribution != path distribution）──
DISTRIBUTION_CAPABILITIES = (
    "NONE", "QUANTILES_ONLY", "TERMINAL_SAMPLES", "TERMINAL_DISTRIBUTION",
    "PATH_SAMPLES", "PATH_DISTRIBUTION", "FULL_DISTRIBUTION",  # FULL_DISTRIBUTION = deprecated alias
)

# ── §16 capability matrix（FULL_DISTRIBUTION 不得自行代表 path capability）──
CAPABILITY_MATRIX = {
    "NONE": {"terminal": False, "touch": False, "first_passage": False},
    "QUANTILES_ONLY": {"terminal": False, "touch": False, "first_passage": False},
    "TERMINAL_SAMPLES": {"terminal": True, "touch": False, "first_passage": False},
    "TERMINAL_DISTRIBUTION": {"terminal": True, "touch": False, "first_passage": False},
    "PATH_SAMPLES": {"terminal": True, "touch": True, "first_passage": True},
    "PATH_DISTRIBUTION": {"terminal": True, "touch": True, "first_passage": True},
    "FULL_DISTRIBUTION": {"terminal": True, "touch": False, "first_passage": False},  # deprecated
}

# ── §15 method-capability rules ──
METHOD_CAPABILITY_RULES = {
    "NOT_ESTABLISHED": {"NONE"},
    "QUANTILES_ONLY": {"QUANTILES_ONLY"},
    "EMPIRICAL": {"TERMINAL_SAMPLES", "TERMINAL_DISTRIBUTION", "PATH_SAMPLES", "PATH_DISTRIBUTION"},
    "MODEL_DISTRIBUTION": {"TERMINAL_DISTRIBUTION", "PATH_DISTRIBUTION"},
    # §15：Gaussian 只能 baseline diagnostic，不可作 production/public calibrated source
    "GAUSSIAN_BASELINE_DIAGNOSTIC": {"NONE", "QUANTILES_ONLY"},
}

# ── evaluation statuses（§11/§12 單一 canonical model）──
EVALUATION_STATUSES = ("NOT_EVALUATED", "UNVERIFIED", "EVALUATED", "INSUFFICIENT_EVIDENCE", "ERROR")
_EVAL_ALIASES = {"VALID": "EVALUATED", "ESTABLISHED": "EVALUATED"}

# ── probability availability statuses（§8）──
PROBABILITY_STATUSES = (
    "AVAILABLE",
    "NOT_AVAILABLE_INSUFFICIENT_DISTRIBUTION",
    "NOT_AVAILABLE_UNCALIBRATED",
    "NOT_AVAILABLE_INSUFFICIENT_SAMPLE",
    "NOT_AVAILABLE_MISSING_PROVENANCE",
    "NOT_AVAILABLE_SCOPE_MISMATCH",
    "NOT_AVAILABLE_UNSUPPORTED_CAPABILITY",
    "NOT_AVAILABLE_INVALID_VALUE",
    "NOT_APPLICABLE",
)

# ── §9 reason codes（truthful）──
REASON_CODES = (
    "NO_DISTRIBUTION", "QUANTILES_ONLY", "UNCALIBRATED", "INSUFFICIENT_SAMPLE",
    "MISSING_PROVENANCE", "UNSUPPORTED_CAPABILITY", "TARGET_SCOPE_MISMATCH",
    "HORIZON_SCOPE_MISMATCH", "INSTRUMENT_SCOPE_MISMATCH", "DISTRIBUTION_METHOD_MISMATCH",
    "CALIBRATION_PROVENANCE_MISSING", "CALIBRATION_DOMAIN_MISMATCH", "INVALID_VALUE",
    "NOT_EVALUATED", "METHOD_CAPABILITY_MISMATCH", "PATH_METADATA_MISSING",
    # ── 3A.2.2 ──
    "MISSING_DISTRIBUTION_SCOPE", "DISTRIBUTION_TARGET_SCOPE_MISMATCH",
    "DISTRIBUTION_INSTRUMENT_SCOPE_MISMATCH", "DISTRIBUTION_HORIZON_SCOPE_MISMATCH",
    "DISTRIBUTION_INSUFFICIENT_SAMPLE", "PROBABILITY_SAMPLE_EXCEEDS_SOURCE",
    "DISTRIBUTION_IDENTITY_MISMATCH", "MISSING_DISTRIBUTION_IDENTITY",
    "MARKET_CALENDAR_MISMATCH", "SESSION_SEMANTICS_MISMATCH", "FORECAST_SCOPE_MISMATCH",
    "MISSING_INSTRUMENT_ROLE", "UNKNOWN_MARKET_SEMANTICS",
    "CALIBRATION_SCOPE_EVIDENCE_MISSING", "CALIBRATION_UNIVERSE_MISMATCH",
    "CALIBRATION_GLOBAL_SCOPE_MISMATCH",
)

CALIBRATION_DOMAINS = ("PRICE_DISTRIBUTION", "DIRECTION_CLASSIFICATION")
CALIBRATION_STATUSES = ("UNCALIBRATED", "CALIBRATING", "CALIBRATED", "INSUFFICIENT_EVIDENCE")
SAMPLE_SUFFICIENCY = ("SUFFICIENT", "INSUFFICIENT", "NOT_EVALUATED")
CALIBRATION_SCOPES = ("SINGLE_INSTRUMENT", "PANEL", "GLOBAL")

# ── 3A.2.2 §10-§14：instrument role / forecast scope（沿用現有 target semantics 語彙）──
INSTRUMENT_ROLES = ("DIRECT", "PROXY")
FORECAST_SCOPES = ("DIRECT_INSTRUMENT", "PROXY_MODEL_REFERENCE")
_SAMPLING_CAPABILITIES = ("TERMINAL_SAMPLES", "PATH_SAMPLES")

# canonical market semantics：family + role → (calendar, session_semantics)。
# calendar 名稱沿用 services/calendar.py（XTAI=TWSE、XTKS=TSE cash、OSE_DERIVATIVES=OSE）。
# ponytail: 小型 canonical 表；若 target 種類膨脹再改讀 config/primary_targets.yaml。
_MARKET_SEMANTICS = {
    ("TAIWAN_STOCK", "DIRECT"): ("XTAI", "day"),
    ("TAIWAN_INDEX", "DIRECT"): ("XTAI", "day"),
    ("OSAKA_MICRO", "DIRECT"): ("OSE_DERIVATIVES", "day+night"),
    ("OSAKA_MICRO", "PROXY"): ("XTKS", "day"),
}

MARKET_STATES = ("BUY_ZONE", "NEUTRAL_ZONE", "PROFIT_ZONE", "BREAKOUT", "BREAKDOWN", "MODEL_FAILURE")
REGIMES = ("RANGE_LOW_VOL", "BULL_TREND", "BEAR_TREND", "HIGH_VOL_EVENT", "ABNORMAL_MODEL_FAILURE")
MODEL_FAILURE_STATUSES = ("NORMAL", "COVERAGE_FAILURE", "PIT_DRIFT", "ERROR_REGIME_SHIFT",
                          "PERSISTENT_DISTRIBUTION_MISS", "MODEL_FAILURE")

_PATH_CAPABILITIES = ("PATH_SAMPLES", "PATH_DISTRIBUTION")


def _valid_prob(p: Any) -> bool:
    try:
        f = float(p)
    except (TypeError, ValueError):
        return False
    return math.isfinite(f) and 0.0 <= f <= 1.0


# ── §23/§24 normalization ──
def normalize_horizon(h: str) -> str:
    return (h or "").strip().lower()


def normalize_family(f: str) -> str:
    return (f or "").strip().upper()


def normalize_instrument(i: str) -> str:
    """3706 / 3706.TW → 3706.TW；其餘 strip upper。"""
    s = (i or "").strip().upper()
    if s.isdigit():
        return f"{s}.TW"
    return s


def capability_supports(capability: str, probability_type: str) -> bool:
    return bool(CAPABILITY_MATRIX.get(capability, {}).get(probability_type, False))


def method_capability_ok(method: str, capability: str) -> bool:
    allowed = METHOD_CAPABILITY_RULES.get(method)
    return allowed is not None and capability in allowed


# ── §2 provenance ──
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
    # ── 3A.2.2 §17：可追溯使用的 DistributionRecord ──
    distribution_id: str = ""
    distribution_version: str = ""

    def is_complete(self) -> bool:
        required = ("model_id", "model_version", "dataset_version", "feature_version",
                    "protocol_version", "distribution_method", "calibration_method",
                    "calibration_version", "evaluation_window", "generated_at",
                    "target_family", "instrument", "horizon")
        return all(getattr(self, k) for k in required)

    def model_dump(self) -> dict:
        return asdict(self)


def validate_provenance_scope(prov: ProbabilityProvenance | None, target_family: str,
                              instrument: str, horizon: str) -> list[str]:
    """§1/§2：provenance scope 必須與 map 一致（canonical normalized）。回 reason codes。"""
    if prov is None:
        return ["MISSING_PROVENANCE"]
    reasons: list[str] = []
    if normalize_family(prov.target_family) != normalize_family(target_family):
        reasons.append("TARGET_SCOPE_MISMATCH")
    if normalize_instrument(prov.instrument) != normalize_instrument(instrument):
        reasons.append("INSTRUMENT_SCOPE_MISMATCH")
    if normalize_horizon(prov.horizon) != normalize_horizon(horizon):
        reasons.append("HORIZON_SCOPE_MISMATCH")
    return reasons


# ── 3A.2.2 §2/§3 distribution scope ──
def validate_distribution_scope(dist: "DistributionRecord", target_family: str,
                                instrument: str, horizon: str) -> list[str]:
    """§2/§3：map == provenance == distribution 三方 scope（canonical normalized）。"""
    if dist.capability in ("NONE", "QUANTILES_ONLY"):
        return []  # 無 public probability capability，不需 scope
    if not (dist.target_family and dist.instrument and dist.horizon):
        return ["MISSING_DISTRIBUTION_SCOPE"]
    reasons: list[str] = []
    if normalize_family(dist.target_family) != normalize_family(target_family):
        reasons.append("DISTRIBUTION_TARGET_SCOPE_MISMATCH")
    if normalize_instrument(dist.instrument) != normalize_instrument(instrument):
        reasons.append("DISTRIBUTION_INSTRUMENT_SCOPE_MISMATCH")
    if normalize_horizon(dist.horizon) != normalize_horizon(horizon):
        reasons.append("DISTRIBUTION_HORIZON_SCOPE_MISMATCH")
    return reasons


def validate_distribution_market_semantics(dist: "DistributionRecord") -> list[str]:
    """§10-§15：集中式 market calendar / session semantics validator（path capability 才需）。"""
    if dist.capability not in _PATH_CAPABILITIES:
        return []
    role = (dist.instrument_role or "").upper()
    if role not in INSTRUMENT_ROLES:
        return ["MISSING_INSTRUMENT_ROLE"]
    expected = _MARKET_SEMANTICS.get((normalize_family(dist.target_family), role))
    if expected is None:
        return ["UNKNOWN_MARKET_SEMANTICS"]
    exp_cal, exp_sess = expected
    reasons: list[str] = []
    if dist.target_market_calendar != exp_cal:
        reasons.append("MARKET_CALENDAR_MISMATCH")
    if dist.session_semantics != exp_sess:
        reasons.append("SESSION_SEMANTICS_MISMATCH")
    exp_scope = "DIRECT_INSTRUMENT" if role == "DIRECT" else "PROXY_MODEL_REFERENCE"
    if dist.forecast_scope != exp_scope:
        reasons.append("FORECAST_SCOPE_MISMATCH")
    return reasons


# ── 3A.2.2 §5/§6/§7 distribution-level sample contract ──
def distribution_sample_ok(dist: "DistributionRecord") -> bool:
    """§5/§7：只有 sampling-based distribution 需要自身 numeric sample evidence。"""
    if dist.capability not in _SAMPLING_CAPABILITIES:
        return True  # analytic/model distribution 不強制 Monte Carlo samples
    return (
        dist.sample_sufficiency_status == "SUFFICIENT"
        and dist.minimum_required_sample > 0
        and dist.sample_count >= dist.minimum_required_sample
        and dist.effective_sample_count >= dist.minimum_required_sample
    )


def probability_sample_within_source(pv: "ProbabilityValue", dist: "DistributionRecord") -> bool:
    """§6：probability 的 sample basis 不得超過 underlying distribution evidence。"""
    if dist.capability == "TERMINAL_SAMPLES":
        return (pv.sample_count <= dist.sample_count
                and pv.effective_sample_count <= dist.effective_sample_count)
    if dist.capability == "PATH_SAMPLES":
        return (pv.sample_count <= dist.path_count
                and pv.effective_sample_count <= dist.path_count)
    return True  # analytic/model distribution：sample basis 由 protocol 定義


# ── 3A.2.2 §18/§20/§21 calibration scope（typed reasons）──
def calibration_scope_eligibility(scope: str, evidence: dict | None, instrument: str,
                                  target_family: str, horizon: str) -> tuple[bool, list[str]]:
    """§18：typed calibration scope eligibility（reason 不得假裝只是 UNCALIBRATED）。"""
    if scope == "SINGLE_INSTRUMENT":
        return True, []
    ev = evidence or {}
    reasons: list[str] = []
    if scope == "PANEL":
        if not ev.get("universe_id") or not ev.get("universe_version"):
            reasons.append("CALIBRATION_SCOPE_EVIDENCE_MISSING")
        members = {normalize_instrument(x) for x in ev.get("members", [])}
        if normalize_instrument(instrument) not in members:
            reasons.append("CALIBRATION_UNIVERSE_MISMATCH")
        fams = {normalize_family(x) for x in ev.get("target_families", [])}
        if fams and normalize_family(target_family) not in fams:
            reasons.append("CALIBRATION_UNIVERSE_MISMATCH")
        hzs = {normalize_horizon(x) for x in ev.get("supported_horizons", [])}
        if hzs and normalize_horizon(horizon) not in hzs:
            reasons.append("CALIBRATION_UNIVERSE_MISMATCH")
        return (not reasons), reasons
    if scope == "GLOBAL":
        if not ev.get("scope_definition") or not ev.get("scope_version"):
            reasons.append("CALIBRATION_SCOPE_EVIDENCE_MISSING")
        fams = {normalize_family(x) for x in ev.get("supported_target_families", [])}
        if normalize_family(target_family) not in fams:
            reasons.append("CALIBRATION_GLOBAL_SCOPE_MISMATCH")
        hzs = {normalize_horizon(x) for x in ev.get("supported_horizons", [])}
        if normalize_horizon(horizon) not in hzs:
            reasons.append("CALIBRATION_GLOBAL_SCOPE_MISMATCH")
        return (not reasons), reasons
    return False, ["CALIBRATION_SCOPE_EVIDENCE_MISSING"]


# ── §11/§12/§13 evidence ──
@dataclass
class EvaluationEvidence:
    status: str = "NOT_EVALUATED"
    method: str = ""
    method_version: str = ""
    data_version: str = ""
    sample_count: int = 0
    evaluated_at: str = ""
    source: str = ""
    notes: str = ""

    def __post_init__(self):
        st = _EVAL_ALIASES.get(self.status, self.status)
        if st not in EVALUATION_STATUSES:
            raise ValueError(f"unknown evaluation status: {self.status!r}")
        self.status = st

    def is_valid(self) -> bool:
        """§13：EVALUATED 需 method/method_version/data_version/sample_count/evaluated_at/source。"""
        return (
            self.status == "EVALUATED"
            and bool(self.method) and bool(self.method_version) and bool(self.data_version)
            and self.sample_count > 0 and bool(self.evaluated_at) and bool(self.source)
        )

    def model_dump(self) -> dict:
        return asdict(self)


# ── §5/§6/§7/§8/§9/§10 typed probability ──
@dataclass
class ProbabilityValue:
    value: float | None = None
    status: str = "NOT_APPLICABLE"
    calibration_status: str = "INSUFFICIENT_EVIDENCE"
    calibration_domain: str = "PRICE_DISTRIBUTION"
    sample_count: int = 0
    effective_sample_count: int = 0
    minimum_required_sample: int = 0
    sample_sufficiency_status: str = "NOT_EVALUATED"
    reason_codes: list[str] = field(default_factory=list)

    def __post_init__(self):
        if self.status not in PROBABILITY_STATUSES:
            raise ValueError(f"unknown probability status: {self.status!r}")
        if self.calibration_status not in CALIBRATION_STATUSES:
            raise ValueError(f"unknown calibration_status: {self.calibration_status!r}")
        if self.calibration_domain not in CALIBRATION_DOMAINS:
            raise ValueError(f"unknown calibration_domain: {self.calibration_domain!r}")
        if self.sample_sufficiency_status not in SAMPLE_SUFFICIENCY:
            raise ValueError(f"unknown sample_sufficiency_status: {self.sample_sufficiency_status!r}")

    def is_sample_sufficient(self) -> bool:
        """§5：numeric sample gate（不得只信 status string）。"""
        return (
            self.sample_sufficiency_status == "SUFFICIENT"
            and self.minimum_required_sample > 0
            and self.sample_count >= self.minimum_required_sample
            and self.effective_sample_count >= self.minimum_required_sample
        )

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass
class ProbabilityEligibilityResult:
    """§10：central authoritative eligibility result（public view 只 render 此結果）。"""

    eligible: bool = False
    public_status: str = "NOT_AVAILABLE"
    reason_codes: list[str] = field(default_factory=list)
    validated_value: float | None = None
    checks: dict = field(default_factory=dict)

    def model_dump(self) -> dict:
        return asdict(self)


def evaluate_probability(
    pv: ProbabilityValue,
    *,
    probability_type: str,
    capability: str,
    map_calibration: str,
    map_family: str,
    instrument: str,
    horizon: str,
    provenance: ProbabilityProvenance | None,
    distribution_method: str = "",
    distribution: "DistributionRecord | None" = None,
    calibration_domain: str = "PRICE_DISTRIBUTION",
    calibration_scope: str = "SINGLE_INSTRUMENT",
    calibration_scope_reasons: list[str] | None = None,
    path_meta: dict | None = None,
) -> ProbabilityEligibilityResult:
    """§8/§9/§10/§22：deterministic gate 評估，回 authoritative result（truthful reason codes）。"""
    reasons: list[str] = []
    checks: dict = {"capability": False, "value": False, "probability_sample": False,
                    "distribution_sample": False, "provenance": False, "provenance_scope": False,
                    "distribution_scope": False, "distribution_identity": False,
                    "market_semantics": False, "calibration": False, "calibration_scope": False,
                    "path": False}

    # 1. capability support（含 path hard gate）
    cap_ok = capability_supports(capability, probability_type)
    checks["capability"] = cap_ok
    if not cap_ok:
        reasons.append("UNSUPPORTED_CAPABILITY")
        if capability == "QUANTILES_ONLY":
            reasons.append("QUANTILES_ONLY")
    if probability_type in ("touch", "first_passage"):
        pm = path_meta or {}
        path_ok = (capability in _PATH_CAPABILITIES and pm.get("path_count", 0) > 0
                   and pm.get("steps_per_path", 0) > 0 and bool(pm.get("bar_frequency"))
                   and bool(pm.get("target_market_calendar")) and bool(pm.get("session_semantics"))
                   and bool(pm.get("generation_method")))
        checks["path"] = path_ok
        if not path_ok:
            reasons.append("PATH_METADATA_MISSING")

    # 2. value validity
    val_ok = pv.value is not None and _valid_prob(pv.value)
    checks["value"] = val_ok
    if not val_ok:
        reasons.append("INVALID_VALUE")

    # 3. calibration（map + zone + domain）+ §18 calibration scope
    cal_ok = (map_calibration == "CALIBRATED" and pv.calibration_status == "CALIBRATED"
              and calibration_domain == "PRICE_DISTRIBUTION" and pv.calibration_domain == "PRICE_DISTRIBUTION")
    checks["calibration"] = cal_ok
    if not cal_ok:
        reasons.append("UNCALIBRATED")
    if calibration_domain != "PRICE_DISTRIBUTION" or pv.calibration_domain != "PRICE_DISTRIBUTION":
        reasons.append("CALIBRATION_DOMAIN_MISMATCH")
    cal_scope_reasons = list(calibration_scope_reasons or [])
    checks["calibration_scope"] = not cal_scope_reasons
    reasons.extend(cal_scope_reasons)

    # 4. probability numeric sample sufficiency
    samp_ok = pv.is_sample_sufficient()
    checks["probability_sample"] = samp_ok
    if not samp_ok:
        reasons.append("INSUFFICIENT_SAMPLE")

    # 5. distribution-level sample contract（§5/§7）
    dist_samp_ok = True
    if distribution is not None:
        dist_samp_ok = distribution_sample_ok(distribution)
        if not dist_samp_ok:
            reasons.append("DISTRIBUTION_INSUFFICIENT_SAMPLE")
    checks["distribution_sample"] = dist_samp_ok

    # 6. probability sample cannot exceed source evidence（§6）
    src_ok = True
    if distribution is not None:
        src_ok = probability_sample_within_source(pv, distribution)
        if not src_ok:
            reasons.append("PROBABILITY_SAMPLE_EXCEEDS_SOURCE")

    # 7. provenance completeness + method consistency + calibration provenance + §17 identity
    prov_ok = provenance is not None and provenance.is_complete()
    if provenance is not None and distribution_method and provenance.distribution_method != distribution_method:
        reasons.append("DISTRIBUTION_METHOD_MISMATCH")
        prov_ok = False
    if map_calibration == "CALIBRATED" and provenance is not None:
        if not (provenance.calibration_method and provenance.calibration_version):
            reasons.append("CALIBRATION_PROVENANCE_MISSING")
            prov_ok = False
    ident_ok = True
    if provenance is not None and distribution is not None:
        if distribution.distribution_id:
            ident_ok = (provenance.distribution_id == distribution.distribution_id
                        and provenance.distribution_version == distribution.distribution_version)
            if not ident_ok:
                reasons.append("DISTRIBUTION_IDENTITY_MISMATCH")
        elif distribution.capability not in ("NONE", "QUANTILES_ONLY"):
            ident_ok = False
            reasons.append("MISSING_DISTRIBUTION_IDENTITY")
    checks["provenance"] = prov_ok
    checks["distribution_identity"] = ident_ok
    if not prov_ok and "MISSING_PROVENANCE" not in reasons and not any(
            r in reasons for r in ("DISTRIBUTION_METHOD_MISMATCH", "CALIBRATION_PROVENANCE_MISSING")):
        reasons.append("MISSING_PROVENANCE")

    # 8. provenance scope match
    scope_reasons = validate_provenance_scope(provenance, map_family, instrument, horizon)
    checks["provenance_scope"] = not scope_reasons
    reasons.extend(scope_reasons)

    # 9. distribution scope（§2/§3）+ §16 dist scope == prov scope
    dist_scope_reasons: list[str] = []
    if distribution is not None:
        dist_scope_reasons = validate_distribution_scope(distribution, map_family, instrument, horizon)
        if (not dist_scope_reasons and provenance is not None
                and normalize_family(distribution.target_family)
                != normalize_family(provenance.target_family)):
            dist_scope_reasons.append("DISTRIBUTION_TARGET_SCOPE_MISMATCH")
        if (not dist_scope_reasons and provenance is not None
                and normalize_instrument(distribution.instrument)
                != normalize_instrument(provenance.instrument)):
            dist_scope_reasons.append("DISTRIBUTION_INSTRUMENT_SCOPE_MISMATCH")
        if (not dist_scope_reasons and provenance is not None
                and normalize_horizon(distribution.horizon)
                != normalize_horizon(provenance.horizon)):
            dist_scope_reasons.append("DISTRIBUTION_HORIZON_SCOPE_MISMATCH")
    checks["distribution_scope"] = not dist_scope_reasons
    reasons.extend(dist_scope_reasons)

    # 10. market calendar / session semantics（§10-§15）
    mkt_reasons: list[str] = []
    if distribution is not None:
        mkt_reasons = validate_distribution_market_semantics(distribution)
    checks["market_semantics"] = not mkt_reasons
    reasons.extend(mkt_reasons)

    eligible = (cap_ok and val_ok and cal_ok and not cal_scope_reasons and samp_ok
                and dist_samp_ok and src_ok and prov_ok and ident_ok
                and not scope_reasons and not dist_scope_reasons and not mkt_reasons)
    if probability_type in ("touch", "first_passage"):
        eligible = eligible and checks["path"] is True
    eligible = bool(eligible)

    # public status（deterministic priority）
    if eligible:
        public_status = "AVAILABLE"
    elif not cap_ok:
        public_status = "NOT_AVAILABLE_UNSUPPORTED_CAPABILITY"
    elif probability_type in ("touch", "first_passage") and checks["path"] is not True:
        public_status = "NOT_AVAILABLE_UNSUPPORTED_CAPABILITY"
    elif not cal_ok or cal_scope_reasons:
        public_status = "NOT_AVAILABLE_UNCALIBRATED"
    elif not samp_ok or not dist_samp_ok or not src_ok:
        public_status = "NOT_AVAILABLE_INSUFFICIENT_SAMPLE"
    elif scope_reasons or dist_scope_reasons:
        public_status = "NOT_AVAILABLE_SCOPE_MISMATCH"
    elif mkt_reasons:
        public_status = "NOT_AVAILABLE_SCOPE_MISMATCH"
    elif not prov_ok or not ident_ok:
        public_status = "NOT_AVAILABLE_MISSING_PROVENANCE"
    elif not val_ok:
        public_status = "NOT_AVAILABLE_INVALID_VALUE"
    else:
        public_status = "NOT_AVAILABLE_INSUFFICIENT_DISTRIBUTION"

    # dedupe reasons（保序）
    seen, deduped = set(), []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            deduped.append(r)

    return ProbabilityEligibilityResult(
        eligible=eligible, public_status=public_status, reason_codes=deduped,
        validated_value=pv.value if eligible else None, checks=checks,
    )


@dataclass
class ZoneProbability:
    zone: str
    terminal: ProbabilityValue = field(default_factory=ProbabilityValue)
    touch: ProbabilityValue = field(default_factory=ProbabilityValue)
    first_passage: ProbabilityValue = field(default_factory=ProbabilityValue)
    availability_status: str = "NOT_AVAILABLE"  # compat
    calibration_status: str = "INSUFFICIENT_EVIDENCE"  # compat
    method: str = ""  # compat

    @property
    def terminal_probability(self):
        return self.terminal.value

    @property
    def touch_probability(self):
        return self.touch.value

    @property
    def first_passage_probability(self):
        return self.first_passage.value

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass
class DistributionRecord:
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
    # ── 3A.2.2 §10/§17 ──
    instrument_role: str = ""
    forecast_scope: str = ""
    distribution_id: str = ""
    distribution_version: str = ""

    def __post_init__(self):
        if self.method not in DISTRIBUTION_METHODS:
            raise ValueError(f"unknown distribution method: {self.method!r}")
        if self.capability not in DISTRIBUTION_CAPABILITIES:
            raise ValueError(f"unknown distribution capability: {self.capability!r}")
        if not method_capability_ok(self.method, self.capability):
            raise ValueError(
                f"method/capability mismatch: method={self.method} capability={self.capability}")
        # §8：sample status 不得只是任意字串
        if self.sample_sufficiency_status not in SAMPLE_SUFFICIENCY:
            raise ValueError(
                f"unknown sample_sufficiency_status: {self.sample_sufficiency_status!r}")
        if self.instrument_role and self.instrument_role not in INSTRUMENT_ROLES:
            raise ValueError(f"unknown instrument_role: {self.instrument_role!r}")
        if self.forecast_scope and self.forecast_scope not in FORECAST_SCOPES:
            raise ValueError(f"unknown forecast_scope: {self.forecast_scope!r}")

    def path_meta(self) -> dict:
        return {"path_count": self.path_count, "steps_per_path": self.steps_per_path,
                "bar_frequency": self.bar_frequency, "target_market_calendar": self.target_market_calendar,
                "session_semantics": self.session_semantics, "generation_method": self.generation_method}

    def model_dump(self) -> dict:
        return asdict(self)


def quantiles_only_distribution(target_family: str = "", instrument: str = "",
                                horizon: str = "") -> DistributionRecord:
    return DistributionRecord(method="QUANTILES_ONLY", capability="QUANTILES_ONLY",
                              is_full_distribution=False, target_family=target_family,
                              instrument=instrument, horizon=horizon)


@dataclass
class ProbabilityMap:
    instrument: str
    target_family: str
    horizon: str
    zones: list[ZoneProbability] = field(default_factory=list)
    distribution: DistributionRecord = field(default_factory=DistributionRecord)
    calibration_status: str = "INSUFFICIENT_EVIDENCE"
    calibration_scope: str = "SINGLE_INSTRUMENT"
    calibration_scope_evidence: dict = field(default_factory=dict)
    provenance: ProbabilityProvenance | None = None
    version: str = PRICE_PROBABILITY_MAP_VERSION

    def __post_init__(self):
        if self.calibration_status not in CALIBRATION_STATUSES:
            raise ValueError(f"unknown calibration_status: {self.calibration_status!r}")
        if self.calibration_scope not in CALIBRATION_SCOPES:
            raise ValueError(f"unknown calibration_scope: {self.calibration_scope!r}")

    @property
    def distribution_method(self):
        return self.distribution.method

    def _scope_ok(self) -> bool:
        """§3：calibration scope enforcement（backward-compat wrapper）。"""
        return self._scope_result()[0]

    def _scope_result(self) -> tuple[bool, list[str]]:
        """§18：typed calibration scope eligibility。"""
        return calibration_scope_eligibility(
            self.calibration_scope, self.calibration_scope_evidence,
            self.instrument, self.target_family, self.horizon)

    def public_view(self) -> dict:
        out = {
            "instrument": self.instrument, "target_family": self.target_family,
            "horizon": self.horizon, "version": self.version,
            "calibration_status": self.calibration_status,
            "calibration_scope": self.calibration_scope,
            "distribution_method": self.distribution.method,
            "distribution_capability": self.distribution.capability,
            "is_full_distribution": self.distribution.is_full_distribution,
            "zones": [],
        }
        scope_ok, scope_reasons = self._scope_result()
        if not scope_ok:
            out["calibration_scope_reason_codes"] = scope_reasons
        for z in self.zones:
            zd: dict = {"zone": z.zone}
            for ptype, pv in (("terminal", z.terminal), ("touch", z.touch), ("first_passage", z.first_passage)):
                res = evaluate_probability(
                    pv, probability_type=ptype, capability=self.distribution.capability,
                    map_calibration=self.calibration_status,
                    map_family=self.target_family, instrument=self.instrument, horizon=self.horizon,
                    provenance=self.provenance, distribution_method=self.distribution.method,
                    distribution=self.distribution,
                    calibration_domain=pv.calibration_domain, calibration_scope=self.calibration_scope,
                    calibration_scope_reasons=scope_reasons,
                    path_meta=self.distribution.path_meta(),
                )
                if res.eligible:
                    zd[f"{ptype}_probability"] = res.validated_value
                    zd[f"{ptype}_status"] = "AVAILABLE"
                else:
                    zd[f"{ptype}_status"] = res.public_status
                    zd[f"{ptype}_reason_codes"] = res.reason_codes or ["NO_DISTRIBUTION"]
            out["zones"].append(zd)
        return out

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass
class ZonePolicy:
    policy_id: str = "default"
    version: str = ZONE_POLICY_VERSION
    buy_zone_upper_quantile: float = 0.25
    profit_zone_lower_quantile: float = 0.75
    note: str = "research parameter; quantile boundary != zone probability"

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


@dataclass
class PriceMap:
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
    distribution_diagnostics: DistributionDiagnostics | None = None
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


# ── profiles ──
PROFILES = {
    "TAIWAN_STOCK_PROFILE": {
        "target_family": "TAIWAN_STOCK", "version": "3A.2.1", "structural_asymmetry": True,
        "note": "equity: structural asymmetry research allowed",
    },
    "TAIWAN_INDEX_PROFILE": {
        "target_family": "TAIWAN_INDEX", "version": "3A.2.1",
        "forecast_reference_target": "TAIEX", "execution_instruments": ["TX", "MTX", "TMF"],
        "cash_index_executable": False, "execution_validation": "NOT_ESTABLISHED",
        "structural_asymmetry": True,
        "note": "TAIEX cash index forecast/reference (non-executable); execution via TX/MTX/TMF",
    },
    "OSAKA_MICRO_PROFILE": {
        "target_family": "OSAKA_MICRO", "version": "3A.2.1", "structural_asymmetry": False,
        "note": "futures: long/short more symmetric research assumption allowed",
    },
}

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
    valid = (regime_status == "EVALUATED" and regime is not None
             and regime_evidence is not None and regime_evidence.is_valid())
    if not valid:
        return {"regime": regime, "regime_status": regime_status, "candidate": "NONE",
                "is_instruction": False, "note": "regime not evaluated/verified; no candidate"}
    return {"regime": regime, "regime_status": regime_status,
            "candidate": STRATEGY_SWITCHING.get(regime, "NONE"), "is_instruction": False,
            "note": "research candidate only; not a trade instruction"}


def _evaluated_status(value: str | None, evidence: EvaluationEvidence | None) -> str:
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
    if market_state is not None and market_state not in MARKET_STATES:
        raise ValueError(f"unknown market_state: {market_state}")
    if regime is not None and regime not in REGIMES:
        raise ValueError(f"unknown regime: {regime}")
    if model_failure_state is not None and model_failure_state not in MODEL_FAILURE_STATUSES:
        raise ValueError(f"unknown model_failure_state: {model_failure_state}")

    ms = _evaluated_status(market_state, market_state_evidence)
    rg = _evaluated_status(regime, regime_evidence)
    mf = _evaluated_status(model_failure_state, model_failure_evidence)
    return PriceMap(
        instrument=instrument, target_family=target_family, horizon=horizon,
        reference_price=reference_price, distribution_center=distribution_center or {},
        zone_boundaries=zone_boundaries or {},
        market_state=market_state, market_state_status=ms, market_state_evidence=market_state_evidence,
        state_is_trade_instruction=False,
        regime=regime, regime_status=rg, regime_evidence=regime_evidence,
        model_failure_state=model_failure_state, model_failure_evaluation_status=mf,
        model_failure_evidence=model_failure_evidence,
        distribution_diagnostics=diagnostics or DistributionDiagnostics(),
        strategy_candidate=strategy_candidate_for(regime, rg, regime_evidence)["candidate"],
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


def calibration_metrics_contract() -> dict:
    return {
        "domain": "PRICE_DISTRIBUTION",
        "metrics": ["coverage_calibration", "pit_diagnostics", "brier_score",
                    "log_score", "reliability_bins", "calibration_error"],
        "status": "INTERFACE_ONLY_NOT_FITTED",
    }
