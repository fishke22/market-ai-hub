import pytest

from market_ai_hub.research.jnu_three_engine_ledger import (
    ALLOWED_OUTCOME_HORIZONS,
    build_forecast_snapshot,
    build_outcome_record,
    record_hash,
)
from market_ai_hub.services.jnu_three_engine import (
    EVIDENCE_DIMENSIONS,
    fuse_engine_records,
    market_ai_hub_contract_view,
)


def test_adapter_is_fail_closed_and_contract_typed():
    x = market_ai_hub_contract_view(
        data_as_of="2026-09-29T00:00:00Z",
        contract_month="202612",
        market_regime="MIXED",
        directional_bias="NEUTRAL_CONDITIONAL",
    )
    assert x["contract_version"] == "1.0"
    assert x["target"] == "OSE_NIKKEI225_MICRO_FUTURES"
    assert x["validation_claims"] == {
        "PREDICTIVE_GAIN": False,
        "CALIBRATED": False,
        "TRADING_EDGE": False,
    }
    assert x["local_validation_status"] == "LOCAL_VALIDATION_PENDING"
    assert set(x["evidence_quality"]["local_validation_components"].values()) == {"PENDING"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("directional_bias", "UP"),
        ("confidence_class", "HIGH"),
        ("market_regime", "SIDEWAYS"),
    ],
)
def test_unsupported_contract_enums_fail_closed(field, value):
    kwargs = {"data_as_of": "t", field: value}
    with pytest.raises(ValueError, match=field):
        market_ai_hub_contract_view(**kwargs)


def test_acceptance_requires_explicit_level():
    with pytest.raises(ValueError, match="explicit finite level"):
        market_ai_hub_contract_view(
            data_as_of="t",
            acceptance_checks=[{"acceptance": True, "break": True}],
        )
    x = market_ai_hub_contract_view(
        data_as_of="t",
        acceptance_checks=[{"touch": True, "break": True, "acceptance": True, "level": 66000}],
    )
    assert x["acceptance_checks"][0]["level"] == 66000


def test_fusion_preserves_disagreement_without_vote_and_dimensions():
    a = market_ai_hub_contract_view(
        data_as_of="t",
        directional_bias="BULLISH_CONDITIONAL",
        model_evidence={"quant_signal": 1},
    )
    b = dict(
        a,
        engine="CHATGPT_CONTEXT",
        directional_bias="BEARISH_CONDITIONAL",
        macro_context={"usd_jpy": "risk"},
        event_risk={"event": "BOJ"},
        analysis_id="b",
    )
    c = dict(a, engine="JNU_RESEARCH", analysis_id="c")
    f = fuse_engine_records([a, b, c], data_as_of="t")

    assert f["directional_bias"] == "ABSTAIN"
    assert f["model_evidence"]["engine_records"] == [a, b, c]
    assert f["model_evidence"]["engine_biases"] == [
        "BULLISH_CONDITIONAL",
        "BEARISH_CONDITIONAL",
        "BULLISH_CONDITIONAL",
    ]
    assert f["model_evidence"]["disagreement_preserved"] is True
    assert f["evidence_quality"]["fusion_method"] == "LOSSLESS_NO_MAJORITY_VOTE"
    dims = f["model_evidence"]["evidence_dimensions"]
    assert tuple(dims) == EVIDENCE_DIMENSIONS
    assert all(len(dims[name]) == 3 for name in EVIDENCE_DIMENSIONS)
    assert dims["MACRO"][1]["evidence"]["macro_context"] == {"usd_jpy": "risk"}
    assert dims["EVENT_RISK"][1]["evidence"]["event_risk"] == {"event": "BOJ"}


def test_model_evidence_cannot_promote_validation_claims():
    x = market_ai_hub_contract_view(
        data_as_of="t",
        model_evidence={
            "validation_claims": {
                "PREDICTIVE_GAIN": True,
                "CALIBRATED": True,
                "TRADING_EDGE": True,
            }
        },
    )
    assert x["validation_claims"] == {
        "PREDICTIVE_GAIN": False,
        "CALIBRATED": False,
        "TRADING_EDGE": False,
    }


def test_local_validation_is_componentwise_not_blanket_pass():
    x = market_ai_hub_contract_view(
        data_as_of="t",
        local_validation={
            "yuanta_runtime": "VERIFIED",
            "jnu_exact_live_contract": "VERIFIED",
            "session_semantics": "VERIFIED",
            "chronos_runtime": "VERIFIED",
            "timesfm_research_runtime": "VERIFIED",
        },
    )
    assert x["local_validation_status"] == "LOCAL_VALIDATION_PARTIAL"
    components = x["evidence_quality"]["local_validation_components"]
    assert components["mcp_runtime"] == "PENDING"
    assert components["chronos_runtime"] == "VERIFIED"


def test_ledger_snapshot_hash_and_outcome_link():
    a = market_ai_hub_contract_view(data_as_of="t")
    s = build_forecast_snapshot(a)
    assert s["record_hash"] == record_hash({k: v for k, v in s.items() if k != "record_hash"})
    for horizon in sorted(ALLOWED_OUTCOME_HORIZONS):
        o = build_outcome_record(
            forecast_hash=s["record_hash"],
            horizon=horizon,
            outcome={"return": 0.1},
        )
        assert o["forecast_hash"] == s["record_hash"]
        assert o["horizon"] == horizon


def test_invalid_outcome_horizon_is_rejected():
    with pytest.raises(ValueError, match="unsupported value"):
        build_outcome_record(forecast_hash="abc", horizon="2h", outcome={})
