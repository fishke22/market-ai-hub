"""Phase 2Q-F.3 — UAT truthfulness remediation tests（contract / agreement / calendar / timezone / no-trading-advice）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, "src")
ROOT = Path(__file__).resolve().parents[1]


# ── HIGH-5：contract selection determinism ──

def test_front_contract_selection_deterministic():
    from market_ai_hub.packet.builder import _select_front_contract

    contracts = ["202703", "202610", "202612", "202611"]
    # FRONT_NEAREST_LISTED：最早到期 = 202610，不依 row order
    assert _select_front_contract(contracts) == "202610"
    # shuffle 100 次結果相同
    import random

    for _ in range(100):
        random.shuffle(contracts)
        assert _select_front_contract(contracts) == "202610"


def test_front_contract_not_far_month():
    from market_ai_hub.packet.builder import _select_front_contract

    # 2026-09-18 同一天 4 active contracts → 應選 202610，非 202703
    assert _select_front_contract(["202610", "202611", "202612", "202703"]) == "202610"


# ── HIGH-4：validated direction agreement ──

def test_validated_agreement_zero_eligible_is_na():
    from datetime import datetime, timezone

    from market_ai_hub.ensemble.ensemble import ensemble_equal_weight
    from market_ai_hub.schemas.market_data import DataGrade, ForecastOutput

    def _clf(model, direction):
        return ForecastOutput(
            model=model, symbol="X", as_of=datetime.now(timezone.utc), horizon="1d",
            point_forecast=100.0, expected_return=0.0,
            quantiles={"p10": None, "p50": None, "p90": None},
            direction=direction, confidence=0.5, data_grade=DataGrade.RESEARCH_PROXY,
            model_task="DIRECTION_CLASSIFICATION",
            eligible_for_direction_vote=False,  # 兩者都不 eligible
        )

    ens = ensemble_equal_weight([_clf("xgboost", "down"), _clf("lightgbm", "down")], "X", "1d")
    mm = ens.model_metadata
    assert mm["eligible_direction_vote_count"] == 0
    assert mm["final_direction"] == "NO_VALIDATED_MODEL_CONSENSUS"
    assert mm["validated_direction_agreement"] == "N/A"
    # raw agreement 不得當 consensus
    assert mm["legacy_raw_unvalidated_agreement"] in ("HIGH", "MEDIUM", "LOW")


# ── HIGH-1：OSE derivatives holiday trading calendar ──

def test_ose_holiday_trading_sessions():
    from market_ai_hub.services.calendar import next_ose_derivatives_sessions

    sessions = next_ose_derivatives_sessions("2026-09-18", 5)
    # 9/21-23 是 Holiday Trading（TSE cash 休市但 OSE OPEN）
    assert "2026-09-21" in sessions
    assert "2026-09-22" in sessions
    assert "2026-09-23" in sessions


def test_ose_calendar_split_from_xtks():
    from market_ai_hub.services.calendar import next_ose_derivatives_sessions, next_trading_sessions

    ose = next_ose_derivatives_sessions("2026-09-18", 5)
    cash = next_trading_sessions("^N225", "2026-09-18", 5)
    # TSE cash 9/21-23 休市（不在 cash 列表），但 OSE 列表包含
    assert "2026-09-21" not in cash
    assert "2026-09-21" in ose


# ── HIGH-8：Taiwan timezone ──

def test_taiwan_yfinance_timezone():
    from market_ai_hub.providers.yfinance_provider import _local_tz_for

    assert _local_tz_for("^TWII") == "Asia/Taipei"
    assert _local_tz_for("2330.TW") == "Asia/Taipei"
    assert _local_tz_for("3706.TWO") == "Asia/Taipei"
    assert _local_tz_for("^N225") == "Asia/Tokyo"


# ── HIGH-3：no trading advice in skills/prompt ──

def test_no_trading_advice_in_skills_and_prompt():
    osaka = (ROOT / "skills" / "osaka-micro-analysis" / "SKILL.md").read_text(encoding="utf-8")
    taiwan = (ROOT / "skills" / "taiwan-stock-v28" / "SKILL.md").read_text(encoding="utf-8")
    prompt = (ROOT / "docs" / "prompts" / "SYSTEM_PROMPT_V4_1_COMPACT.md").read_text(encoding="utf-8")

    # skills 明寫禁止交易建議 + support/resistance NOT_AVAILABLE
    assert "不得輸出" in osaka
    assert "research reference only" in osaka or "research reference only" in taiwan
    assert "NO_VALIDATED_MODEL_CONSENSUS" in osaka
    assert "NO_VALIDATED_MODEL_CONSENSUS" in taiwan
    assert "NOT_AVAILABLE" in osaka
    # prompt 明寫不得交易建議 + quantile 不當 support
    assert "不得輸出任何交易建議" in prompt


def test_direct_micro_forecast_status_in_packet():
    from market_ai_hub.packet.builder import build_analysis_packet

    p = build_analysis_packet(market="osaka", detail_level="compact", save_analysis=False)
    assert p["target_semantics"]["direct_micro_forecast_status"] == "NOT_AVAILABLE"


def test_training_review_no_auto_retrain():
    from market_ai_hub.mcp import server as s

    g = s.get_research_gates()
    tr = g["training_review"]
    assert tr["auto_train"] is False
    assert tr["immediate_retrain_authorized"] is False
    assert tr["manual_approval_required"] is True
