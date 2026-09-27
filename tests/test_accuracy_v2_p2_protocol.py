from __future__ import annotations

from datetime import date

import pytest
import yaml

from market_ai_hub.research.accuracy_v2_p2 import (
    P2ProtocolError,
    load_p2_protocol,
)


def test_p2_protocol_is_preregistered_before_candidate_execution():
    p = load_p2_protocol()
    assert p.development_origin_end == date(2026, 7, 10)
    assert p.quarantine_start == date(2026, 7, 11)
    assert p.quarantine_end == date(2026, 9, 27)
    assert p.final_holdout_start == date(2026, 9, 28)
    assert p.minimum_meaningful_delta == pytest.approx(0.0005)
    assert p.raw["target_measure"] == "NEXT_PUBLISHED_SETTLEMENT_OBSERVATION"
    assert p.raw["final_holdout"]["minimum_origins"] == 20
    assert p.raw["selection"]["outer_results_are_development_information"] is True
    assert p.raw["promotion"]["required_same_origin_coverage"] == 1.0
    assert p.raw["promotion"]["required_delta_ci_upper_below"] == pytest.approx(-0.0005)


def test_p2_search_budget_is_finite_and_classification_is_not_return_promotion():
    p = load_p2_protocol()
    b = p.raw["search_budget"]
    families = p.raw["model_families"]
    assert b["maximum_candidate_model_families"] == 3
    assert b["maximum_settings_per_family"] == 8
    assert b["seeds"] == [42]
    assert len(families["ridge_return"]["alphas"]) == 3
    assert len(families["lightgbm_return"]["settings"]) == 4
    assert families["logistic_direction"]["implementation"] == "BaselineClassifier_lr"
    assert families["logistic_direction"]["promotion_task"] is False


def test_p2_protocol_fail_closed_if_exposed_quarantine_is_reused(tmp_path):
    p = load_p2_protocol()
    payload = {"schema_version": "AV2P2.1", "protocols": {p.protocol_id: p.raw}}
    payload["protocols"][p.protocol_id]["exposed_quarantine"]["use_for_fit"] = True
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with pytest.raises(P2ProtocolError, match="quarantine"):
        load_p2_protocol(path=path)


def test_p2_protocol_fail_closed_if_delta_or_coverage_is_weakened(tmp_path):
    p = load_p2_protocol()
    payload = {"schema_version": "AV2P2.1", "protocols": {p.protocol_id: p.raw}}
    payload["protocols"][p.protocol_id]["primary_evaluation"]["minimum_meaningful_delta"] = 0.0
    path = tmp_path / "weak-delta.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with pytest.raises(P2ProtocolError, match="delta"):
        load_p2_protocol(path=path)

    p = load_p2_protocol()
    payload = {"schema_version": "AV2P2.1", "protocols": {p.protocol_id: p.raw}}
    payload["protocols"][p.protocol_id]["promotion"]["required_same_origin_coverage"] = 0.9
    path = tmp_path / "weak-coverage.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with pytest.raises(P2ProtocolError, match="coverage"):
        load_p2_protocol(path=path)


def test_p2_protocol_hash_is_deterministic():
    assert load_p2_protocol().hash == load_p2_protocol().hash
