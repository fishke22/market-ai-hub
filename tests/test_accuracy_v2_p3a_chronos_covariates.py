"""Accuracy v2 P3-A: Chronos-2 past-only covariate engineering contract."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest
import torch

from market_ai_hub.models.chronos_model import (
    CHRONOS2_QUANTILES,
    ChronosAdapter,
    ChronosCovariateContractError,
    ChronosPastCovariate,
    chronos_forecast,
    prepare_chronos_past_covariates,
)


DECISION = datetime(2026, 9, 18, 6, 45, tzinfo=timezone.utc)


def _target(n: int = 32) -> pd.Series:
    idx = pd.date_range("2026-08-01", periods=n, freq="B", tz="UTC")
    return pd.Series(100.0 + np.arange(n) * 0.25, index=idx)


def _cov(target: pd.Series | None = None, *, shift: float = 0.0) -> ChronosPastCovariate:
    target = target if target is not None else _target()
    n = len(target)
    event = [
        DECISION - timedelta(days=n - i + 1, hours=2)
        for i in range(n)
    ]
    available = [x + timedelta(minutes=2) for x in event]
    values = pd.Series(np.linspace(-0.02, 0.03, n) + shift, index=target.index)
    return ChronosPastCovariate(
        values=values,
        event_time=event,
        available_at=available,
        source_hashes=[f"src-{i}" for i in range(n)],
        feature_version="p3a-test-v1",
    )


class _FakePipeline:
    def __init__(self):
        self.calls = []

    def predict(self, inputs, prediction_length):
        self.calls.append((inputs, prediction_length))
        out = torch.zeros(
            (1, len(CHRONOS2_QUANTILES), prediction_length),
            dtype=torch.float32,
        )
        for q_idx, q in enumerate(CHRONOS2_QUANTILES):
            out[0, q_idx, :] = 100.0 + float(q)
        return [out]


def _adapter_with_fake_pipeline() -> tuple[ChronosAdapter, _FakePipeline]:
    adapter = ChronosAdapter(device="cpu")
    pipe = _FakePipeline()
    adapter._pipeline = pipe
    return adapter, pipe


def test_p3a_adapter_passes_only_past_covariates_to_installed_chronos_schema():
    target = _target()
    adapter, pipe = _adapter_with_fake_pipeline()
    out = adapter.predict(
        target,
        horizon=3,
        past_covariates={"nq_lagged_return": _cov(target)},
        decision_time=DECISION,
    )
    inputs, horizon = pipe.calls[-1]
    assert horizon == 3
    assert isinstance(inputs, list) and len(inputs) == 1
    assert set(inputs[0]) == {"target", "past_covariates"}
    assert set(inputs[0]["past_covariates"]) == {"nq_lagged_return"}
    assert len(inputs[0]["target"]) == len(target)
    assert len(inputs[0]["past_covariates"]["nq_lagged_return"]) == len(target)
    assert out["metadata"]["past_only_covariates_used"] is True
    assert out["metadata"]["future_covariates_allowed"] is False


def test_p3a_future_covariates_fail_before_model_load(monkeypatch):
    adapter = ChronosAdapter(device="cpu")
    called = {"load": 0}

    def _boom():
        called["load"] += 1
        raise AssertionError("future-covariate rejection must happen before weight load")

    monkeypatch.setattr(adapter, "load", _boom)
    with pytest.raises(
        ChronosCovariateContractError,
        match="FUTURE_COVARIATES_BLOCKED_P3A",
    ):
        adapter.predict(
            _target(),
            horizon=1,
            future_covariates={"calendar": np.array([1.0])},
            decision_time=DECISION,
        )
    assert called["load"] == 0

    with pytest.raises(
        ChronosCovariateContractError,
        match="FUTURE_COVARIATES_BLOCKED_P3A",
    ):
        adapter.predict(
            _target(),
            horizon=1,
            future_covariates={},
            decision_time=DECISION,
        )
    assert called["load"] == 0


def test_p3a_covariates_require_decision_time_before_model_load(monkeypatch):
    adapter = ChronosAdapter(device="cpu")
    called = {"load": 0}

    def _load():
        called["load"] += 1

    monkeypatch.setattr(adapter, "load", _load)
    with pytest.raises(ChronosCovariateContractError, match="decision_time is required"):
        adapter.predict(_target(), past_covariates={"x": _cov()})
    assert called["load"] == 0


def test_p3a_rejects_late_or_future_covariate_availability():
    target = _target()
    cov = _cov(target)
    late = ChronosPastCovariate(
        values=cov.values,
        event_time=cov.event_time,
        available_at=[*list(cov.available_at)[:-1], DECISION + timedelta(seconds=1)],
        source_hashes=cov.source_hashes,
        feature_version=cov.feature_version,
    )
    with pytest.raises(ChronosCovariateContractError, match="FUTURE_AVAILABLE_AT"):
        prepare_chronos_past_covariates(
            target,
            {"x": late},
            decision_time=DECISION,
        )


def test_p3a_rejects_event_after_available_duplicate_time_and_length_mismatch():
    target = _target()
    cov = _cov(target)

    bad_event = list(cov.event_time)
    bad_event[-1] = list(cov.available_at)[-1] + timedelta(seconds=1)
    with pytest.raises(ChronosCovariateContractError, match="event_time exceeds available_at"):
        prepare_chronos_past_covariates(
            target,
            {
                "x": ChronosPastCovariate(
                    cov.values,
                    bad_event,
                    cov.available_at,
                    cov.source_hashes,
                    cov.feature_version,
                )
            },
            decision_time=DECISION,
        )

    dup_event = list(cov.event_time)
    dup_event[-1] = dup_event[-2]
    dup_available = [x + timedelta(minutes=2) for x in dup_event]
    with pytest.raises(ChronosCovariateContractError, match="strictly increasing"):
        prepare_chronos_past_covariates(
            target,
            {
                "x": ChronosPastCovariate(
                    cov.values,
                    dup_event,
                    dup_available,
                    cov.source_hashes,
                    cov.feature_version,
                )
            },
            decision_time=DECISION,
        )

    with pytest.raises(ChronosCovariateContractError, match="values length"):
        prepare_chronos_past_covariates(
            target,
            {
                "x": ChronosPastCovariate(
                    np.ones(len(target) - 1),
                    cov.event_time[:-1],
                    cov.available_at[:-1],
                    cov.source_hashes[:-1],
                    cov.feature_version,
                )
            },
            decision_time=DECISION,
        )


def test_p3a_rejects_nonfinite_missing_provenance_and_index_mismatch():
    target = _target()
    cov = _cov(target)

    nonfinite = cov.values.copy()
    nonfinite.iloc[-1] = np.inf
    with pytest.raises(ChronosCovariateContractError, match="non-finite"):
        prepare_chronos_past_covariates(
            target,
            {
                "x": ChronosPastCovariate(
                    nonfinite,
                    cov.event_time,
                    cov.available_at,
                    cov.source_hashes,
                    cov.feature_version,
                )
            },
            decision_time=DECISION,
        )

    with pytest.raises(ChronosCovariateContractError, match="source_hash"):
        prepare_chronos_past_covariates(
            target,
            {
                "x": ChronosPastCovariate(
                    cov.values,
                    cov.event_time,
                    cov.available_at,
                    [""] * len(target),
                    cov.feature_version,
                )
            },
            decision_time=DECISION,
        )

    shifted = cov.values.copy()
    shifted.index = shifted.index + pd.Timedelta(days=1)
    with pytest.raises(ChronosCovariateContractError, match="index must exactly match"):
        prepare_chronos_past_covariates(
            target,
            {
                "x": ChronosPastCovariate(
                    shifted,
                    cov.event_time,
                    cov.available_at,
                    cov.source_hashes,
                    cov.feature_version,
                )
            },
            decision_time=DECISION,
        )


def test_p3a_identity_changes_on_values_availability_source_or_feature_revision():
    target = _target()
    base = _cov(target)
    _, a = prepare_chronos_past_covariates(
        target,
        {"x": base},
        decision_time=DECISION,
    )

    _, b = prepare_chronos_past_covariates(
        target,
        {"x": _cov(target, shift=0.001)},
        decision_time=DECISION,
    )

    available = list(base.available_at)
    available[-1] = available[-1] + timedelta(seconds=1)
    _, c = prepare_chronos_past_covariates(
        target,
        {
            "x": ChronosPastCovariate(
                base.values,
                base.event_time,
                available,
                base.source_hashes,
                base.feature_version,
            )
        },
        decision_time=DECISION,
    )

    hashes = list(base.source_hashes)
    hashes[-1] = "different-source"
    _, d = prepare_chronos_past_covariates(
        target,
        {
            "x": ChronosPastCovariate(
                base.values,
                base.event_time,
                base.available_at,
                hashes,
                base.feature_version,
            )
        },
        decision_time=DECISION,
    )

    _, e = prepare_chronos_past_covariates(
        target,
        {
            "x": ChronosPastCovariate(
                base.values,
                base.event_time,
                base.available_at,
                base.source_hashes,
                "p3a-test-v2",
            )
        },
        decision_time=DECISION,
    )
    assert len({x["identity_hash"] for x in (a, b, c, d, e)}) == 5

    shifted_target = target.copy()
    shifted_target.index = shifted_target.index + pd.Timedelta(days=7)
    shifted_cov = _cov(shifted_target)
    _, f = prepare_chronos_past_covariates(
        shifted_target,
        {"x": shifted_cov},
        decision_time=DECISION,
    )
    assert f["identity_hash"] != a["identity_hash"]
    assert f["target_index_hash"] != a["target_index_hash"]


def test_p3a_forecast_output_hash_and_metadata_include_covariate_identity(monkeypatch):
    target = _target()
    adapter, _ = _adapter_with_fake_pipeline()
    monkeypatch.setattr(
        "market_ai_hub.models.chronos_model.quote_freshness",
        lambda *a, **k: {
            "market_open": False,
            "tradable_now": False,
            "source_timestamp": "",
            "received_at": "",
            "quote_age_seconds": None,
            "freshness_status": "TEST",
            "session_status": "CLOSED",
            "quote_live": False,
            "usable_for_live_decision": False,
        },
    )
    plain = chronos_forecast(
        adapter,
        "X",
        target,
        horizon="1d",
        horizon_steps=1,
    )
    with_cov = chronos_forecast(
        adapter,
        "X",
        target,
        horizon="1d",
        horizon_steps=1,
        past_covariates={"nq_lagged_return": _cov(target)},
        decision_time=DECISION,
    )
    assert plain.input_data_hash != with_cov.input_data_hash
    assert plain.forecast_config_hash != with_cov.forecast_config_hash
    assert with_cov.model_metadata["adapter_implements_past_only_covariates"] is True
    assert with_cov.model_metadata["future_covariates_allowed_p3a"] is False
    assert with_cov.model_metadata["past_only_covariates_used"] is True
    assert with_cov.model_metadata["covariate_identity"]["covariate_names"] == [
        "nq_lagged_return"
    ]


def test_p3a_registry_marks_adapter_implemented_but_runtime_not_verified():
    from market_ai_hub.services.model_governance import model_capability_inventory

    inv = model_capability_inventory("chronos-2")
    assert inv["upstream_support"]["covariates"] is True
    assert inv["adapter_implemented"]["past_only_covariates"] is True
    assert inv["adapter_implemented"]["future_covariates"] is False
    assert inv["local_verified"]["covariates"] is False
