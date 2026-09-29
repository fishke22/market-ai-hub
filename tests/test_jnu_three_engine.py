from market_ai_hub.services.jnu_three_engine import market_ai_hub_contract_view, fuse_engine_records
from market_ai_hub.research.jnu_three_engine_ledger import build_forecast_snapshot, build_outcome_record, record_hash

def test_adapter_is_fail_closed_and_contract_typed():
    x=market_ai_hub_contract_view(data_as_of="2026-09-29T00:00:00Z",contract_month="202612",market_regime="MIXED",directional_bias="NEUTRAL_CONDITIONAL")
    assert x["contract_version"]=="1.0"
    assert x["target"]=="OSE_NIKKEI225_MICRO_FUTURES"
    assert x["validation_claims"]=={"PREDICTIVE_GAIN":False,"CALIBRATED":False,"TRADING_EDGE":False}
    assert x["local_validation_status"]=="LOCAL_VALIDATION_PENDING"

def test_fusion_preserves_disagreement_without_vote():
    a=market_ai_hub_contract_view(data_as_of="t",directional_bias="BULLISH_CONDITIONAL")
    b=dict(a,engine="CHATGPT_CONTEXT",directional_bias="BEARISH_CONDITIONAL",analysis_id="b")
    f=fuse_engine_records([a,b],data_as_of="t")
    assert f["directional_bias"]=="ABSTAIN"
    assert f["model_evidence"]["disagreement_preserved"] is True
    assert f["evidence_quality"]["fusion_method"]=="LOSSLESS_NO_MAJORITY_VOTE"

def test_ledger_snapshot_hash_and_outcome_link():
    a=market_ai_hub_contract_view(data_as_of="t")
    s=build_forecast_snapshot(a)
    assert s["record_hash"]==record_hash({k:v for k,v in s.items() if k!="record_hash"})
    o=build_outcome_record(forecast_hash=s["record_hash"],horizon="1h",outcome={"return":0.1})
    assert o["forecast_hash"]==s["record_hash"]
