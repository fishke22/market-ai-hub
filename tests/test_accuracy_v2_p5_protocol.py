from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from market_ai_hub.research.accuracy_v2_p5 import P5ProtocolError, load_p5_protocol


def _mutated(tmp_path, mutate):
    payload = yaml.safe_load(Path("config/accuracy_v2_p5_protocol.yaml").read_text(encoding="utf-8"))
    raw = payload["protocols"]["jnu_forward_publication_monitor_v1"]
    mutate(raw)
    path = tmp_path / "p5.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def test_p5_protocol_freezes_forward_publication_monitor():
    p = load_p5_protocol()
    assert p.raw["target"]["measure"] == "NEXT_PUBLISHED_SETTLEMENT_OBSERVATION"
    assert p.raw["origin"]["first_eligible_publication_date"] == "2026-09-28"
    assert p.raw["artifacts"]["point"]["method"] == "ZERO_RETURN_NAIVE_LAST_AVAILABLE_SETTLEMENT"
    assert p.raw["forward_evaluation"]["minimum_settled_canonical_origins"] == 20
    assert p.raw["forward_evaluation"]["automatic_model_promotion"] is False
    assert p.raw["collector"]["planned_weekday_times"] == ["08:05", "08:15"]
    assert len(p.hash) == 64


def test_p5_rejects_backdated_origin(tmp_path):
    p = _mutated(tmp_path, lambda raw: raw["origin"].__setitem__("backdated_forecast_origin_allowed", True))
    with pytest.raises(P5ProtocolError, match="backdated"):
        load_p5_protocol(path=p)


def test_p5_rejects_weak_interval_coverage_gate(tmp_path):
    p = _mutated(
        tmp_path,
        lambda raw: raw["downgrade"]["interval"].__setitem__("minimum_acceptable_coverage", 0.50),
    )
    with pytest.raises(P5ProtocolError, match="interval downgrade"):
        load_p5_protocol(path=p)


def test_p5_rejects_auto_promotion(tmp_path):
    p = _mutated(
        tmp_path,
        lambda raw: raw["forward_evaluation"].__setitem__("automatic_model_promotion", True),
    )
    with pytest.raises(P5ProtocolError, match="automatically promote"):
        load_p5_protocol(path=p)


def test_p5_rejects_broker_or_recorder_use(tmp_path):
    p = _mutated(tmp_path, lambda raw: raw["collector"].__setitem__("broker_used", True))
    with pytest.raises(P5ProtocolError, match="broker_used"):
        load_p5_protocol(path=p)


def test_p5_rejects_full_session_claim(tmp_path):
    p = _mutated(
        tmp_path,
        lambda raw: raw["target"].__setitem__("full_session_forecast_claim_allowed", True),
    )
    with pytest.raises(P5ProtocolError, match="full-session"):
        load_p5_protocol(path=p)
