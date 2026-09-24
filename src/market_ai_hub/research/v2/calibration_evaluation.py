"""V2-I 2I.1 — calibration / evaluation foundation (evaluation engine, NOT fitting).

決定性、content-addressed 的評估層：只從 V2-H 2H.2 的 PredictionRecord /
ForecastArtifactRecord / OutcomeRecord 建立評估資料集並計算指標。

嚴格邊界（contract：docs/architecture/v2-calibration-evaluation-contract.md）：

- **ENGINE PASS != CALIBRATED**；**EVALUATED != CALIBRATED**；
  **SYNTHETIC METRICS != MARKET EVIDENCE**。
- 2I.1 **不 fit calibration model**、**無 pre-registered acceptance threshold**，
  因此 adapter 只能產生 ``INSUFFICIENT_EVIDENCE`` / ``EVALUATED_UNCALIBRATED``，
  **永不產生 CALIBRATED**。
- 只有 ``EVENT_PROBABILITY``（value in [0,1]）配 binary outcome 才可計算
  Brier / log loss / reliability / ECE / MCE；``CLASS_SCORE`` 永不當機率。
- TERMINAL / TOUCH / FIRST_PASSAGE / BREAK / ACCEPTANCE / DIRECTION 全部分開，
  1d != 5d、Osaka != Taiwan（由 manifest 欄位承載，不可跨組）。
- 不從 CSV 或其他來源補值；缺 outcome = 資料稀疏（非致命），
  型別/跨預測/洩漏 = BLOCKED（fail-closed）。
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from market_ai_hub.research.v2.prediction_audit import (
    PredictionAuditDB,
    default_audit_db_path,
)

V2_CALIBRATION_EVALUATION_SCHEMA_VERSION = "2I.1"

PARTITION_ROLES = ("CALIBRATION", "VALIDATION", "FINAL_OOS", "FORWARD")
EVALUATION_STATUSES = ("EVALUATED", "INSUFFICIENT_SAMPLE", "NOT_EVALUATABLE", "BLOCKED")
EVIDENCE_STATUSES = ("INSUFFICIENT_EVIDENCE", "EVALUATED_UNCALIBRATED")
# CALIBRATED 刻意不存在（2I.1 不 fit model、無門檻、無真實 settled 機率樣本）

RELIABILITY_BIN_COUNT = 10
LOG_LOSS_EPSILON = 1e-15
MIN_PROBABILITY_SAMPLES = 2      # 單一樣本無法呈現 calibration，僅 1 筆 -> INSUFFICIENT_SAMPLE

PAIRING_REJECTIONS = (
    "CROSS_PREDICTION", "WRONG_PROBABILITY_TYPE", "WRONG_EVENT_DEFINITION",
    "WRONG_TARGET", "WRONG_HORIZON", "WRONG_MODEL", "WRONG_CALIBRATION_DOMAIN",
    "MISSING_OUTCOME", "AMBIGUOUS_OUTCOME", "LEAKAGE_FUTURE", "OUTSIDE_WINDOW",
    "NOT_PROBABILITY", "NON_BINARY_OUTCOME", "NOT_BOUND", "EMPTY_VALUE",
)
# 致命（資料集本身不合法 -> BLOCKED）vs 稀疏（缺 outcome -> 不致命）
BLOCKING_PAIRING_REJECTIONS = frozenset({
    "CROSS_PREDICTION", "WRONG_PROBABILITY_TYPE", "WRONG_EVENT_DEFINITION",
    "WRONG_TARGET", "WRONG_HORIZON", "WRONG_MODEL", "WRONG_CALIBRATION_DOMAIN",
    "AMBIGUOUS_OUTCOME", "LEAKAGE_FUTURE", "OUTSIDE_WINDOW", "NOT_PROBABILITY",
})
NON_BLOCKING_PAIRING_REJECTIONS = frozenset({
    "MISSING_OUTCOME", "NON_BINARY_OUTCOME", "NOT_BOUND", "EMPTY_VALUE",
})

# probability_type（family）<-> outcome_kind：fail-closed，未知即拒。
# TERMINAL 與 TOUCH 是不同事件家族，永不互相評估。
PROBABILITY_TYPE_OUTCOME_KINDS: dict[str, frozenset[str]] = {
    "TERMINAL": frozenset({"TERMINAL"}),
    "TOUCH": frozenset({"TOUCH"}),
    "FIRST_PASSAGE": frozenset({"TOUCH"}),
    "BREAK": frozenset({"BREAK"}),
    "ACCEPTANCE": frozenset({"ACCEPTANCE"}),
    "DIRECTION": frozenset({"DIRECTION"}),
}

NUMERIC_ARTIFACT_TYPES = ("POINT", "QUANTILE", "INTERVAL")
NON_EVALUATABLE_ARTIFACT_TYPES = ("STATE", "CLASS_SCORE", "NOT_AVAILABLE")


class CalibrationEvaluationError(Exception):
    """Base for 2I.1 contract violations."""


def _hash(namespace: str, payload: dict) -> str:
    from market_ai_hub.research.v2.prediction_audit import canonical_json

    return sha256(f"{namespace}|{canonical_json(payload)}".encode("utf-8")).hexdigest()[:16]


def evaluation_dataset_identity(payload: dict) -> str:
    """Content-addressed dataset id：member set 或任何欄位改變 -> id 改變。"""
    return "v2i_ds_" + _hash("calibration_evaluation_dataset", payload)


def _utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _require_aware(name: str, dt: datetime | None) -> None:
    if dt is None:
        raise CalibrationEvaluationError(f"{name} is required")
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise CalibrationEvaluationError(f"{name} must be timezone-aware")


@dataclass(frozen=True)
class EvaluationMember:
    """一個評估樣本單位：預測 + 其預測輸出 artifact + 綁定的 outcome。"""

    prediction_id: str
    forecast_artifact_id: str
    outcome_id: str

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EvaluationRejection:
    """被拒的候選樣本（保存理由，日後可審）。"""

    prediction_id: str = ""
    forecast_artifact_id: str = ""
    reason: str = ""
    detail: str = ""

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EvaluationDatasetManifest:
    """評估資料集 manifest（content-addressed；成員 ID 全部保存）。"""

    members: list[EvaluationMember]
    target_family: str
    instrument: str
    horizon: str
    model: str
    model_version: str
    artifact_type: str
    partition_role: str
    window_start: datetime
    window_end: datetime
    calibration_domain: str = ""
    probability_type: str = ""
    event_definition_id: str = ""
    label_types: list[str] = field(default_factory=list)
    rejected: list[EvaluationRejection] = field(default_factory=list)
    schema_version: str = V2_CALIBRATION_EVALUATION_SCHEMA_VERSION
    dataset_id: str = ""          # derived
    created_at: datetime | None = None  # runtime metadata

    def __post_init__(self) -> None:
        if self.partition_role not in PARTITION_ROLES:
            raise CalibrationEvaluationError(f"unknown partition_role: {self.partition_role!r}")
        if self.partition_role == "FINAL_OOS" and self.schema_version != V2_CALIBRATION_EVALUATION_SCHEMA_VERSION:
            raise CalibrationEvaluationError("FINAL_OOS manifest must carry the 2I.1 schema version")
        if self.window_end < self.window_start:
            raise CalibrationEvaluationError("window_end < window_start")
        object.__setattr__(self, "members", sorted(
            self.members, key=lambda m: (m.prediction_id, m.forecast_artifact_id, m.outcome_id)))
        object.__setattr__(self, "rejected", sorted(
            self.rejected, key=lambda r: (r.prediction_id, r.forecast_artifact_id, r.reason)))
        object.__setattr__(self, "label_types", sorted({*self.label_types}))

    def model_dump(self) -> dict:
        return asdict(self)

    def identity_payload(self) -> dict:
        d = asdict(self)
        d.pop("dataset_id", None)
        d.pop("created_at", None)
        return d

    def blocked_rejections(self) -> list[EvaluationRejection]:
        return [r for r in self.rejected if r.reason in BLOCKING_PAIRING_REJECTIONS]

    def is_blocked(self) -> bool:
        return bool(self.blocked_rejections())


@dataclass(frozen=True)
class ReliabilityBin:
    lower: float
    upper: float
    count: int
    mean_predicted: float | None = None
    empirical_rate: float | None = None
    gap: float | None = None

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ProbabilityMetrics:
    sample_count: int
    brier_score: float
    log_loss: float
    base_rate: float
    mean_predicted_probability: float
    ece: float
    mce: float
    reliability_bins: list[ReliabilityBin] = field(default_factory=list)
    log_loss_epsilon: float = LOG_LOSS_EPSILON
    bin_count: int = RELIABILITY_BIN_COUNT

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PointMetrics:
    sample_count: int
    mae: float
    rmse: float

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class QuantileMetrics:
    sample_count: int
    quantile_level: float
    pinball_loss: float

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class IntervalMetrics:
    sample_count: int
    nominal_coverage: float
    empirical_coverage: float
    mean_width: float
    coverage_error: float

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EvaluationResult:
    """評估結果（引擎輸出；非 calibration 認證）。"""

    status: str
    artifact_type: str
    dataset_id: str
    partition_role: str
    sample_count: int = 0
    reason: str = ""
    probability: ProbabilityMetrics | None = None
    point: PointMetrics | None = None
    quantile: QuantileMetrics | None = None
    interval: IntervalMetrics | None = None
    rejected: list[EvaluationRejection] = field(default_factory=list)
    schema_version: str = V2_CALIBRATION_EVALUATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.status not in EVALUATION_STATUSES:
            raise CalibrationEvaluationError(f"unknown evaluation status: {self.status!r}")

    def model_dump(self) -> dict:
        return asdict(self)


# ── manifest 建構（只配對 forecast artifact <-> 其綁定 outcome） ──
def build_evaluation_dataset(
    db: PredictionAuditDB,
    *,
    prediction_ids: list[str],
    target_family: str,
    instrument: str,
    horizon: str,
    model: str = "",
    model_version: str = "",
    artifact_type: str = "EVENT_PROBABILITY",
    partition_role: str = "CALIBRATION",
    window_start: datetime,
    window_end: datetime,
    calibration_domain: str = "",
    probability_type: str = "",
    event_definition_id: str = "",
) -> EvaluationDatasetManifest:
    """從 2H.2 audit DB 建立 content-addressed 評估資料集（不補值、不跨來源）。"""
    _require_aware("window_start", window_start)
    _require_aware("window_end", window_end)
    if partition_role not in PARTITION_ROLES:
        raise CalibrationEvaluationError(f"unknown partition_role: {partition_role!r}")

    members: list[EvaluationMember] = []
    rejected: list[EvaluationRejection] = []
    label_types: set[str] = set()

    for pid in sorted(set(prediction_ids)):
        pred = db.get_prediction(pid)
        if pred is None:
            rejected.append(EvaluationRejection(prediction_id=pid, reason="CROSS_PREDICTION",
                                                detail="unknown prediction"))
            continue
        if pred.target_family != target_family or pred.instrument != instrument:
            rejected.append(EvaluationRejection(prediction_id=pid, reason="WRONG_TARGET",
                                                detail=f"{pred.target_family}/{pred.instrument}"))
            continue
        if pred.horizon != horizon:
            rejected.append(EvaluationRejection(prediction_id=pid, reason="WRONG_HORIZON",
                                                detail=f"{pred.horizon!r} != {horizon!r}"))
            continue
        if (model and pred.model != model) or (model_version and pred.model_version != model_version):
            rejected.append(EvaluationRejection(
                prediction_id=pid, reason="WRONG_MODEL",
                detail=f"{pred.model!r}/{pred.model_version!r}"))
            continue
        origin = _utc(pred.forecast_origin)
        if origin < _utc(window_start) or origin > _utc(window_end):
            rejected.append(EvaluationRejection(prediction_id=pid, reason="OUTSIDE_WINDOW",
                                                detail=origin.isoformat()))
            continue
        outcomes = db.get_outcomes(pid)
        for art in db.get_forecast_artifacts(pid):
            aid = art.forecast_artifact_id
            if art.artifact_type != artifact_type:
                rejected.append(EvaluationRejection(prediction_id=pid, forecast_artifact_id=aid,
                                                    reason="WRONG_PROBABILITY_TYPE",
                                                    detail=f"artifact_type {art.artifact_type!r}"))
                continue
            if calibration_domain and art.calibration_domain != calibration_domain:
                rejected.append(EvaluationRejection(prediction_id=pid, forecast_artifact_id=aid,
                                                    reason="WRONG_CALIBRATION_DOMAIN",
                                                    detail=art.calibration_domain))
                continue
            if probability_type and art.probability_type != probability_type:
                rejected.append(EvaluationRejection(prediction_id=pid, forecast_artifact_id=aid,
                                                    reason="WRONG_PROBABILITY_TYPE",
                                                    detail=art.probability_type))
                continue
            if event_definition_id and art.event_definition_id != event_definition_id:
                rejected.append(EvaluationRejection(prediction_id=pid, forecast_artifact_id=aid,
                                                    reason="WRONG_EVENT_DEFINITION",
                                                    detail=art.event_definition_id))
                continue
            bound = [o for o in outcomes if o.forecast_artifact_id == aid]
            if not bound:
                rejected.append(EvaluationRejection(prediction_id=pid, forecast_artifact_id=aid,
                                                    reason="MISSING_OUTCOME", detail="no bound outcome"))
                continue
            if len(bound) > 1:
                rejected.append(EvaluationRejection(prediction_id=pid, forecast_artifact_id=aid,
                                                    reason="AMBIGUOUS_OUTCOME",
                                                    detail=f"{len(bound)} bound outcomes"))
                continue
            out = bound[0]
            if out.prediction_id != pid:
                rejected.append(EvaluationRejection(prediction_id=pid, forecast_artifact_id=aid,
                                                    reason="CROSS_PREDICTION", detail=out.outcome_id))
                continue
            if _utc(out.available_at) < origin:
                rejected.append(EvaluationRejection(prediction_id=pid, forecast_artifact_id=aid,
                                                    reason="LEAKAGE_FUTURE",
                                                    detail="outcome available before forecast_origin"))
                continue
            if artifact_type == "EVENT_PROBABILITY":
                if art.value is None:
                    rejected.append(EvaluationRejection(prediction_id=pid, forecast_artifact_id=aid,
                                                        reason="EMPTY_VALUE", detail="no probability value"))
                    continue
                if not (0.0 <= float(art.value) <= 1.0):
                    rejected.append(EvaluationRejection(prediction_id=pid, forecast_artifact_id=aid,
                                                        reason="NOT_PROBABILITY",
                                                        detail=f"value {art.value} outside [0,1]"))
                    continue
                allowed = PROBABILITY_TYPE_OUTCOME_KINDS.get(art.probability_type, frozenset())
                if out.outcome_kind not in allowed:
                    rejected.append(EvaluationRejection(
                        prediction_id=pid, forecast_artifact_id=aid, reason="WRONG_PROBABILITY_TYPE",
                        detail=f"probability_type {art.probability_type!r} != outcome_kind {out.outcome_kind!r}"))
                    continue
            if out.actual_value is None:
                rejected.append(EvaluationRejection(prediction_id=pid, forecast_artifact_id=aid,
                                                    reason="MISSING_OUTCOME",
                                                    detail="outcome not numerically settled"))
                continue
            if artifact_type == "EVENT_PROBABILITY" and float(out.actual_value) not in (0.0, 1.0):
                rejected.append(EvaluationRejection(prediction_id=pid, forecast_artifact_id=aid,
                                                    reason="NON_BINARY_OUTCOME",
                                                    detail=f"actual_value {out.actual_value}"))
                continue
            members.append(EvaluationMember(prediction_id=pid, forecast_artifact_id=aid,
                                            outcome_id=out.outcome_id))
            if out.label_type:
                label_types.add(out.label_type)

    manifest = EvaluationDatasetManifest(
        members=members, target_family=target_family, instrument=instrument, horizon=horizon,
        model=model, model_version=model_version, artifact_type=artifact_type,
        partition_role=partition_role, window_start=window_start, window_end=window_end,
        calibration_domain=calibration_domain, probability_type=probability_type,
        event_definition_id=event_definition_id, label_types=sorted(label_types),
        rejected=rejected,
    )
    return replace(manifest, dataset_id=evaluation_dataset_identity(manifest.identity_payload()))


# ── 指標（deterministic；無任意 good/bad threshold） ──
def _samples_probability(db: PredictionAuditDB, manifest: EvaluationDatasetManifest
                         ) -> tuple[list[tuple[float, float]], int]:
    pairs: list[tuple[float, float]] = []
    for m in manifest.members:
        art = db.get_forecast_artifact(m.forecast_artifact_id)
        if art is None:
            continue
        out = [o for o in db.get_outcomes(m.prediction_id) if o.outcome_id == m.outcome_id]
        if not out:
            continue
        pairs.append((float(art.value), float(out[0].actual_value)))
    return pairs, len(pairs)


def reliability_bins(pairs: list[tuple[float, float]],
                     bin_count: int = RELIABILITY_BIN_COUNT) -> list[ReliabilityBin]:
    """等寬 deterministic bins：[0,.1) ... [.9,1]（p=1 落在最後一 bin）；空 bin 保留。"""
    if bin_count < 1:
        raise CalibrationEvaluationError("bin_count must be >= 1")
    width = 1.0 / bin_count
    counts = [0] * bin_count
    sums_p = [0.0] * bin_count
    sums_y = [0.0] * bin_count
    for p, y in pairs:
        idx = min(int(p * bin_count), bin_count - 1)   # p=1.0 -> last bin
        counts[idx] += 1
        sums_p[idx] += p
        sums_y[idx] += y
    bins: list[ReliabilityBin] = []
    for i in range(bin_count):
        lower = i * width
        upper = 1.0 if i == bin_count - 1 else (i + 1) * width
        n = counts[i]
        if n == 0:
            bins.append(ReliabilityBin(lower=lower, upper=upper, count=0))
        else:
            mp = sums_p[i] / n
            er = sums_y[i] / n
            bins.append(ReliabilityBin(lower=lower, upper=upper, count=n, mean_predicted=mp,
                                       empirical_rate=er, gap=abs(er - mp)))
    return bins


def _probability_metrics(pairs: list[tuple[float, float]]) -> ProbabilityMetrics:
    n = len(pairs)
    eps = LOG_LOSS_EPSILON
    brier = sum((p - y) ** 2 for p, y in pairs) / n
    log_loss = -sum(
        y * math.log(min(max(p, eps), 1.0 - eps)) + (1 - y) * math.log(min(max(1 - p, eps), 1.0 - eps))
        for p, y in pairs) / n
    base_rate = sum(y for _, y in pairs) / n
    mean_p = sum(p for p, _ in pairs) / n
    bins = reliability_bins(pairs)
    ece = sum(b.count / n * b.gap for b in bins if b.count)
    mce = max((b.gap for b in bins if b.count), default=0.0)
    return ProbabilityMetrics(sample_count=n, brier_score=brier, log_loss=log_loss,
                              base_rate=base_rate, mean_predicted_probability=mean_p,
                              ece=ece, mce=mce, reliability_bins=bins)


def _numeric_pairs(db: PredictionAuditDB, manifest: EvaluationDatasetManifest
                   ) -> list[tuple[Any, float]]:
    pairs: list[tuple[Any, float]] = []
    for m in manifest.members:
        art = db.get_forecast_artifact(m.forecast_artifact_id)
        if art is None:
            continue
        out = [o for o in db.get_outcomes(m.prediction_id) if o.outcome_id == m.outcome_id]
        if not out or out[0].actual_value is None:
            continue
        pairs.append((art, float(out[0].actual_value)))
    return pairs


def evaluate_manifest(db: PredictionAuditDB,
                      manifest: EvaluationDatasetManifest) -> EvaluationResult:
    """依 artifact_type 分派評估；狀態只會是 EVALUATED/INSUFFICIENT_SAMPLE/NOT_EVALUATABLE/BLOCKED。"""
    base = {"dataset_id": manifest.dataset_id, "artifact_type": manifest.artifact_type,
            "partition_role": manifest.partition_role, "rejected": manifest.rejected}

    if manifest.is_blocked():
        reasons = sorted({r.reason for r in manifest.blocked_rejections()})
        return EvaluationResult(status="BLOCKED", reason=";".join(reasons), **base)

    for m in manifest.members:
        if not db.verify_prediction(m.prediction_id):
            return EvaluationResult(status="BLOCKED", reason="PREDICTION_INTEGRITY_FAILED", **base)

    if manifest.artifact_type in NON_EVALUATABLE_ARTIFACT_TYPES:
        reason = ("CLASS_SCORE is never treated as a probability"
                  if manifest.artifact_type == "CLASS_SCORE" else "artifact carries no evaluable value")
        return EvaluationResult(status="NOT_EVALUATABLE", reason=reason,
                                sample_count=len(manifest.members), **base)

    if manifest.artifact_type == "EVENT_PROBABILITY":
        pairs, n = _samples_probability(db, manifest)
        if n == 0:
            return EvaluationResult(status="NOT_EVALUATABLE", reason="NO_SETTLED_PROBABILITY_SAMPLE",
                                    sample_count=0, **base)
        if n < MIN_PROBABILITY_SAMPLES:
            return EvaluationResult(status="INSUFFICIENT_SAMPLE",
                                    reason=f"MIN_PROBABILITY_SAMPLES={MIN_PROBABILITY_SAMPLES}",
                                    sample_count=n, **base)
        return EvaluationResult(status="EVALUATED", sample_count=n,
                                probability=_probability_metrics(pairs), **base)

    pairs = _numeric_pairs(db, manifest)
    if not pairs:
        return EvaluationResult(status="NOT_EVALUATABLE", reason="NO_SETTLED_NUMERIC_OUTCOME",
                                sample_count=0, **base)
    ys = [y for _, y in pairs]
    if manifest.artifact_type == "POINT":
        errs = [float(a.value) - y for a, y in pairs if a.value is not None]
        if len(errs) != len(pairs):
            return EvaluationResult(status="NOT_EVALUATABLE", reason="POINT_MISSING_VALUE",
                                    sample_count=len(pairs), **base)
        mae = sum(abs(e) for e in errs) / len(errs)
        rmse = math.sqrt(sum(e * e for e in errs) / len(errs))
        return EvaluationResult(status="EVALUATED", sample_count=len(pairs),
                                point=PointMetrics(len(pairs), mae, rmse), **base)
    if manifest.artifact_type == "QUANTILE":
        levels = {a.quantile_level for a, _ in pairs}
        if len(levels) != 1 or None in levels:
            return EvaluationResult(status="BLOCKED", reason="MIXED_OR_MISSING_QUANTILE_LEVEL",
                                    sample_count=len(pairs), **base)
        tau = float(next(iter(levels)))
        loss = sum((tau - (1.0 if y < float(a.value) else 0.0)) * (y - float(a.value))
                   for a, y in pairs) / len(pairs)
        return EvaluationResult(status="EVALUATED", sample_count=len(pairs),
                                quantile=QuantileMetrics(len(pairs), tau, loss), **base)
    if manifest.artifact_type == "INTERVAL":
        covs = [1.0 if float(a.lower_value) <= y <= float(a.upper_value) else 0.0 for a, y in pairs]
        widths = [float(a.upper_value) - float(a.lower_value) for a, _ in pairs]
        nominals = {a.nominal_coverage for a, _ in pairs}
        if len(nominals) != 1 or None in nominals:
            return EvaluationResult(status="BLOCKED", reason="MIXED_OR_MISSING_NOMINAL_COVERAGE",
                                    sample_count=len(pairs), **base)
        nominal = float(next(iter(nominals)))
        empirical = sum(covs) / len(covs)
        return EvaluationResult(
            status="EVALUATED", sample_count=len(pairs),
            interval=IntervalMetrics(len(pairs), nominal, empirical,
                                     sum(widths) / len(widths), empirical - nominal), **base)
    return EvaluationResult(status="NOT_EVALUATABLE", reason="UNSUPPORTED_ARTIFACT_TYPE",
                            sample_count=len(pairs), **base)


# ── CalibrationEvidence adapter（2I.1 永不產生 CALIBRATED） ──
def evaluation_result_to_calibration_evidence(result: EvaluationResult) -> dict:
    """把評估結果轉成 calibration evidence 候選（永不 CALIBRATED）。

    2I.1 不 fit calibration model、無 pre-registered acceptance threshold，
    且目前無真實 settled 機率樣本，因此只可能回 INSUFFICIENT_EVIDENCE /
    EVALUATED_UNCALIBRATED。
    """
    if result.status == "EVALUATED":
        status, reason = "EVALUATED_UNCALIBRATED", (
            "2I.1 does not fit a calibration model and has no pre-registered "
            "acceptance threshold; metric values are descriptive only")
    else:
        status = "INSUFFICIENT_EVIDENCE"
        reason = f"evaluation status {result.status}" + (f": {result.reason}" if result.reason else "")
    out = {
        "evidence_status": status,
        "calibration_status": "UNCALIBRATED",
        "reason": reason,
        "fitted_model": False,
        "pre_registered_threshold": False,
        "sample_count": result.sample_count,
        "artifact_type": result.artifact_type,
        "dataset_id": result.dataset_id,
        "partition_role": result.partition_role,
        "schema_version": V2_CALIBRATION_EVALUATION_SCHEMA_VERSION,
    }
    if out["evidence_status"] not in EVIDENCE_STATUSES:
        raise CalibrationEvaluationError("adapter produced a non-2I.1 evidence status")
    return out


# ── 真實資料 readiness（不建立 DB、不補值） ──
def actual_evaluation_readiness(db: PredictionAuditDB | None = None) -> dict:
    """檢查 audit DB 是否已有真實 settled probabilistic samples。

    回傳 ACTUAL_PROBABILITY_EVALUATION / ACTUAL_CALIBRATION_EVIDENCE。
    DB 不存在 -> 直接 NONE_YET（不建立檔案）。
    """
    if db is None:
        if not default_audit_db_path().exists():
            return {
                "db_present": False,
                "prediction_count": 0,
                "settled_event_probability_samples": 0,
                "ACTUAL_PROBABILITY_EVALUATION": "INSUFFICIENT_EVIDENCE",
                "ACTUAL_CALIBRATION_EVIDENCE": "NONE_YET",
            }
        db = PredictionAuditDB()

    settled = 0
    for pid in db.list_prediction_ids():
        pred = db.get_prediction(pid)
        if pred is None:
            continue
        for art in db.get_forecast_artifacts(pid):
            if art.artifact_type != "EVENT_PROBABILITY" or art.value is None:
                continue
            if not (0.0 <= float(art.value) <= 1.0):
                continue
            for out in db.get_outcomes(pid):
                if out.forecast_artifact_id != art.forecast_artifact_id:
                    continue
                if out.actual_value in (0.0, 1.0) and _utc(out.available_at) >= _utc(pred.forecast_origin):
                    settled += 1
    return {
        "db_present": True,
        "prediction_count": len(db.list_prediction_ids()),
        "settled_event_probability_samples": settled,
        "ACTUAL_PROBABILITY_EVALUATION": ("EVALUATED" if settled >= MIN_PROBABILITY_SAMPLES
                                          else "INSUFFICIENT_EVIDENCE"),
        "ACTUAL_CALIBRATION_EVIDENCE": "NONE_YET",
    }


def evaluate_default_db() -> dict:
    """對 default V2-H DB 做正式 readiness 檢查（read-only，不建立 DB）。"""
    return actual_evaluation_readiness()


def pinball_loss(tau: float, predicted: float, actual: float) -> float:
    """單筆 pinball（quantile）loss，供外部驗算。"""
    return (tau - (1.0 if actual < predicted else 0.0)) * (actual - predicted)


def brier_score(pairs: list[tuple[float, float]]) -> float:
    if not pairs:
        raise CalibrationEvaluationError("empty pairs")
    return sum((p - y) ** 2 for p, y in pairs) / len(pairs)


def log_loss(pairs: list[tuple[float, float]], epsilon: float = LOG_LOSS_EPSILON) -> float:
    if not pairs:
        raise CalibrationEvaluationError("empty pairs")
    if not (0.0 < epsilon < 0.5):
        raise CalibrationEvaluationError("epsilon must be in (0, 0.5)")
    return -sum(
        y * math.log(min(max(p, epsilon), 1.0 - epsilon))
        + (1 - y) * math.log(min(max(1 - p, epsilon), 1.0 - epsilon))
        for p, y in pairs) / len(pairs)


def schema_version() -> str:
    return V2_CALIBRATION_EVALUATION_SCHEMA_VERSION
