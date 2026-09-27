import market_ai_hub.services.itrader_advisory as ia


def test_itrader_guidance_is_advisory_only_and_never_touches_broker():
    out = ia.itrader_smart_order_guidance(strategy="OCO")
    assert out["status"] == "ADVISORY_ONLY"
    assert out["no_order"] is True
    assert out["no_trading"] is True
    assert out["no_account_access"] is True
    assert out["no_position_query"] is True
    assert out["no_broker_login"] is True
    assert out["no_broker_mutation"] is True
    assert out["personalized_from_explicit_user_inputs"] is False
    assert out["quantity"] is None
    assert out["closing_side"] is None


def test_itrader_oco_uses_explicit_long_position_closing_side():
    out = ia.itrader_smart_order_guidance(
        strategy="OCO",
        instrument="JNU2612",
        position_side="LONG",
        quantity=2,
        cost_price=66200,
        take_profit_price=67000,
        stop_loss_price=65800,
    )
    assert out["personalized_from_explicit_user_inputs"] is True
    assert out["closing_side"] == "SELL"
    assert out["quantity"] == 2
    assert out["template"]["take_profit_trigger"] == 67000.0
    assert out["template"]["stop_loss_trigger"] == 65800.0
    assert any("反向新倉" in x for x in out["mandatory_checks"])


def test_itrader_short_closing_side_is_buy():
    out = ia.itrader_smart_order_guidance(
        strategy="OCO",
        position_side="SHORT",
        quantity=1,
        take_profit_price=65000,
        stop_loss_price=67000,
    )
    assert out["closing_side"] == "BUY"


def test_itrader_trailing_tick_conversion_for_jnu():
    out = ia.itrader_smart_order_guidance(
        strategy="TRAILING",
        position_side="LONG",
        quantity=1,
        trail_activation_ticks=20,
        trail_retrace_ticks=40,
        pre_activation_stop_ticks=50,
    )
    assert out["jnu_reference"]["tick_size_points"] == 5.0
    assert out["jnu_reference"]["tick_value_jpy_per_contract"] == 50.0
    assert out["template"]["activation"]["points"] == 100.0
    assert out["template"]["retrace"]["points"] == 200.0
    assert out["template"]["pre_activation_stop"]["points"] == 250.0


def test_itrader_ui_mapping_is_not_claimed_fully_verified():
    out = ia.itrader_smart_order_guidance(strategy="GENERAL", trigger_price=66600)
    assert out["ui_mapping_status"].startswith("PARTIALLY_VERIFIED")
    assert "本系統不把特定App畫面名稱視為穩定API契約" in out["evidence_note"]
