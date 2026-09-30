import json
from pathlib import Path

from scripts.update_jnu_market_session_readiness import build_readiness


def _write_view(root: Path, sessions):
    p = root / "research" / "jnu_market_session_view.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "schema_version": "AV2.JNU.MARKET_SESSION_VIEW.1",
        "generated_at": "2026-10-01T00:00:00+00:00",
        "source_rows_sha256": "abc",
        "market_sessions": sessions,
    }), encoding="utf-8")


def _session(key, context=True):
    return {
        "market_session_key": key,
        "research_use": {"context_allowed": context},
    }


def test_one_distinct_session_keeps_cross_session_pairing_blocked(tmp_path):
    _write_view(tmp_path, [_session("NIGHT|2026-09-30")])
    out = build_readiness(tmp_path)
    assert out["status"] == "ACCUMULATING_MARKET_SESSIONS"
    assert out["eligible_market_session_count"] == 1
    assert out["sessions_needed_for_descriptive_pairing"] == 1
    assert out["cross_session_descriptive_pairing_ready"] is False
    assert out["chronological_model_selection_ready"] is False
    assert out["predictive_performance_evaluation_ready"] is False


def test_two_distinct_sessions_only_unlock_descriptive_pairing(tmp_path):
    _write_view(tmp_path, [
        _session("NIGHT|2026-09-30"),
        _session("NIGHT|2026-10-01"),
    ])
    out = build_readiness(tmp_path)
    assert out["status"] == "DESCRIPTIVE_PAIRING_READY_ONLY"
    assert out["eligible_market_session_count"] == 2
    assert out["sessions_needed_for_descriptive_pairing"] == 0
    assert out["cross_session_descriptive_pairing_ready"] is True
    assert out["chronological_model_selection_ready"] is False
    assert out["predictive_performance_evaluation_ready"] is False
    assert out["policy"]["predictive_gain_claim_allowed"] is False
    assert out["policy"]["calibrated_probability_claim_allowed"] is False
    assert out["policy"]["trading_edge_claim_allowed"] is False


def test_non_context_session_is_not_eligible(tmp_path):
    _write_view(tmp_path, [
        _session("NIGHT|2026-09-30"),
        _session("NIGHT|2026-10-01", context=False),
    ])
    out = build_readiness(tmp_path)
    assert out["market_session_count"] == 2
    assert out["eligible_market_session_count"] == 1
    assert out["cross_session_descriptive_pairing_ready"] is False


def test_missing_view_does_not_invent_sessions(tmp_path):
    out = build_readiness(tmp_path)
    assert out["status"] == "NO_MARKET_SESSIONS"
    assert out["market_session_count"] == 0
    assert out["eligible_market_session_count"] == 0
    assert out["sessions_needed_for_descriptive_pairing"] == 2
