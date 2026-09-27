from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from market_ai_hub.research.accuracy_v2_p2 import load_p2_protocol
from market_ai_hub.research.accuracy_v2_p2_engine import (
    build_p2_samples,
    chronological_folds,
    evaluate_final_holdout,
    run_p2_development,
    save_development_selection,
)


JST = ZoneInfo("Asia/Tokyo")


def _frame(periods: int = 105) -> pd.DataFrame:
    dates = pd.date_range("2026-01-05", periods=periods, freq="B")
    rows = []
    values = 1000.0 + np.arange(periods) * 0.6 + np.sin(np.arange(periods) / 3.0) * 9.0
    for i, (d, value) in enumerate(zip(dates, values)):
        rows.append(
            {
                "contract_month": "202612",
                "date": d.date().isoformat(),
                "settlement": float(value),
                "source_hash": f"s{i}",
            }
        )
    return pd.DataFrame(rows)


def _publication(day):
    d = pd.Timestamp(day).date()
    return datetime.combine(d, time(9, 0), tzinfo=JST) + timedelta(hours=24)


def test_p2_sample_builder_is_exact_contract_causal_and_excludes_simultaneous_target():
    p = load_p2_protocol()
    samples = build_p2_samples(_frame(), protocol=p, publication_fn=_publication)
    assert samples
    assert all(s.contract_month == "202612" for s in samples)
    assert all(s.label_available_at > s.decision_time for s in samples)
    assert all(len(s.features) == 10 for s in samples)
    assert all(np.isfinite(list(s.features.values())).all() for s in samples)
    assert all(s.partition == "DEVELOPMENT" for s in samples)


def test_p2_chronological_folds_enforce_embargo_and_label_availability():
    p = load_p2_protocol()
    samples = build_p2_samples(_frame(), protocol=p, publication_fn=_publication)
    folds = chronological_folds(
        samples,
        minimum_train_origins=32,
        test_origins_per_fold=10,
        maximum_folds=5,
        embargo_origins=1,
    )
    assert folds
    for fold in folds:
        assert len(fold.train) >= 32
        assert max(x.decision_time for x in fold.train) < min(x.decision_time for x in fold.test)
        assert all(x.label_available_at <= fold.test[0].decision_time for x in fold.train)
        train_origins = {x.origin_date for x in fold.train}
        test_origins = {x.origin_date for x in fold.test}
        assert train_origins.isdisjoint(test_origins)


def test_p2_nested_engine_records_trials_and_never_uses_quarantine_for_fit():
    out = run_p2_development(_frame(), publication_fn=_publication)
    assert out["status"] == "OK"
    assert out["prereg_commit"].startswith("53386f5")
    assert out["outer_fold_count"] > 0
    assert out["outer_oof_origin_count"] > 0
    assert out["trial_ledger"]
    assert set(out["metrics"]) == {"zero_return_naive", "ridge_return", "lightgbm_return"}
    assert out["selection"]["development_information_only"] is True
    assert out["not_final_holdout_evidence"] is True
    assert all(row["quarantine_used_for_fit"] is False for row in out["outer_oof_ledger"])
    assert all(row["origin_date"] <= "2026-07-10" for row in out["outer_oof_ledger"])
    assert all(t["setting_index"] < 8 for t in out["trial_ledger"])
    assert all(t["seed"] == 42 for t in out["trial_ledger"])


def test_p2_development_selection_is_exclusive(tmp_path):
    out = run_p2_development(_frame(), publication_fn=_publication)
    path = save_development_selection(out, data_root=tmp_path)
    assert path.exists()
    assert save_development_selection(out, data_root=tmp_path) == path
    changed = dict(out)
    changed["development_result_id"] = "different"
    with pytest.raises(RuntimeError, match="DEVELOPMENT_SELECTION_ALREADY_FROZEN"):
        save_development_selection(changed, data_root=tmp_path)


def test_p2_final_is_data_not_ready_before_new_forward_minimum():
    out = run_p2_development(_frame(), publication_fn=_publication)
    final = evaluate_final_holdout(out, _frame(), publication_fn=_publication)
    assert final["status"] in {"INSUFFICIENT_EVIDENCE", "NO_IMPROVEMENT"}
    if final["status"] == "NO_IMPROVEMENT":
        assert final["reason"] == "DEVELOPMENT_SELECTION_KEPT_BASELINE"
        assert final["evidence_grade"] == "DEVELOPMENT_INFORMATION_ONLY"
        assert final["final_not_opened"] is True
        assert final["not_final_holdout_evidence"] is True
    assert final["not_calibration_evidence"] is True
    assert final["not_trading_edge"] is True
