"""Offline regressions for invalid predictions and one-use research evidence."""
from dataclasses import replace
import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from market_ai_hub.schemas.market_data import validate_price_path, validate_quantiles
from market_ai_hub.research import historical_prequential as hp
from market_ai_hub.services.jnu_direct import _model_result


@pytest.mark.parametrize("path", [
    {"p10": [1], "p50": [float("inf")], "p90": [float("inf")]},
    {"p10": [3], "p50": [2], "p90": [4]},
    {"p10": [0], "p50": [2], "p90": [4]},
    {"p10": [1, 1], "p50": [2, 2], "p90": [3, 3]},
    {"p10": [None], "p50": [2], "p90": [3]},
])
def test_malformed_price_path_cannot_enter_direct_forecast(path):
    class Adapter:
        def predict(self, series, horizon):
            return {"path": path}
    with pytest.raises(ValueError):
        _model_result(Adapter(), "test", pd.Series([2.0]), 1, ["2026-09-28"])


def test_quantile_missing_bounds_does_not_hide_infinite_median():
    assert not validate_quantiles({"p50": float("inf")})[0]
    validate_price_path({"p10": [1], "p50": [2], "p90": [3]}, 1)


def test_sealed_identity_cannot_hide_changed_forecasts(tmp_path):
    first = {"status": "OK", "evidence_id": "same", "prediction": 1}
    path = hp.save_one_use_evidence(first, tmp_path)
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match="ALREADY_OPENED"):
        hp.save_one_use_evidence({**first, "prediction": 2}, tmp_path)
    assert path.read_bytes() == before


def test_cli_reads_seal_before_loading_models_and_reserves_failed_attempt(tmp_path, monkeypatch, capsys):
    script = Path(__file__).parents[1] / "scripts/run_jnu_historical_prequential.py"
    spec = importlib.util.spec_from_file_location("hpq_cli", script)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setattr(cli, "evidence_dir", lambda: tmp_path)
    monkeypatch.setattr(cli, "load_sealed_evidence", lambda: {"status": "OK"})
    def forbidden():
        raise AssertionError("model must not load after final holdout opened")
    monkeypatch.setattr(cli, "get_chronos", forbidden)
    assert cli.main() == 0
    monkeypatch.setattr(cli, "load_sealed_evidence", lambda: None)
    with pytest.raises(AssertionError):
        cli.main()
    with pytest.raises(FileExistsError):
        cli.main()


def test_known_training_cutoff_alone_never_proves_clean_oos(monkeypatch):
    from test_historical_prequential import _frame, _protocol, _LastPriceAdapter
    monkeypatch.setattr(hp, "_model_identity", lambda name: {
        "name": name, "training_cutoff_known": True, "training_cutoff": "2099-01-01",
    })
    result = hp.run_replay({"test": _LastPriceAdapter()}, frame=_frame(), protocol=_protocol())
    assert result["evidence_grade"] == "HISTORICAL_PREQUENTIAL_OOS_NOT_VERIFIED"
    with pytest.raises(ValueError, match="horizon"):
        hp.run_replay({"test": _LastPriceAdapter()}, frame=_frame(), protocol=replace(_protocol(), horizon_steps=2))


def test_missing_holiday_session_is_not_one_day_evidence():
    from test_historical_prequential import _frame, _protocol
    frame = _frame()
    frame = frame[frame["date"] != "2026-01-08"]
    origins = hp.build_front_contract_origins(frame, _protocol())
    assert not any(str(x.origin_date) == "2026-01-07" for x in origins)
    evidence = {"status": "OK", "models": {"test": {"records": [{
        "origin_date": "2026-09-18", "target_date": "2026-09-24",
    }]}}}
    assert hp.compact_evidence_summary(evidence)["status"] == "BLOCKED_HORIZON_MISMATCH"
    assert hp.equal_weight_ensemble_summary(evidence)["status"] == "BLOCKED_HORIZON_MISMATCH"


def test_cross_market_returns_align_timestamps_without_filling_missing_prices():
    from market_ai_hub.features.features import cross_market_features
    dates = pd.date_range("2026-09-21", periods=4, tz="UTC")
    frame = pd.DataFrame({"symbol": ["A"] * 4 + ["B"] * 4,
        "timestamp_utc": list(dates) * 2,
        "close": [100, 110, None, 121, 200, 180, 180, 180]})
    result = cross_market_features(frame)
    assert result.index.is_unique
    assert result.loc[dates[1], "A_return"] == pytest.approx(.1)
    assert result.loc[dates[1], "B_return"] == pytest.approx(-.1)
    assert pd.isna(result.loc[dates[2], "A_return"])
    assert pd.isna(result.loc[dates[3], "A_return"])
    with pytest.raises(ValueError, match="duplicate"):
        cross_market_features(pd.concat([frame, frame.iloc[:1]]))
