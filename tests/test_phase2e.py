"""Phase 2E — automation 核心測試。"""
import numpy as np
import pandas as pd
import pytest

from market_ai_hub.automation.archive import AnalysisArchive, AnalysisOutcome, AnalysisRecord
from market_ai_hub.automation.data_lake import DataLakeManager, DataManifest
from market_ai_hub.automation.incremental import atomic_write, dedupe, dedupe_and_write, missing_ranges
from market_ai_hub.automation.loop import LoopContext, run_catchup, run_tick
from market_ai_hub.automation.scheduler import JOBS, SchedulerState
from market_ai_hub.automation.training_policy import AUTO_PROMOTE_TO_CHAMPION, DriftMonitor, TrainingEligibilityPolicy


@pytest.fixture
def tmp_root(tmp_path):
    return tmp_path


def test_missing_ranges_none_covered():
    assert missing_ranges(None, ("2024-01-01", "2024-01-31")) == [("2024-01-01", "2024-01-31")]


def test_missing_ranges_both_sides():
    gaps = missing_ranges(("2024-01-10", "2024-01-20"), ("2024-01-01", "2024-01-31"))
    assert gaps == [("2024-01-01", "2024-01-09"), ("2024-01-21", "2024-01-31")]


def test_missing_ranges_fully_covered():
    assert missing_ranges(("2024-01-01", "2024-01-31"), ("2024-01-05", "2024-01-10")) == []


def test_dedupe():
    df = pd.DataFrame({"a": [1, 1, 2], "b": [10, 11, 20]})
    out = dedupe(df, ["a"])
    assert len(out) == 2 and list(out["b"]) == [11, 20]  # keep last


def test_atomic_write_and_hash_no_rewrite(tmp_root):
    p = tmp_root / "f.parquet"
    df = pd.DataFrame({"a": [1, 2, 3]})
    n1, h1 = dedupe_and_write(p, df, ["a"])
    n2, h2 = dedupe_and_write(p, df, ["a"])
    assert h1 == h2 and n1 == n2 == 3


def test_data_lake_manifest_roundtrip(tmp_root):
    lake = DataLakeManager(tmp_root)
    m = DataManifest(provider="twse", dataset="daily", instrument="2330", frequency="D",
                     start="2024-01-01", end="2024-12-31", row_count=244, source="STOCK_DAY", source_hash="x")
    lake.save_manifest(m)
    got = lake.load_manifest("twse", "daily", "2330")
    assert got is not None and got.row_count == 244
    assert lake.coverage("twse", "daily", "2330") == ("2024-01-01", "2024-12-31")


def test_analysis_archive_immutable_and_settle(tmp_root):
    a = AnalysisArchive(tmp_root)
    rec = AnalysisRecord(analysis_id="A1", information_cutoff="2024-06-01T00:00:00+00:00",
                         target="2330", horizon="5d")
    rec.analysis_packet_hash = rec.packet_hash()
    a.save(rec)
    with pytest.raises(ValueError):
        a.save(rec)  # immutable
    assert a.unsettled_ids() == ["A1"]
    a.settle(AnalysisOutcome(analysis_id="A1", actual_close=100, actual_high=101, actual_low=99,
                             center_absolute_error=2.0, direction_hit=True, core_range_hit=True))
    assert a.unsettled_ids() == []
    with pytest.raises(ValueError):
        a.settle(AnalysisOutcome(analysis_id="A1", actual_close=100, actual_high=101, actual_low=99,
                                 center_absolute_error=2.0, direction_hit=True, core_range_hit=True))


def test_scheduler_state(tmp_root):
    s = SchedulerState(tmp_root)
    s.record_attempt("sync_market_data")
    s.record_success("sync_market_data")
    st = s.status()["sync_market_data"]
    assert st["status"] == "ok"


def test_run_tick_offline_no_fabrication(tmp_root):
    r = run_tick(tmp_root, LoopContext(offline=True))
    assert r["results"]["sync_market_data"] == "OFFLINE_DEFERRED"
    assert r["results"]["settle_predictions"] == "OFFLINE_DEFERRED"


def test_run_tick_gpu_busy(tmp_root):
    r = run_tick(tmp_root, LoopContext(gpu_busy=True))
    assert r["results"]["training_due_check"] == "TRAINING_DEFERRED_GPU_BUSY"


def test_run_catchup(tmp_root):
    out = run_catchup(tmp_root, LoopContext(offline=True))
    assert set(out["last_success"]) == set(JOBS)


def test_training_policy():
    p = TrainingEligibilityPolicy()
    assert p.eligible_model("xgboost") and not p.eligible_model("moirai")
    due, reason = p.training_due("xgboost", new_labeled_observations=2, last_train=None)
    assert not due  # insufficient samples
    due, reason = p.training_due("xgboost", new_labeled_observations=6, last_train=None)
    assert due and "weekly" in reason
    due, _ = p.training_due("xgboost", new_labeled_observations=6, last_train=None, drift_warning=True)
    assert due


def test_auto_promote_always_false():
    assert AUTO_PROMOTE_TO_CHAMPION is False


def test_drift_monitor_psi():
    dm = DriftMonitor(threshold=0.2)
    ref = np.random.default_rng(0).normal(0, 1, 1000)
    same = np.random.default_rng(1).normal(0, 1, 1000)
    shifted = np.random.default_rng(2).normal(3, 1, 1000)
    assert dm.check(ref, same)["status"] == "NORMAL"
    assert dm.check(ref, shifted)["status"] == "DRIFT_WARNING"
    assert dm.check(ref, shifted)["shadow_only"] is True
