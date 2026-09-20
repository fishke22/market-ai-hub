"""Phase 2V-B.3 — Direct Micro Bar OOS static tests."""
import sys
from pathlib import Path
import yaml

sys.path.insert(0, "src")
ROOT = Path(__file__).resolve().parents[1]

def _doc(p): return (ROOT / p).read_text(encoding="utf-8")
def _yaml(p): return yaml.safe_load((ROOT / p).read_text(encoding="utf-8"))
def _csv(p):
    import pandas as pd
    return pd.read_csv(ROOT / p)

PROTO = _yaml("DIRECT_MICRO_BAR_OOS_PROTOCOL.yaml")
MANIFEST = _yaml("DIRECT_MICRO_BAR_DATASET_MANIFEST.yaml")
REPORT = _doc("PHASE2VB3_DIRECT_MICRO_BAR_OOS_REPORT.md")

def test_micro_bar_protocol_frozen():
    assert PROTO["protocol_version"] == 1
    assert PROTO["frozen_at"]
    assert PROTO["targets"]["DIRECT_MICRO_BAR"]["semantic"] == "NEXT_TRADING_DAY_BAR_CLOSE"

def test_micro_source_is_225labo():
    assert MANIFEST["provider"] == "225LABO"
    assert MANIFEST["redistribution_allowed"] is False

def test_micro_raw_not_publishable():
    assert MANIFEST["redistribution_allowed"] is False
    d = _doc("PUBLICATION_EXCLUDE_MANIFEST.txt")
    assert "225LABO_MARKET_DATA_PRIVATE_LOCAL_ONLY" in d or "225LABO" in d

def test_micro_continuous_not_contract_level():
    assert MANIFEST["continuous_series"] is True
    assert MANIFEST["contract_specific"] is False
    assert PROTO["targets"]["DIRECT_MICRO_BAR"]["contract_specific"] is False

def test_micro_bar_close_not_settlement():
    assert MANIFEST["settlement"] is False
    assert MANIFEST["close_semantics"] == "BAR_CLOSE"

def test_night_session_trading_date():
    assert MANIFEST["night_session_rule"] is not None
    assert "16:30" in MANIFEST["night_session_rule"]

def test_no_intraday_future_leak():
    assert PROTO["max_feature_timestamp_rule"] is not None

def test_micro_only_crossasset_separate():
    assert PROTO["exams"]["A_MICRO_ONLY"]["name"] == "Micro-only features"
    assert PROTO["exams"]["B_MICRO_PLUS_CROSS_ASSET"]["name"] is not None

def test_zero_return_baseline_present():
    assert "ZERO_RETURN" in PROTO["baselines"]["return"]

def test_same_origins_crossasset_compare():
    assert PROTO["horizons"] is not None
    assert PROTO["warmup_history"] == 128

def test_roll_days_not_deleted():
    import pandas as pd
    df = pd.read_parquet("data/normalized/ose_micro/ose_micro_daily_bar_v1.parquet")
    assert len(df) > 900  # roll days retained

def test_block_bootstrap():
    assert "moving_block_bootstrap" in str(PROTO["statistical_tests"])

def test_dm_hac_overlap():
    assert "HAC" in str(PROTO["statistical_tests"]["forecast_comparison"])

def test_no_auto_champion():
    assert PROTO["no_auto_champion"] is True
    assert "CHAMPION_CANDIDATE" in REPORT
    assert "AUTO_PROMOTE=false" in REPORT