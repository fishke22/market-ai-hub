"""Pure-text Yuanta/iTRADER smart-order advisory translator.

No broker API is imported or called here. This module cannot inspect accounts,
positions or balances and cannot submit or mutate orders.
"""
from __future__ import annotations

import math
from typing import Any


SCHEMA_VERSION = "BROKER.ADVISORY.1"
JNU_TICK_POINTS = 5.0
JNU_MULTIPLIER_JPY_PER_POINT = 10.0
JNU_TICK_VALUE_JPY = JNU_TICK_POINTS * JNU_MULTIPLIER_JPY_PER_POINT
UI_MAPPING_STATUS = "PARTIALLY_VERIFIED_PUBLIC_YUANTA_CONDITION_ORDER_CONCEPTS"


def _finite(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _positive_int(value: Any) -> int | None:
    try:
        out = int(value)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None


def _ticks(value: Any) -> dict[str, Any] | None:
    n = _positive_int(value)
    if n is None:
        return None
    return {
        "ticks": n,
        "points": float(n * JNU_TICK_POINTS),
        "jpy_per_contract": float(n * JNU_TICK_VALUE_JPY),
    }


def itrader_smart_order_guidance(
    *,
    strategy: str = "OCO",
    instrument: str = "JNU",
    position_side: str | None = None,
    quantity: int | None = None,
    cost_price: float | None = None,
    take_profit_price: float | None = None,
    stop_loss_price: float | None = None,
    trigger_price: float | None = None,
    trail_activation_ticks: int | None = None,
    trail_retrace_ticks: int | None = None,
    pre_activation_stop_ticks: int | None = None,
) -> dict[str, Any]:
    """Return advisory text fields only; never sends an order."""
    strategy = str(strategy or "OCO").upper()
    if strategy not in {"GENERAL", "OCO", "TRAILING"}:
        raise ValueError("strategy must be GENERAL, OCO or TRAILING")
    side = str(position_side or "").upper()
    if side not in {"", "LONG", "SHORT"}:
        raise ValueError("position_side must be LONG, SHORT or omitted")
    qty = _positive_int(quantity)
    close_side = "SELL" if side == "LONG" else "BUY" if side == "SHORT" else None
    personalized = bool(side and qty)

    common = {
        "schema_version": SCHEMA_VERSION,
        "status": "ADVISORY_ONLY",
        "ui_mapping_status": UI_MAPPING_STATUS,
        "strategy": strategy,
        "instrument": str(instrument or "JNU"),
        "personalized_from_explicit_user_inputs": personalized,
        "position_side": side or None,
        "quantity": qty,
        "closing_side": close_side,
        "cost_price": _finite(cost_price),
        "no_order": True,
        "no_trading": True,
        "no_account_access": True,
        "no_position_query": True,
        "no_broker_login": True,
        "no_broker_mutation": True,
        "jnu_reference": {
            "tick_size_points": JNU_TICK_POINTS,
            "multiplier_jpy_per_point": JNU_MULTIPLIER_JPY_PER_POINT,
            "tick_value_jpy_per_contract": JNU_TICK_VALUE_JPY,
        },
        "mandatory_checks": [
            "在目前使用的元大/iTRADER版本中確認實際策略名稱與畫面欄位。",
            "確認商品與限月正確。",
            "確認買賣方向與平倉方向正確；多單平倉為賣出、空單平倉為買進。",
            "確認口數與有效期限。",
            "設定後到有效策略／智能單查詢畫面確認條件仍存在且內容正確。",
            "若手動減碼或平倉，必須同步修改或取消原智能單，避免剩餘條件單造成反向新倉。",
        ],
        "evidence_note": (
            "元大公開資料可驗證停損利、移動鎖利與OCO/二擇一等條件單概念；"
            "本系統不把特定App畫面名稱視為穩定API契約。"
        ),
    }

    if strategy == "GENERAL":
        common["template"] = {
            "concept": "單一條件觸發後由使用者在券商App設定委託",
            "monitor_instrument": str(instrument or "JNU"),
            "trigger_price": _finite(trigger_price),
            "closing_side": close_side,
            "quantity": qty,
            "requires_explicit_trigger": _finite(trigger_price) is None,
            "requires_explicit_side_and_quantity_for_closing_order": not personalized,
        }
    elif strategy == "OCO":
        common["template"] = {
            "concept": "二擇一 / OCO：其中一個條件執行後，另一個策略應依券商規則取消或失效",
            "take_profit_trigger": _finite(take_profit_price),
            "stop_loss_trigger": _finite(stop_loss_price),
            "closing_side": close_side,
            "quantity": qty,
            "requires_explicit_take_profit": _finite(take_profit_price) is None,
            "requires_explicit_stop_loss": _finite(stop_loss_price) is None,
            "requires_explicit_side_and_quantity": not personalized,
        }
    else:
        common["template"] = {
            "concept": "移動停損／移動鎖利文字設定參考",
            "activation": _ticks(trail_activation_ticks),
            "retrace": _ticks(trail_retrace_ticks),
            "pre_activation_stop": _ticks(pre_activation_stop_ticks),
            "closing_side": close_side,
            "quantity": qty,
            "requires_explicit_side_and_quantity": not personalized,
        }

    if not personalized:
        common["personalization_blocked_reason"] = (
            "未同時取得使用者本次明確提供的多/空方向與口數；系統只回傳空白模板，不推測持倉。"
        )
    return common
