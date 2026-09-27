from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from market_ai_hub.integrations.open_source_research import (
    OpenSourceAdapterError,
    load_open_source_manifest,
    open_source_adapter_status,
)
from market_ai_hub.research.accuracy_v2_p4 import P4ProtocolError, load_p4_protocol
from market_ai_hub.research.future_data_acquisition import (
    FutureDataPlanError,
    future_data_readiness,
    load_future_data_plan,
)


def test_p4_protocol_is_frozen_and_preserves_p2_baseline():
    p = load_p4_protocol()
    assert p.raw["evidence_boundaries"]["point_champion"] == "ZERO_RETURN_NAIVE"
    assert p.raw["quantile_challenger"]["tuning"] == "NONE"
    assert p.raw["conformal"]["initial_fit_partition"] == "DEVELOPMENT_ONLY"
    assert p.raw["regime"]["model_switching_allowed"] is False
    assert p.raw["promotion"]["point_default_without_gain"] == "ZERO_RETURN_NAIVE"
    assert len(p.hash) == 64


def test_p4_rejects_quarantine_reuse(tmp_path):
    src = Path("config/accuracy_v2_p4_protocol.yaml")
    payload = yaml.safe_load(src.read_text(encoding="utf-8"))
    raw = payload["protocols"]["jnu_no_future_analysis_v1"]
    raw["evidence_boundaries"]["exposed_quarantine_use_for_fit"] = True
    p = tmp_path / "bad.yaml"
    p.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with pytest.raises(P4ProtocolError, match="quarantine"):
        load_p4_protocol(path=p)


def test_p4_rejects_probability_or_future_fill_upgrade(tmp_path):
    src = Path("config/accuracy_v2_p4_protocol.yaml")
    payload = yaml.safe_load(src.read_text(encoding="utf-8"))
    raw = payload["protocols"]["jnu_no_future_analysis_v1"]
    raw["inference_context"]["future_fill_allowed"] = True
    p = tmp_path / "bad.yaml"
    p.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with pytest.raises(P4ProtocolError, match="future fill"):
        load_p4_protocol(path=p)


def test_open_source_boundaries_do_not_mutate_core_or_enable_live():
    specs = load_open_source_manifest()
    assert specs["qlib"].raw["release"] == "v0.9.7"
    assert specs["qlib"].raw["release_commit"] == "da920b7"
    assert specs["qlib"].raw["core_venv_install_allowed"] is False
    assert specs["nautilus_trader"].raw["selected_release"] == "1.231.0"
    assert specs["nautilus_trader"].raw["not_selected_prerelease"] == "2.0.0rc5"
    status = open_source_adapter_status()
    assert status["qlib"]["live_execution_allowed"] is False
    assert status["nautilus_trader"]["live_execution_allowed"] is False


def test_open_source_manifest_rejects_live_execution(tmp_path):
    src = Path("config/open_source_research_adapters.yaml")
    payload = yaml.safe_load(src.read_text(encoding="utf-8"))
    payload["adapters"]["qlib"]["live_execution_allowed"] = True
    p = tmp_path / "bad.yaml"
    p.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with pytest.raises(OpenSourceAdapterError, match="live execution"):
        load_open_source_manifest(p)


def test_future_data_plan_has_public_collectors_and_blocked_cme_web():
    _, sources = load_future_data_plan()
    assert sources["jpx_micro_settlement"].active_public_collector
    assert sources["taifex_tmf_settlement"].active_public_collector
    assert sources["cme_public_website_settlement"].status == "BLOCKED_AUTOMATED_WEBSITE_ACCESS"
    ready = future_data_readiness()
    assert ready["orders_allowed"] is False
    assert ready["account_access_allowed"] is False
    assert ready["recorder_restart_allowed"] is False


def test_future_data_plan_rejects_blocked_source_that_is_not_disabled(tmp_path):
    src = Path("config/future_data_acquisition.yaml")
    payload = yaml.safe_load(src.read_text(encoding="utf-8"))
    payload["sources"]["cme_public_website_settlement"]["acquisition"] = "PUBLIC_HTTP"
    p = tmp_path / "bad.yaml"
    p.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with pytest.raises(FutureDataPlanError, match="blocked source"):
        load_future_data_plan(p)
