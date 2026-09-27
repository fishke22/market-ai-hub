"""Current research evidence summary (ValidationTruth).

Accuracy v2 is the current authority.  The older Phase 2 freeze remains
available only as legacy evidence/provenance and must never overwrite the
newer blocked-horizon / no-improvement conclusions.
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

from market_ai_hub.config.settings import project_root

log = logging.getLogger(__name__)

_FREEZE_PATH = project_root() / "research" / "phase2" / "freeze" / "PHASE2_RESEARCH_FREEZE.yaml"

# 證據層級（§8）：DATA → HISTORICAL → CAUSAL → ECONOMIC → FORWARD
EVIDENCE_LAYERS = ("proxy_historical", "direct_micro_historical", "causal", "economic", "forward")

CURRENT_OSAKA_DIRECT_HISTORICAL = "BLOCKED_HORIZON_MISMATCH"
CURRENT_OSAKA_DEVELOPMENT = "NO_IMPROVEMENT_BASELINE_RETAINED"
CURRENT_OSAKA_CAUSAL = "NOT_ESTABLISHED_CURRENT_ACCURACY_V2"


def _load_freeze() -> dict:
    if not _FREEZE_PATH.exists():
        log.warning("research/phase2/freeze/PHASE2_RESEARCH_FREEZE.yaml not found; research truth unavailable")
        return {}
    return yaml.safe_load(_FREEZE_PATH.read_text(encoding="utf-8")) or {}


def research_evidence_summary() -> dict:
    """Return current Accuracy v2 truth while preserving the old freeze as legacy."""
    fz = _load_freeze()
    hist = fz.get("historical_conclusions", {})
    legacy_direct = hist.get("direct_micro_forecast", "NONE")
    legacy_causal = fz.get("causality_conclusion", "NONE")
    return {
        "source": "ACCURACY_V2_CURRENT",
        "legacy_source": "PHASE2_RESEARCH_FREEZE",
        "frozen_at": fz.get("frozen_at", ""),
        "proxy_historical": hist.get("proxy_exam", "NO_EVIDENCE"),
        "direct_micro_historical": CURRENT_OSAKA_DIRECT_HISTORICAL,
        "direct_micro_development": CURRENT_OSAKA_DEVELOPMENT,
        "causal": CURRENT_OSAKA_CAUSAL,
        "economic": fz.get("strategy_conclusion", "NO_ECONOMIC_EDGE"),
        "forward": {
            "activation": "2026-09-28",
            "evidence_status": "NONE_YET",
            "infrastructure": "Accuracy v2 P5 immutable forward monitor ready",
            "runtime_truth_source": "get_forward_test_status",
        },
        "legacy_phase2": {
            "direct_micro_historical": legacy_direct,
            "causal": legacy_causal,
            "note": "historical only; superseded for current claims by Accuracy v2",
        },
        "strategy_candidate": "NONE",
        "production_candidate": "NONE",
        "forbidden_claims": sorted(set(
            list(fz.get("forbidden_claims", []))
            + ["predictive gain confirmed", "calibrated probability", "fixed win rate"]
        )),
    }


def validation_truth() -> dict:
    """gate 用的權威 validation truth（直接映射 §8 五層）。"""
    s = research_evidence_summary()
    return {
        "proxy_historical": s["proxy_historical"],
        "direct_micro_historical": s["direct_micro_historical"],
        "direct_micro_development": s["direct_micro_development"],
        "causal": s["causal"],
        "economic": s["economic"],
        "forward": s["forward"],
    }


# ── Phase 2Q-C §21：evidence per target family/target ──
# 證據必須按市場隔離，禁止用 Osaka evidence 替 Taiwan 背書。

def evidence_by_target() -> dict:
    """以 target_family → target → 各證據層 的結構回 evidence。

    OSAKA_MICRO 映射 frozen evidence；TAIWAN_STOCK / TAIWAN_INDEX 尚未 historical-validated，
    誠實標 NO_EVIDENCE / NOT_YET_VALIDATED（不可假裝已驗證）。
    """
    s = research_evidence_summary()
    return {
        "OSAKA_MICRO": {
            "OSE_NIKKEI225_MICRO_FUTURES": {
                "proxy_historical": s["proxy_historical"],
                "direct_micro_historical": s["direct_micro_historical"],
                "direct_micro_development": s["direct_micro_development"],
                "causal": s["causal"],
                "economic": s["economic"],
                "forward": s["forward"]["evidence_status"],
            },
        },
        "TAIWAN_STOCK": {
            "TAIWAN_INDIVIDUAL_STOCK": {
                "proxy_historical": "NO_EVIDENCE",
                "historical_oos": "NOT_YET_VALIDATED",
                "direct_historical": "NOT_YET_VALIDATED",  # compat alias
                "causal": "NOT_ESTABLISHED",
                "economic": "NOT_ESTABLISHED",
                "forward": "NOT_YET_VALIDATED",
            },
        },
        "TAIWAN_INDEX": {
            "TAIEX": {
                "proxy_historical": "NO_EVIDENCE",
                "historical_oos": "NOT_YET_VALIDATED",
                "direct_historical": "NOT_YET_VALIDATED",  # compat alias
                "causal": "NOT_ESTABLISHED",
                "economic": "NOT_ESTABLISHED",
                "execution_validation": "NOT_ESTABLISHED",
                "forward": "NOT_YET_VALIDATED",
            },
        },
    }


def evidence_for(family: str, target: str = "") -> dict:
    """取單一 target 的 evidence。

    - 精確 target 命中 → 回該 target。
    - TAIWAN_STOCK 之 target 為動態代碼（如 3706.TW）→ fallback 到 family 預設 entry。
    - 未知 family → 全 NO_EVIDENCE / NOT_YET_VALIDATED（不得繼承 Osaka）。
    """
    by = evidence_by_target().get(family, {})
    if target and target in by:
        return by[target]
    # fallback：family 預設 entry（TAIWAN_STOCK 動態代碼用）
    if by:
        return next(iter(by.values()))
    return {
        "proxy_historical": "NO_EVIDENCE",
        "historical_oos": "NOT_YET_VALIDATED",
        "causal": "NOT_ESTABLISHED",
        "economic": "NOT_ESTABLISHED",
        "forward": "NOT_YET_VALIDATED",
        "status": "UNKNOWN_TARGET",
    }


def economic_gate_explanation() -> str:
    """TRADING_EDGE_GATE 的誠實解釋（§9）。不得說 cost model missing。"""
    return (
        "Phase2 cost/slippage strategy validation completed; "
        "result NO_ECONOMIC_EDGE."
    )


def model_gate_explanation() -> str:
    """MODEL_PREDICTIVE_GATE 的誠實解釋（§9）。UNPROVEN = general production gate，非 NO_OOS_TEST_EXISTS。"""
    return (
        "GENERAL_PRODUCTION_MODEL_GATE_UNPROVEN: "
        "current Accuracy v2 evidence has a blocked historical horizon artifact and "
        "a development NO_IMPROVEMENT / BASELINE_RETAINED result; no forward-validated "
        "production model exists."
    )


def mase_wording(mase: float | None) -> str:
    """MASE 語義（§11）：≈1 = baseline-level，<1 = lower-than-scaling-baseline，皆非獲利/勝率。"""
    if mase is None:
        return "MASE not available"
    if mase >= 0.95 and mase <= 1.05:
        return "roughly baseline-level error"
    if mase < 1.0:
        return "lower error than specified scaling baseline in that exam"
    return "higher error than specified scaling baseline"
