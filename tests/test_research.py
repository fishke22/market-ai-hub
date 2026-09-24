"""Phase 2A research tests：registry immutability / outcome append-only /
no look-ahead / settlement / FEV adapter / MLflow。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from market_ai_hub.research.registry import PredictionRegistry
from market_ai_hub.research.schemas import (
    LookAheadError,
    OutcomeRecord,
    PredictionRecord,
    assert_no_lookahead,
)
from market_ai_hub.research.forward import compute_outcome, settle_forecast


def _rec(fid="f-1", cutoff=None, origin_price=100.0, point=102.0, p10=100.5, p50=102.0, p90=103.5,
         direction="up", model="chronos-2", targets=None):
    return PredictionRecord(
        forecast_id=fid,
        information_cutoff=cutoff or datetime(2026, 9, 18, 6, 0, tzinfo=timezone.utc),
        forecast_origin=datetime(2026, 9, 18, 6, 0, tzinfo=timezone.utc),
        forecast_target_dates=targets or ["2026-09-24"],
        exchange_calendar="XTKS",
        model_name=model,
        model_task="PRICE_FORECAST",
        model_revision="rev",
        point_forecast=point,
        p10=p10, p50=p50, p90=p90,
        origin_price=origin_price,
        direction=direction,
    )


def test_prediction_registry_immutable(tmp_path):
    reg = PredictionRegistry(root=tmp_path)
    reg.register(_rec("f-1"))
    # 重複 register → 拒絕
    with pytest.raises(ValueError):
        reg.register(_rec("f-1", point=999.0))
    # 內容未變
    assert reg.get("f-1")["point_forecast"] == 102.0


def test_outcome_append_only(tmp_path):
    reg = PredictionRegistry(root=tmp_path)
    reg.register(_rec("f-1"))
    o = OutcomeRecord(forecast_id="f-1", actual=103.0, absolute_error=1.0, squared_error=1.0)
    reg.settle(o)
    # 重複 settle → 拒絕
    with pytest.raises(ValueError):
        reg.settle(OutcomeRecord(forecast_id="f-1", actual=104.0, absolute_error=2.0, squared_error=4.0))
    # settle 不存在的 forecast → 拒絕
    with pytest.raises(ValueError):
        reg.settle(OutcomeRecord(forecast_id="nope", actual=1.0, absolute_error=1.0, squared_error=1.0))
    assert reg.is_settled("f-1")


def test_information_cutoff_leakage_rejected():
    cutoff = datetime(2026, 9, 18, 6, 0, tzinfo=timezone.utc)
    assert_no_lookahead(cutoff, [datetime(2026, 9, 17, tzinfo=timezone.utc)])  # ok
    with pytest.raises(LookAheadError):
        assert_no_lookahead(cutoff, [datetime(2026, 9, 19, tzinfo=timezone.utc)])  # 未來 → reject


def test_forward_settlement():
    rec = _rec("f-1", origin_price=100.0, point=102.0, p10=100.5, p50=102.0, p90=103.5, direction="up")
    o = compute_outcome(rec, actual=103.0)
    assert o.absolute_error == pytest.approx(1.0)
    assert o.squared_error == pytest.approx(1.0)
    assert o.direction_result == "correct"
    assert o.interval_hit is True
    assert o.pinball_loss == pytest.approx(0.5 * (103.0 - 102.0))
    assert o.scaled_error == pytest.approx(1.0 / 3.0)


def test_forward_settlement_wrong_direction():
    rec = _rec("f-1", origin_price=100.0, point=102.0, direction="up")
    o = compute_outcome(rec, actual=99.0)
    assert o.direction_result == "incorrect"


def test_settle_forecast_persists(tmp_path):
    reg = PredictionRegistry(root=tmp_path)
    reg.register(_rec("f-1"))
    settle_forecast(reg, "f-1", actual=103.0)
    assert reg.is_settled("f-1")
    lb = reg.leaderboard()
    assert lb[0]["model_name"] == "chronos-2"
    assert lb[0]["n"] == 1


def test_forecast_target_dates_preserved(tmp_path):
    reg = PredictionRegistry(root=tmp_path)
    targets = ["2026-09-24", "2026-09-25"]
    reg.register(_rec("f-2", targets=targets))
    got = reg.get("f-2")
    assert got["forecast_target_dates"] == targets


def test_schema_versioned_non_destructive(tmp_path):
    reg = PredictionRegistry(root=tmp_path)
    assert reg.schema_version() == 1
    reg.register(_rec("f-1"))
    # 重新 init（模擬 migration）不得刪除既有資料
    reg.init()
    assert reg.get("f-1")["forecast_id"] == "f-1"


def test_parquet_export(tmp_path):
    reg = PredictionRegistry(root=tmp_path)
    reg.register(_rec("f-1"))
    settle_forecast(reg, "f-1", actual=103.0)
    p_pred, p_out = reg.export_parquet()
    assert p_pred.exists() and p_out.exists()


def test_fev_adapter_baselines_and_metrics():
    from market_ai_hub.research.evaluation import (
        FEVAdapter,
        classification_baselines,
        classification_metrics,
        make_fev_adapter,
        price_metrics,
    )

    a = np.array([100.0, 101.0, 102.0, 103.0])
    f = np.array([100.5, 101.2, 102.1, 103.2])
    naive = np.array([99.5, 100.5, 101.5, 102.5])
    m = price_metrics(a, f, naive, p10=f - 0.5, p90=f + 0.5)
    assert m["mae"] > 0 and m["rmse"] > 0 and m["mase"] > 0
    assert 0 <= m["interval_coverage"] <= 1

    y_true = np.array([1, -1, 0, 1, -1, 0])
    y_pred = np.array([1, -1, 0, 1, -1, 0])
    cm = classification_metrics(y_true, y_pred, train_labels=np.array([1, -1, 0, 1, -1, 0]))
    assert cm["accuracy"] == 1.0
    assert cm["baseline_threshold"] == pytest.approx(max(cm["majority_class_baseline_accuracy"], cm["uniform_baseline_accuracy"]))

    bases = classification_baselines(y_true)
    assert set(bases) == {"majority_class", "always_flat"}

    fev = make_fev_adapter()
    assert isinstance(fev, FEVAdapter)
    assert fev.evaluate_price(a, f, naive)["mae"] == pytest.approx(m["mae"])


def test_mlflow_recording(tmp_path, monkeypatch):
    from market_ai_hub.research.mlflow_tracker import sanitize_params, start_run

    monkeypatch.setattr("market_ai_hub.research.mlflow_tracker.TRACKING_URI",
                        "sqlite:///" + str(tmp_path / "mlflow.db").replace("\\", "/"))
    # sanitize 移除 secret key
    clean = sanitize_params({"model": "chronos-2", "api_key": "SECRET", "revision": "rev"})
    assert "api_key" not in clean and clean["model"] == "chronos-2"
    summary = start_run("test", clean, {"mae": 1.5}, artifact_ref="f-1")
    assert summary["run_id"]
    assert (tmp_path / "mlflow.db").exists()


def test_v1_build_unchanged():
    """build_id 凍結：Phase 2H MCP 整合後新 build_id（含 V1 correctness contract）。"""
    from market_ai_hub.services.build_info import build_fingerprint

    assert build_fingerprint()["build_id"] == "549df22a3dff85f3"
