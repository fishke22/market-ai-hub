"""Phase 2Q-A — single-source research evidence summary（ValidationTruth）。

以 `research/phase2/freeze/PHASE2_RESEARCH_FREEZE.yaml`（權威 historical research state）為單一來源。
所有 packet / gate / leaderboard 引用此函式，避免不同 tool 各說各話：
- 不再輸出「尚未做 OOS」→ OOS 已做，結論 NO_EVIDENCE / STATISTICAL_FORECAST_EVIDENCE。
- 不再輸出「cost model missing」→ cost/slippage 已做，結論 NO_ECONOMIC_EDGE。
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


def _load_freeze() -> dict:
    if not _FREEZE_PATH.exists():
        log.warning("research/phase2/freeze/PHASE2_RESEARCH_FREEZE.yaml not found; research truth unavailable")
        return {}
    return yaml.safe_load(_FREEZE_PATH.read_text(encoding="utf-8")) or {}


def research_evidence_summary() -> dict:
    """權威研究狀態（single source）。forward 為 runtime current truth，此處回 metadata。"""
    fz = _load_freeze()
    hist = fz.get("historical_conclusions", {})
    return {
        "source": "PHASE2_RESEARCH_FREEZE",
        "frozen_at": fz.get("frozen_at", ""),
        "proxy_historical": hist.get("proxy_exam", "NO_EVIDENCE"),
        "direct_micro_historical": hist.get("direct_micro_forecast", "NONE"),
        "causal": fz.get("causality_conclusion", "NONE"),
        "economic": fz.get("strategy_conclusion", "NO_ECONOMIC_EDGE"),
        "forward": {
            "activation": fz.get("forward", {}).get("activation", ""),
            "evidence_status": fz.get("forward", {}).get("evidence_status", "NONE_YET"),
            "infrastructure": fz.get("forward", {}).get("infrastructure", ""),
            "runtime_truth_source": "get_forward_test_status",
        },
        "strategy_candidate": fz.get("strategy_candidate", "NONE"),
        "production_candidate": fz.get("production_candidate", "NONE"),
        "forbidden_claims": fz.get("forbidden_claims", []),
    }


def validation_truth() -> dict:
    """gate 用的權威 validation truth（直接映射 §8 五層）。"""
    s = research_evidence_summary()
    return {
        "proxy_historical": s["proxy_historical"],
        "direct_micro_historical": s["direct_micro_historical"],
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
                "causal": s["causal"],
                "economic": s["economic"],
                "forward": s["forward"]["evidence_status"],
            },
        },
        "TAIWAN_STOCK": {
            "TAIWAN_INDIVIDUAL_STOCK": {
                "proxy_historical": "NO_EVIDENCE",
                "direct_historical": "NOT_YET_VALIDATED",
                "causal": "NOT_YET_VALIDATED",
                "economic": "NO_ECONOMIC_EDGE",
                "forward": "NOT_YET_VALIDATED",
            },
        },
        "TAIWAN_INDEX": {
            "TAIEX": {
                "proxy_historical": "NO_EVIDENCE",
                "direct_historical": "NOT_YET_VALIDATED",
                "causal": "NOT_YET_VALIDATED",
                "economic": "NO_ECONOMIC_EDGE",
                "forward": "NOT_YET_VALIDATED",
            },
        },
    }


def evidence_for(family: str, target: str = "") -> dict:
    """取單一 target 的 evidence（找不到 → 全 NO_EVIDENCE / NOT_YET_VALIDATED）。"""
    by = evidence_by_target().get(family, {})
    if target:
        return by.get(target, {"status": "UNKNOWN_TARGET"})
    # 回 family 下第一個 target（通常唯一）
    return next(iter(by.values()), {"status": "UNKNOWN_TARGET"})


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
        "historical statistical signal exists but no forward-validated production model."
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
