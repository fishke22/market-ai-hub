from datetime import datetime, timezone

import pandas as pd

import market_ai_hub.services.data_continuity as dc


UTC = timezone.utc


def _meta():
    return {
        "status": "OK",
        "contract_month": "202610",
        "quote_code": "JNU2610",
        "latest_date": "2026-09-25",
        "latest_settlement": 66140.0,
        "latest_received_at": "2026-09-25T07:50:00+00:00",
        "latest_source_hash": "receipt-hash",
    }


def _series():
    return pd.Series(
        [65000.0, 65500.0, 66140.0],
        index=pd.to_datetime(["2026-09-23", "2026-09-24", "2026-09-25"], utc=True),
    )


def _daily(value=66140.0):
    return pd.DataFrame([{
        "contract_month": "202610",
        "date": "2026-09-25",
        "settlement": value,
        "source_hash": "daily-hash",
    }])


def _receipts(value=66140.0):
    return pd.DataFrame([{
        "contract_month": "202610",
        "date": "2026-09-25",
        "settlement": value,
        "source_hash": "receipt-hash",
        "_received_at": pd.Timestamp("2026-09-25T07:50:00Z"),
    }])


def _patch_normal(monkeypatch):
    monkeypatch.setattr(dc, "load_direct_micro_settlements", lambda contract_month="": (_series(), _meta()))
    monkeypatch.setattr(dc, "_daily_channel", lambda: _daily())
    monkeypatch.setattr(dc, "load_current_micro_settlement_receipts", lambda contract_month="": _receipts())
    monkeypatch.setattr(dc, "next_published_settlement_observation_dates", lambda d, n: ["2026-09-28"])
    monkeypatch.setattr(
        dc,
        "jpx_report_publication_for_session",
        lambda d: datetime(2026, 9, 29, 0, 0, tzinfo=UTC),
    )


def test_continuity_normal_before_next_expected_publication(monkeypatch):
    _patch_normal(monkeypatch)
    out = dc.jnu_data_continuity_status(
        now=datetime(2026, 9, 28, 23, 0, tzinfo=UTC),
    )
    assert out["mode"] == dc.NORMAL_MODE
    assert out["context_only"] is False
    assert out["target_prediction_allowed"] is True
    assert out["proxy_can_replace_target"] is False
    assert out["source_redundancy"]["status"] == "DUAL_CHANNEL_MATCH"
    assert out["source_redundancy"]["independent_publisher_count"] == 1
    assert out["context_confidence_not_probability"] is True


def test_continuity_goes_context_only_when_expected_observation_overdue(monkeypatch):
    _patch_normal(monkeypatch)
    out = dc.jnu_data_continuity_status(
        now=datetime(2026, 9, 29, 1, 0, tzinfo=UTC),
    )
    assert out["mode"] == dc.CONTINUITY_MODE
    assert out["reason"] == "EXPECTED_PUBLISHED_OBSERVATION_OVERDUE"
    assert out["target_prediction_allowed"] is False
    assert out["new_forward_precommit_allowed"] is False
    assert out["forward_evidence_update_allowed"] is False
    assert out["p5_precommit_gate"] == "BLOCKED_DATA_CONTINUITY_MODE"


def test_continuity_fails_closed_on_source_conflict(monkeypatch):
    _patch_normal(monkeypatch)
    monkeypatch.setattr(dc, "_daily_channel", lambda: _daily(66000.0))
    out = dc.jnu_data_continuity_status(
        now=datetime(2026, 9, 28, 23, 0, tzinfo=UTC),
    )
    assert out["mode"] == dc.CONTINUITY_MODE
    assert out["reason"] == "EXACT_TARGET_SOURCE_CONFLICT"
    assert out["source_redundancy"]["revision_conflict"] is True
    assert out["target_prediction_allowed"] is False


def test_continuity_without_exact_target_never_promotes_proxy(monkeypatch):
    monkeypatch.setattr(
        dc,
        "load_direct_micro_settlements",
        lambda contract_month="": (
            pd.Series(dtype=float),
            {"status": "NO_DIRECT_HISTORY"},
        ),
    )
    out = dc.jnu_data_continuity_status(now=datetime(2026, 9, 29, 1, 0, tzinfo=UTC))
    assert out["mode"] == dc.CONTINUITY_MODE
    assert out["target_reference_available"] is False
    assert out["proxy_can_replace_target"] is False
    assert out["context_confidence_grade"] == "VERY_LOW"


def test_continuity_public_summary_explicitly_blocks_prediction(monkeypatch):
    snapshot = {
        "mode": dc.CONTINUITY_MODE,
        "reason": "EXPECTED_PUBLISHED_OBSERVATION_OVERDUE",
        "target_reference_available": True,
        "freshness_status": "STALE_EXPECTED_OBSERVATION_MISSING",
        "latest_reference": {
            "date": "2026-09-25",
            "exact_contract": "JNU2610",
            "settlement": 66140.0,
        },
        "next_expected_published_observation_date": "2026-09-28",
        "next_expected_publication_at": "2026-09-29T00:00:00+00:00",
        "source_redundancy": {"status": "SINGLE_CHANNEL_ONLY"},
    }
    import market_ai_hub.research.accuracy_v2_p4_engine as p4
    monkeypatch.setattr(
        p4,
        "analyze_no_new_forward_outcome",
        lambda: {
            "status": "OK",
            "point_reference": {"price": 66140.0},
            "volatility": {"ewma_return_volatility": 0.01},
            "empirical_interval": {"lower_price": 64000.0, "upper_price": 68000.0},
        },
    )
    out = dc.jnu_continuity_user_summary(snapshot)
    assert out["模式"].startswith("資料連續性模式")
    assert "新的 exact JNU target prediction" in out["目前暫停"]
    assert out["情境參考"]["區間不是機率"] is True
    assert out["PREDICTIVE_GAIN"] is False
    assert out["CALIBRATED"] is False
    assert out["TRADING_EDGE"] is False
