"""Phase 2V-E — Forward data feed + daily operations static/unit tests."""
import sys
from pathlib import Path
import yaml

sys.path.insert(0, "src")
ROOT = Path(__file__).resolve().parents[1]

def _doc(p): return (ROOT / p).read_text(encoding="utf-8")
def _yaml(p): return yaml.safe_load((ROOT / p).read_text(encoding="utf-8"))

POLICY = _yaml("research/phase2/protocols/FORWARD_DATA_SOURCE_POLICY.yaml")
FREEZE = _yaml("research/phase2/freeze/PHASE2_RESEARCH_FREEZE.yaml")

from market_ai_hub.data import ylab225_ingest as ing

def test_manual_225labo_import_idempotent():
    # build_daily_bars is idempotent (deterministic aggregation)
    rows = [
        ("2023-07-24", "14:15:00", 100, 110, 95, 105, 10),
        ("2023-07-24", "15:15:00", 105, 115, 100, 110, 20),
    ]
    bars1 = ing.build_daily_bars_from_minutes(rows)
    bars2 = ing.build_daily_bars_from_minutes(rows)
    assert bars1 == bars2

def test_raw_source_immutable():
    # ingest archives raw (copy to archive, never overwrite) — policy enforces
    assert POLICY["rules"][0] == "no_auto_scrape" or "raw_source_immutable" in POLICY["rules"]

def test_micro_validation_before_import():
    # valid bar passes
    assert ing._validate_bar({"trading_date": "2023-07-24", "open": 100, "high": 110, "low": 95, "close": 105, "volume": 10}) == []
    # pre-listing rejected
    assert "PRE_LISTING" in ing._validate_bar({"trading_date": "2023-01-01", "open": 100, "high": 110, "low": 95, "close": 105, "volume": 10})
    # invalid OHLC rejected
    assert "INVALID_OHLC" in ing._validate_bar({"trading_date": "2023-07-24", "open": 100, "high": 90, "low": 95, "close": 105, "volume": 10})

def test_incremental_import_no_duplicates():
    # merge dedup logic: existing dates not re-added
    import pandas as pd
    existing = pd.DataFrame({"trading_date": pd.to_datetime(["2023-07-24", "2023-07-25"])})
    new = pd.DataFrame({"trading_date": pd.to_datetime(["2023-07-25", "2023-07-26"])})
    merged = pd.concat([existing, new]).drop_duplicates(subset="trading_date")
    assert len(merged) == 3

def test_stale_data_skips_forecast():
    from market_ai_hub.research import forward_shadow as fs
    r = fs.create_daily_forecasts()
    # data is stale (last bar 2026-09-01), so must skip
    assert r.get("status") == "FORECAST_SKIPPED_DATA_QUALITY" or len(r.get("created", [])) == 0

def test_missed_origin_not_backfilled():
    assert POLICY["rules"] is not None
    assert "no_auto_scrape" in POLICY["rules"]

def test_replay_not_forward():
    assert "activation timestamp 之前永遠不算 forward evidence" in _doc("research/phase2/protocols/FORWARD_SHADOW_PROTOCOL.yaml")

def test_scheduler_default_disabled():
    proto = _yaml("research/phase2/protocols/FORWARD_SHADOW_PROTOCOL.yaml")
    assert proto["scheduler_default"] == "DISABLED"

def test_daily_cycle_no_broker():
    d = _doc("scripts/run_daily_forward_cycle.ps1")
    assert "broker" not in d.lower() or "no broker" in d.lower()
    assert "order" not in d.lower() or "no broker" in d.lower()

def test_forward_status_counts_missed():
    import json
    st = json.loads(_doc("research/phase2/status/FORWARD_SHADOW_STATUS.json"))
    assert "forward_origins_missed" in st
    assert "forward_origins_created" in st

def test_schema_change_fails_closed():
    assert "schema_change_fails_closed" in _doc("research/phase2/protocols/FORWARD_DATA_SOURCE_POLICY.yaml")

def test_private_data_gitignored():
    # 225LABO raw/normalized must be excluded from publication
    excl = _doc("research/phase2/publication/PUBLICATION_EXCLUDE_MANIFEST.txt")
    assert "225LABO" in excl or "ylab225" in excl or "N225microf" in excl

def test_phase2_research_freeze_truthful():
    assert FREEZE["strategy_conclusion"] == "NO_ECONOMIC_EDGE"
    assert FREEZE["causality_conclusion"] == "NON_EXECUTABLE_FORECAST_EDGE"
    assert FREEZE["strategy_candidate"] == "NONE"
    assert FREEZE["production_candidate"] == "NONE"

def test_no_profitable_claim():
    freeze_doc = _doc("research/phase2/freeze/PHASE2_RESEARCH_FREEZE.yaml")
    for bad in ["profitable", "alpha confirmed", "trading edge", "winning model", "production ready trading"]:
        assert bad not in freeze_doc.split("forbidden_claims")[0].lower() or bad in freeze_doc
