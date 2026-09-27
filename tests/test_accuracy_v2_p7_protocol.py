from pathlib import Path

import pytest
import yaml

from market_ai_hub.research.accuracy_v2_p7 import P7ProtocolError, load_p7_protocol


def _mutated(tmp_path, mutate):
    payload = yaml.safe_load(Path("config/accuracy_v2_p7_protocol.yaml").read_text(encoding="utf-8"))
    raw = payload["protocols"]["independent_engine_acceptance_v1"]
    mutate(raw)
    p = tmp_path / "p7.yaml"
    p.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return p


def test_p7_protocol_freezes_isolated_nautilus_and_completion_boundary():
    p = load_p7_protocol()
    assert p.raw["engine"]["release"] == "1.231.0"
    assert p.raw["engine"]["commit"] == "27a8e54"
    assert p.raw["engine"]["core_venv_install_allowed"] is False
    assert p.raw["engine"]["live_execution_allowed"] is False
    assert p.raw["parity"]["deterministic_repeats"] == 2
    assert p.raw["cost_diagnostic"]["presets"] == ["ZERO_COST", "BASE_COST", "STRESS_COST"]
    assert "P6_CONDITIONAL_FEATURE" in p.raw["completion"]["does_not_require"]
    assert len(p.hash) == 64


def test_p7_rejects_core_install(tmp_path):
    p = _mutated(tmp_path, lambda raw: raw["engine"].__setitem__("core_venv_install_allowed", True))
    with pytest.raises(P7ProtocolError, match="core venv"):
        load_p7_protocol(path=p)


def test_p7_rejects_live_execution(tmp_path):
    p = _mutated(tmp_path, lambda raw: raw["engine"].__setitem__("live_execution_allowed", True))
    with pytest.raises(P7ProtocolError, match="live execution"):
        load_p7_protocol(path=p)


def test_p7_rejects_single_repeat(tmp_path):
    p = _mutated(tmp_path, lambda raw: raw["parity"].__setitem__("deterministic_repeats", 1))
    with pytest.raises(P7ProtocolError, match="repeat"):
        load_p7_protocol(path=p)


def test_p7_rejects_actual_cost_claim(tmp_path):
    p = _mutated(
        tmp_path,
        lambda raw: raw["cost_diagnostic"].__setitem__("actual_execution_cost_claim_allowed", True),
    )
    with pytest.raises(P7ProtocolError, match="actual execution cost"):
        load_p7_protocol(path=p)


def test_p7_rejects_runtime_handover(tmp_path):
    p = _mutated(
        tmp_path,
        lambda raw: raw["migration_acceptance"].__setitem__("runtime_handover_allowed", True),
    )
    with pytest.raises(P7ProtocolError, match="runtime handover"):
        load_p7_protocol(path=p)
