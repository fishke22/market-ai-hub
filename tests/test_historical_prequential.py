from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from market_ai_hub.research.historical_prequential import (
    HistoricalPrequentialProtocol,
    build_front_contract_origins,
    compact_evidence_summary,
    equal_weight_ensemble_summary,
    load_protocol,
    run_replay,
    save_one_use_evidence,
)


def _protocol() -> HistoricalPrequentialProtocol:
    return HistoricalPrequentialProtocol(
        protocol_id="test",
        market_family="OSAKA_MICRO",
        product="Nikkei 225 Micro",
        target_field="settlement",
        horizon_steps=1,
        history_len=3,
        contract_rule="nearest",
        source_scope="TEST",
        source_availability_semantics="SESSION_ORDER_CAUSAL_NOT_PUBLICATION_TIMESTAMP",
        development_origin_end=date(2026, 1, 5),
        validation_origin_end=date(2026, 1, 8),
        final_holdout_origin_end=date(2026, 1, 12),
        boundary_selection_basis="SAMPLE_COUNT_ONLY_BEFORE_MODEL_REPLAY",
        final_holdout_one_use=True,
        model_training_cutoff_policy="FAIL_CLOSED_UNKNOWN_IS_NOT_CLEAN_OOS",
    )


def _frame() -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=9, freq="B")
    rows = []
    for contract, shift in (("202601", 0.0), ("202602", 100.0)):
        for i, d in enumerate(dates):
            rows.append(
                {
                    "contract_month": contract,
                    "date": d.date().isoformat(),
                    "settlement": 1000.0 + shift + i * 10.0,
                    "source_hash": f"{contract}-{i}",
                }
            )
    return pd.DataFrame(rows)


class _LastPriceAdapter:
    def predict(self, series, horizon=1):
        last = float(series.iloc[-1])
        return {"path": {"p10": [last], "p50": [last], "p90": [last]}}


def test_tracked_protocol_is_frozen_before_replay():
    p = load_protocol()
    assert p.history_len == 32
    assert p.development_origin_end == date(2026, 5, 15)
    assert p.validation_origin_end == date(2026, 7, 10)
    assert p.final_holdout_origin_end == date(2026, 9, 18)
    assert p.final_holdout_one_use is True


def test_front_contract_builder_uses_one_contract_per_origin_and_no_future_context(monkeypatch):
    import market_ai_hub.research.historical_prequential as hp

    monkeypatch.setattr(hp, "ose_last_trading_date", lambda y, m: date(2026, 12, 31))
    origins = build_front_contract_origins(_frame(), _protocol())
    assert origins
    assert len({x.origin_date for x in origins}) == len(origins)
    assert all(x.contract_month == "202601" for x in origins)
    for x in origins:
        assert x.context.index[-1].date() == x.origin_date
        assert x.target_date > x.origin_date
        assert float(x.context.iloc[-1]) == x.origin_price
        assert x.actual not in set(x.context.iloc[:-1].astype(float))


def test_replay_last_price_model_matches_naive_and_partitions(monkeypatch):
    import market_ai_hub.research.historical_prequential as hp

    monkeypatch.setattr(hp, "ose_last_trading_date", lambda y, m: date(2026, 12, 31))
    monkeypatch.setattr(
        hp,
        "_model_identity",
        lambda name: {
            "name": name,
            "model_id": name,
            "revision": "test",
            "training_cutoff": "unknown",
            "training_cutoff_known": False,
        },
    )
    out = run_replay({"chronos-2": _LastPriceAdapter()}, frame=_frame(), protocol=_protocol())
    assert out["status"] == "OK"
    assert sum(out["partition_counts"].values()) == out["origin_count"]
    assert out["evidence_grade"] == "HISTORICAL_PREQUENTIAL_TRAINING_CUTOFF_UNKNOWN"
    m = out["models"]["chronos-2"]["all"]
    assert m["evaluation"]["model"]["mase"] == pytest.approx(1.0)
    assert m["paired_vs_last_price_naive"]["delta_model_minus_naive"] == pytest.approx(0.0)
    assert out["not_forward_evidence"] is True
    assert out["not_calibration_evidence"] is True


def test_one_use_final_holdout_refuses_different_identity(tmp_path):
    first = {"status": "OK", "evidence_id": "A", "x": 1}
    path = save_one_use_evidence(first, data_root=tmp_path)
    assert path.exists()
    assert save_one_use_evidence(first, data_root=tmp_path) == path
    with pytest.raises(RuntimeError, match="FINAL_HOLDOUT_ALREADY_OPENED"):
        save_one_use_evidence({"status": "OK", "evidence_id": "B"}, data_root=tmp_path)


def test_equal_weight_ensemble_is_derived_from_sealed_records_without_model_calls(monkeypatch):
    import market_ai_hub.research.historical_prequential as hp

    monkeypatch.setattr(hp, "ose_last_trading_date", lambda y, m: date(2026, 12, 31))
    monkeypatch.setattr(
        hp,
        "_model_identity",
        lambda name: {
            "name": name, "model_id": name, "revision": "test",
            "training_cutoff": "unknown", "training_cutoff_known": False,
        },
    )
    sealed = run_replay(
        {"chronos-2": _LastPriceAdapter(), "timesfm-3.0": _LastPriceAdapter()},
        frame=_frame(),
        protocol=_protocol(),
    )
    ensemble = equal_weight_ensemble_summary(sealed)
    assert ensemble["status"] == "OK"
    assert ensemble["all"]["evaluation"]["model"]["mase"] == pytest.approx(1.0)
    compact = compact_evidence_summary(sealed)
    assert compact["origin_count"] == sealed["origin_count"]
    assert "records" not in compact["models"]["chronos-2"]
