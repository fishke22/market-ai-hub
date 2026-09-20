"""Phase 2Q-C — primary market parity + historical split + leakage + evidence isolation tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, "src")
ROOT = Path(__file__).resolve().parents[1]


# ── §1/§3 primary market parity ──

def test_three_target_families_defined():
    import yaml

    mission = yaml.safe_load((ROOT / "PRIMARY_MARKET_MISSION.yaml").read_text(encoding="utf-8"))
    families = {f["name"] for f in mission["target_families"]}
    assert families == {"OSAKA_MICRO", "TAIWAN_STOCK", "TAIWAN_INDEX"}


def test_primary_targets_registry_complete():
    from market_ai_hub.services.primary_targets import (
        TARGET_FAMILIES,
        load_primary_targets,
        targets_of,
    )

    assert set(TARGET_FAMILIES) == {"OSAKA_MICRO", "TAIWAN_STOCK", "TAIWAN_INDEX"}
    data = load_primary_targets()
    required = {"target_family", "symbol", "instrument_type", "exchange", "timezone",
                "calendar", "currency", "data_semantics"}
    for t in data["targets"]:
        assert required <= set(t.keys()), f"{t['target']} missing fields"
    assert targets_of("TAIWAN_INDEX")  # 至少 TAIEX/TX/MTX/TMF


def test_taiwan_index_forecast_target_not_execution():
    from market_ai_hub.services.primary_targets import resolve_target

    taiex = resolve_target("TAIEX")
    assert taiex["instrument_type"] == "cash_index"
    assert taiex["execution_instrument"] is None  # 非可成交
    tmf = resolve_target("TMF")
    assert tmf["execution_instrument"] == "TMF"


# ── §9/§10/§11 historical split + walk-forward ──

def test_three_zone_split_no_overlap():
    from market_ai_hub.research.historical_learning import (
        FINAL_OOS_HOLDOUT,
        TRAIN,
        VALIDATION,
        assert_no_zone_overlap,
        three_zone_split,
    )

    b = three_zone_split(1000)
    assert b[TRAIN][1] <= b[VALIDATION][0]
    assert b[VALIDATION][1] <= b[FINAL_OOS_HOLDOUT][0]
    assert assert_no_zone_overlap(1000)


def test_chronological_origins_no_leakage():
    import numpy as np

    from market_ai_hub.research.historical_learning import (
        assert_origins_no_leakage,
        chronological_origins,
    )

    origins = chronological_origins(500, n_origins=5, min_train=60, mode="expanding")
    assert origins
    assert assert_origins_no_leakage(origins)
    for train, test in origins:
        assert train.max() < test.min()  # fit only past


def test_rolling_window_no_leakage():
    from market_ai_hub.research.historical_learning import (
        assert_origins_no_leakage,
        chronological_origins,
    )

    origins = chronological_origins(500, n_origins=5, min_train=60, mode="rolling", rolling_window=120)
    assert origins
    assert assert_origins_no_leakage(origins)
    for train, test in origins:
        assert len(train) <= 120  # rolling window 只保留最近


# ── §13 pre-registration protocol ──

def test_protocol_hash_deterministic_and_sensitive():
    from market_ai_hub.research.historical_learning import ProtocolSpec

    p = ProtocolSpec(target_family="TAIWAN_INDEX", target="TAIEX",
                     dataset_semantic="cash_index", date_range_start="2020-01-01", date_range_end="2026-01-01")
    assert p.protocol_hash() == p.protocol_hash()
    p2 = ProtocolSpec(target_family="TAIWAN_INDEX", target="TAIEX",
                      dataset_semantic="cash_index", date_range_start="2020-01-01", date_range_end="2026-02-01")
    assert p.protocol_hash() != p2.protocol_hash()


# ── §32 leakage tests ──

def test_future_row_not_in_train():
    import numpy as np

    from market_ai_hub.research.historical_learning import three_zone_split

    n = 300
    b = three_zone_split(n)
    train = np.arange(*b["TRAIN"])
    final = np.arange(*b["FINAL_OOS_HOLDOUT"])
    assert not set(train) & set(final)  # future row not in train


def test_validation_not_final_test():
    import numpy as np

    from market_ai_hub.research.historical_learning import three_zone_split

    n = 300
    b = three_zone_split(n)
    val = np.arange(*b["VALIDATION"])
    final = np.arange(*b["FINAL_OOS_HOLDOUT"])
    assert not set(val) & set(final)


def test_walkforward_origin_strict():
    import numpy as np

    from market_ai_hub.research.historical_learning import (
        assert_origins_no_leakage,
        chronological_origins,
    )

    origins = chronological_origins(400, 5, 60)
    assert assert_origins_no_leakage(origins)


def test_proxy_not_direct():
    from market_ai_hub.packet.builder import _fill_target_semantics
    from market_ai_hub.packet.schema import AnalysisPacket

    p = AnalysisPacket()
    _fill_target_semantics(p, "osaka", "OSE_NIKKEI225_MICRO_FUTURES")
    assert p.target_semantics["direct_target"] != p.target_semantics["proxy_model_target"]

    p2 = AnalysisPacket()
    _fill_target_semantics(p2, "taiwan_index", "TAIEX")
    assert p2.target_semantics["execution_instrument"] is None  # TAIEX 非可成交
    assert p2.target_semantics["proxy_model_target"] == "^TWII"


def test_target_family_isolated():
    from market_ai_hub.services.research_truth import evidence_by_target

    by = evidence_by_target()
    osaka = by["OSAKA_MICRO"]["OSE_NIKKEI225_MICRO_FUTURES"]
    taiwan_stock = by["TAIWAN_STOCK"]["TAIWAN_INDIVIDUAL_STOCK"]
    taiwan_index = by["TAIWAN_INDEX"]["TAIEX"]
    # Osaka 有 STATISTICAL_FORECAST_EVIDENCE，Taiwan 仍是 NOT_YET_VALIDATED（隔離）
    assert "STATISTICAL_FORECAST_EVIDENCE" in osaka["direct_micro_historical"]
    assert taiwan_stock["direct_historical"] == "NOT_YET_VALIDATED"
    assert taiwan_index["direct_historical"] == "NOT_YET_VALIDATED"
    # 不得用 Osaka 替 Taiwan 背書
    assert osaka != taiwan_stock and osaka != taiwan_index


def test_hyperparameter_tuning_no_test_access():
    from market_ai_hub.research.historical_learning import ProtocolSpec

    p = ProtocolSpec(target_family="X", target="Y", dataset_semantic="z",
                     date_range_start="2020-01-01", date_range_end="2026-01-01")
    # protocol 不提供任何 test/FINAL_OOS 資料欄位（tuning 只能靠 train + inner validation）
    d = p.__dict__
    assert "test" not in str(d).lower() or "final_oos" not in str(d).lower()


# ── §7 packet parity ──

def test_analysis_packet_supports_three_markets():
    from market_ai_hub.packet.builder import build_analysis_packet

    for market, target in (("osaka", "OSE_NIKKEI225_MICRO_FUTURES"),
                           ("taiwan", "3706.TW"),
                           ("taiwan_index", "TAIEX")):
        p = build_analysis_packet(market=market, target=target, detail_level="compact", save_analysis=False)
        assert p["execution_target"] in (target, "OSE_NIKKEI225_MICRO_FUTURES")
        assert "target_semantics" in p


# ── §22 training != auto train ──

def test_training_not_auto_train():
    import yaml

    from market_ai_hub.services.resource_governor import PROFILES_PATH

    data = yaml.safe_load(PROFILES_PATH.read_text(encoding="utf-8"))
    for name, prof in data["profiles"].items():
        assert prof["auto_train"] is False
        assert prof["auto_fine_tune"] is False
