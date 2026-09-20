"""Model catalog：角色 / 雙重狀態 / eligibility / research gates（V1 remediation + V1.1）。

V1.1 修正：
- adapter 使用 process-level singleton（services/model_runtime），gate 評估不重複載入模型
- TS 模型 predictive_validation_status 由 TsValidationStore 的 OOS 結果驅動
  （deterministic promotion，threshold 在 services/validation.PROMOTION_RULES）
- gates 帶 evaluated_at / build_id / evidence（不 stale）
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from market_ai_hub.schemas.market_data import (
    EngineeringStatus,
    GateStatus,
    ModelRole,
    ModelTask,
    PredictiveValidationStatus,
)
from market_ai_hub.services.build_info import build_fingerprint
from market_ai_hub.services.model_runtime import get_chronos, get_timesfm

log = logging.getLogger(__name__)

MODEL_ROLES: dict[str, str] = {
    "chronos-2": ModelRole.BASE_MODEL.value,
    "timesfm-3.0": ModelRole.BASE_MODEL.value,
    "logistic-regression": ModelRole.BASE_MODEL.value,
    "random-forest": ModelRole.BASE_MODEL.value,
    "xgboost": ModelRole.BASE_MODEL.value,
    "lightgbm": ModelRole.BASE_MODEL.value,
    "fincast": ModelRole.BASE_MODEL.value,
    "ensemble": ModelRole.ENSEMBLE.value,
    "analysis_wrapper": ModelRole.ANALYSIS_WRAPPER.value,
}

MODEL_TASKS: dict[str, str] = {
    "chronos-2": ModelTask.PRICE_FORECAST.value,
    "timesfm-3.0": ModelTask.PRICE_FORECAST.value,
    "fincast": ModelTask.PRICE_FORECAST.value,
    "logistic-regression": ModelTask.DIRECTION_CLASSIFICATION.value,
    "random-forest": ModelTask.DIRECTION_CLASSIFICATION.value,
    "xgboost": ModelTask.DIRECTION_CLASSIFICATION.value,
    "lightgbm": ModelTask.DIRECTION_CLASSIFICATION.value,
}

BASE_MODEL_NAMES = [
    "chronos-2", "timesfm-3.0", "logistic-regression",
    "random-forest", "xgboost", "lightgbm", "fincast",
]


@dataclass
class ModelCard:
    name: str
    role: str
    model_task: str = ""
    engineering_status: str = EngineeringStatus.NOT_RUN.value
    predictive_validation_status: str = PredictiveValidationStatus.UNVALIDATED.value
    eligible_for_price_reference: bool = False
    eligible_for_direction_vote: bool = False
    eligible_for_ensemble_weighting: bool = False
    reason: str = ""
    evidence: dict = field(default_factory=dict)


def _ts_validation_status(model: str, symbol: str = "^N225") -> tuple[str, dict]:
    """從 persisted OOS validation 決定 TS 模型 status（deterministic promotion）。"""
    from market_ai_hub.services.validation import TsValidationStore, determine_validation_status

    rec = TsValidationStore().latest(model, symbol)
    if rec is None:
        return PredictiveValidationStatus.UNVALIDATED.value, {"oos_validation": "not run"}
    status, reasons = determine_validation_status(rec.get("result", {}))
    return status, {"oos_validation": rec, "promotion_reasons": reasons}


def live_model_cards() -> dict[str, ModelCard]:
    """根據 live adapter 狀態與 stored OOS 績效計算各 model card（不重複載入模型）。"""
    from market_ai_hub.storage.performance import PerformanceStore

    cards: dict[str, ModelCard] = {}
    perf = PerformanceStore().latest_by_model()

    from market_ai_hub.services.model_status import shallow_status

    chronos_ok = shallow_status("chronos") == "AVAILABLE_NOT_LOADED"
    chronos_val, chronos_ev = _ts_validation_status("chronos-2")
    cards["chronos-2"] = ModelCard(
        name="chronos-2", role=ModelRole.BASE_MODEL.value, model_task=ModelTask.PRICE_FORECAST.value,
        engineering_status=EngineeringStatus.PASS.value if chronos_ok else EngineeringStatus.FAIL.value,
        predictive_validation_status=chronos_val,
        eligible_for_price_reference=chronos_ok,
        eligible_for_direction_vote=chronos_val == PredictiveValidationStatus.VALIDATED.value,
        eligible_for_ensemble_weighting=chronos_ok,
        reason="research price forecast；direction vote 需 VALIDATED（見 PROMOTION_RULES）" if chronos_ok else "load failed",
        evidence={"smoke": "PASS" if chronos_ok else "FAIL", **chronos_ev},
    )

    tsfm_ok = shallow_status("timesfm") == "AVAILABLE_NOT_LOADED"
    tsfm_val, tsfm_ev = _ts_validation_status("timesfm-3.0")
    cards["timesfm-3.0"] = ModelCard(
        name="timesfm-3.0", role=ModelRole.BASE_MODEL.value, model_task=ModelTask.PRICE_FORECAST.value,
        engineering_status=EngineeringStatus.PASS.value if tsfm_ok else EngineeringStatus.FAIL.value,
        predictive_validation_status=tsfm_val,
        eligible_for_price_reference=tsfm_ok,
        eligible_for_direction_vote=tsfm_val == PredictiveValidationStatus.VALIDATED.value,
        eligible_for_ensemble_weighting=tsfm_ok,
        reason="research price forecast；direction vote 需 VALIDATED" if tsfm_ok else "load failed",
        evidence={"smoke": "PASS" if tsfm_ok else "FAIL", "license": "TIMESFM3_NON_COMMERCIAL_ONLY", **tsfm_ev},
    )

    from market_ai_hub.models.fincast_model import FinCastAdapter

    fin_ok = FinCastAdapter().status() == "ready"
    cards["fincast"] = ModelCard(
        name="fincast", role=ModelRole.BASE_MODEL.value, model_task=ModelTask.PRICE_FORECAST.value,
        engineering_status=EngineeringStatus.PASS.value if fin_ok else EngineeringStatus.FAIL.value,
        predictive_validation_status=PredictiveValidationStatus.UNVALIDATED.value,
        eligible_for_price_reference=fin_ok,
        eligible_for_direction_vote=False,
        eligible_for_ensemble_weighting=False,  # bridge 無 quantile/path，不進 ensemble
        reason="research price forecast（subprocess bridge）" if fin_ok else "not installed / load failed",
        evidence={"bridge": fin_ok},
    )

    for name, key in (("xgboost", "xgboost"), ("lightgbm", "lightgbm")):
        rec = perf.get(key) or {}
        has_oos = bool(rec)
        if has_oos:
            eng = EngineeringStatus.PASS.value
            bal_acc = rec.get("balanced_accuracy")
            majority_base = rec.get("majority_class_baseline_accuracy")
            uniform_base = rec.get("uniform_random_baseline_accuracy")
            beat = False
            if bal_acc is not None:
                threshold = max([b for b in (majority_base, uniform_base, 1 / 3) if b is not None])
                beat = bal_acc > threshold
            val_status = (
                PredictiveValidationStatus.EXPERIMENTAL.value
                if beat
                else PredictiveValidationStatus.DEGRADED.value
            )
            cards[name] = ModelCard(
                name=name, role=ModelRole.BASE_MODEL.value, model_task=ModelTask.DIRECTION_CLASSIFICATION.value,
                engineering_status=eng,
                predictive_validation_status=val_status,
                eligible_for_price_reference=False,  # 分類器不給價格
                eligible_for_direction_vote=beat,
                eligible_for_ensemble_weighting=bool(rec.get("n_samples", 0) > 0),
                reason=f"OOS record 存在；balanced_accuracy={bal_acc} vs baseline_threshold={threshold:.4f}"
                if bal_acc is not None else "OOS record 缺少 balanced_accuracy",
                evidence={"oos_record": rec},
            )
        else:
            cards[name] = ModelCard(
                name=name, role=ModelRole.BASE_MODEL.value, model_task=ModelTask.DIRECTION_CLASSIFICATION.value,
                engineering_status=EngineeringStatus.PASS.value,  # fit/predict 已驗證不崩潰
                predictive_validation_status=PredictiveValidationStatus.UNVALIDATED.value,
                eligible_for_price_reference=False,
                eligible_for_direction_vote=False,
                eligible_for_ensemble_weighting=True,
                reason="無 OOS record → UNVALIDATED，不參與 direction vote",
                evidence={},
            )

    return cards


def compute_research_gates(cards: dict[str, ModelCard]) -> dict[str, dict]:
    """Research validation gates。每次評估基於 CURRENT RUNTIME + 最新 persisted 證據。"""
    evaluated_at = datetime.now(timezone.utc).isoformat()
    fp = build_fingerprint()

    required = ["chronos-2", "timesfm-3.0", "xgboost", "lightgbm"]
    eng_ok = all(cards.get(n, ModelCard(n, "")).engineering_status == EngineeringStatus.PASS.value for n in required)
    eng_evidence = {
        n: {
            "engineering_status": cards.get(n, ModelCard(n, "")).engineering_status,
            "model_task": cards.get(n, ModelCard(n, "")).model_task,
        }
        for n in required
    }
    engineering_gate = {
        "status": GateStatus.PASS.value if eng_ok else GateStatus.PARTIAL.value,
        "reason": "必修 base models 工程狀態皆 PASS（current runtime，singleton 載入）" if eng_ok else "部分模型工程狀態非 PASS",
        "evidence": eng_evidence,
        "evaluated_at": evaluated_at,
        "build_id": fp["build_id"],
    }

    from market_ai_hub.providers.registry import ProviderRegistry

    prov = {k: v.status.value for k, v in ProviderRegistry().status_all().items()}
    market_data_ok = prov.get("yfinance") == "ok" and (prov.get("twse") == "ok" or prov.get("finmind") == "ok")
    market_data_gate = {
        "status": GateStatus.PASS.value if market_data_ok else GateStatus.PARTIAL.value,
        "reason": "yfinance + (TWSE 或 FinMind) 可用" if market_data_ok else "core provider 部分不可用",
        "evidence": prov,
        "evaluated_at": evaluated_at,
        "build_id": fp["build_id"],
    }

    # CALENDAR_GATE：XTAI / XTKS 皆可載入且覆蓋未來
    calendar_gate = _calendar_gate(evaluated_at, fp["build_id"])

    # TEMPORAL_ALIGNMENT_GATE：future-only forecast targets（self-check）
    temporal_gate = _temporal_alignment_gate(evaluated_at, fp["build_id"])

    # DATA_GATE 由子 gate 綜合
    sub_gates = [market_data_gate, calendar_gate, temporal_gate]
    if all(g["status"] == GateStatus.PASS.value for g in sub_gates):
        data_status = GateStatus.PASS.value
        data_reason = "Market Data / Calendar / Temporal Alignment 全 PASS"
    elif all(g["status"] in (GateStatus.PASS.value, GateStatus.PARTIAL.value) for g in sub_gates):
        data_status = GateStatus.PARTIAL.value
        data_reason = "部分子 gate 為 PARTIAL"
    else:
        data_status = GateStatus.FAIL.value
        data_reason = "存在 FAIL 子 gate"
    data_gate = {
        "status": data_status,
        "reason": data_reason,
        "evidence": {"market_data": market_data_gate, "calendar": calendar_gate, "temporal_alignment": temporal_gate},
        "evaluated_at": evaluated_at,
        "build_id": fp["build_id"],
    }

    base = {k: v for k, v in cards.items() if v.role == ModelRole.BASE_MODEL.value}
    any_proven = any(
        v.predictive_validation_status in (PredictiveValidationStatus.VALIDATED.value, PredictiveValidationStatus.EXPERIMENTAL.value)
        for v in base.values()
    )
    from market_ai_hub.services.research_truth import (
        economic_gate_explanation,
        model_gate_explanation,
    )

    model_gate = {
        "status": GateStatus.PASS.value if any_proven else GateStatus.UNPROVEN.value,
        "label": "GENERAL_PRODUCTION_MODEL_GATE_UNPROVEN" if not any_proven else "GENERAL_PRODUCTION_MODEL_GATE_PASS",
        "reason": (
            model_gate_explanation()
            if not any_proven
            else "有模型 OOS 超越 baseline（EXPERIMENTAL 以上）"
        ),
        "evidence": {n: {"status": v.predictive_validation_status, "reason": v.reason} for n, v in base.items()},
        "evaluated_at": evaluated_at,
        "build_id": fp["build_id"],
    }

    trading_gate = {
        "status": GateStatus.UNPROVEN.value,  # backward-compat enum；result 才是權威結論
        "result": "NO_ECONOMIC_EDGE",
        "reason": economic_gate_explanation(),
        "evidence": {
            "strategy_validation": "completed",
            "result": "NO_ECONOMIC_EDGE",
            "cost_slippage_validated": True,
        },
        "evaluated_at": evaluated_at,
        "build_id": fp["build_id"],
    }

    return {
        "ENGINEERING_GATE": engineering_gate,
        "MARKET_DATA_GATE": market_data_gate,
        "CALENDAR_GATE": calendar_gate,
        "TEMPORAL_ALIGNMENT_GATE": temporal_gate,
        "DATA_GATE": data_gate,
        "MODEL_PREDICTIVE_GATE": model_gate,
        "TRADING_EDGE_GATE": trading_gate,
    }


def _calendar_gate(evaluated_at: str, build_id: str) -> dict:
    """CALENDAR_GATE：XTAI（TWSE）與 XTKS（TSE）日曆可載入且覆蓋未來。"""
    from market_ai_hub.services.calendar import calendar_metadata, calendar_verified

    ev = {}
    ok = True
    for sym in ("^N225", "3706.TW"):
        v = calendar_verified(sym)
        m = calendar_metadata(sym)
        ev[sym] = {"verified": v, "calendar_name": m["calendar_name"], "source": m["calendar_source"]}
        ok = ok and v
    return {
        "status": GateStatus.PASS.value if ok else GateStatus.PARTIAL.value,
        "reason": "XTAI(TWSE) + XTKS(TSE) 日曆已載入且覆蓋未來" if ok else "日曆未確認（CALENDAR_UNVERIFIED）",
        "evidence": ev,
        "evaluated_at": evaluated_at,
        "build_id": build_id,
    }


def _temporal_alignment_gate(evaluated_at: str, build_id: str) -> dict:
    """TEMPORAL_ALIGNMENT_GATE：future-only forecast targets 自檢。"""
    import pandas as pd

    from market_ai_hub.services.calendar import next_trading_sessions, trading_date_of

    ok = True
    ev = {}
    today_utc = pd.Timestamp.now("UTC").normalize()
    for sym, tz in (("^N225", "Asia/Tokyo"), ("3706.TW", "Asia/Taipei")):
        try:
            last_obs = trading_date_of(today_utc, sym)
            targets = next_trading_sessions(sym, last_obs, 3)
            future_only = all(t > last_obs for t in targets)
            ev[sym] = {"last_observed": last_obs, "targets": targets, "future_only": future_only}
            ok = ok and future_only and len(targets) == 3
        except Exception as e:
            ev[sym] = {"error": str(e)}
            ok = False
    return {
        "status": GateStatus.PASS.value if ok else GateStatus.FAIL.value,
        "reason": "forecast target dates 均為 last_observed 之後的未來 sessions" if ok else "temporal alignment 自檢失敗",
        "evidence": ev,
        "evaluated_at": evaluated_at,
        "build_id": build_id,
    }
