"""分類 baselines / dual status / gates（V1 remediation Phase 5/7/12）。"""
import numpy as np
import pytest


def test_classification_metrics_and_baselines():
    from market_ai_hub.backtest.walk_forward import classification_metrics

    rng = np.random.default_rng(7)
    y_true = rng.choice([-1, 0, 1], size=300, p=[0.2, 0.6, 0.2])
    y_pred = y_true.copy()
    y_pred[::10] = 0  # 90% 正確
    train = rng.choice([-1, 0, 1], size=1000, p=[0.2, 0.6, 0.2])

    cm = classification_metrics(y_true, y_pred, train)
    assert cm["accuracy"] > 0.8
    assert cm["balanced_accuracy"] > 0.8
    assert cm["uniform_random_baseline_accuracy"] == pytest.approx(1 / 3, abs=1e-3)
    assert cm["majority_class_baseline_accuracy"] == pytest.approx(0.6, abs=0.05)
    assert cm["baseline_threshold"] == pytest.approx(0.6, abs=0.05)
    # 90% 正確的模型必須被判為超越 baseline
    assert cm["beats_majority_baseline"] is True


def test_weak_model_not_eligible():
    from market_ai_hub.backtest.walk_forward import classification_metrics

    rng = np.random.default_rng(3)
    y_true = rng.choice([-1, 0, 1], size=300, p=[0.2, 0.6, 0.2])
    y_pred = rng.choice([-1, 0, 1], size=300, p=[0.2, 0.6, 0.2])  # 隨機
    train = rng.choice([-1, 0, 1], size=1000, p=[0.2, 0.6, 0.2])
    cm = classification_metrics(y_true, y_pred, train)
    assert cm["beats_majority_baseline"] is False


def test_dual_status_independent():
    from market_ai_hub.schemas.market_data import EngineeringStatus, PredictiveValidationStatus

    # engineering PASS ≠ predictive VALIDATED
    assert EngineeringStatus.PASS.value == "PASS"
    assert PredictiveValidationStatus.UNVALIDATED.value == "UNVALIDATED"
    assert EngineeringStatus.PASS.value != PredictiveValidationStatus.VALIDATED.value


@pytest.mark.integration
def test_catalog_ts_models_unvalidated():
    from market_ai_hub.services.model_catalog import ModelCard, live_model_cards

    cards = live_model_cards()
    # 無 OOS record 時 TS 模型不得 VALIDATED
    assert cards["chronos-2"].predictive_validation_status in ("UNVALIDATED", "EXPERIMENTAL", "DEGRADED")
    assert cards["timesfm-3.0"].predictive_validation_status in ("UNVALIDATED", "EXPERIMENTAL", "DEGRADED")
    # 未驗證 → 不參與方向投票
    assert cards["chronos-2"].eligible_for_direction_vote is False


@pytest.mark.integration
def test_classifier_vote_rule_respects_baseline(monkeypatch):
    """有 OOS record 但未超越 baseline → 不得 eligible_for_direction_vote。"""
    from market_ai_hub.services import model_catalog
    import market_ai_hub.storage.performance as perf_mod

    class FakeStore:
        def latest_by_model(self):
            return {
                "xgboost": {"balanced_accuracy": 0.30, "majority_class_baseline_accuracy": 0.6,
                            "uniform_random_baseline_accuracy": 1 / 3, "n_samples": 100},
            }

    monkeypatch.setattr(perf_mod, "PerformanceStore", FakeStore)
    cards = model_catalog.live_model_cards()
    assert cards["xgboost"].eligible_for_direction_vote is False
    assert cards["xgboost"].predictive_validation_status == "DEGRADED"


@pytest.mark.integration
def test_gates_defaults():
    from market_ai_hub.services.model_catalog import compute_research_gates, live_model_cards

    gates = compute_research_gates(live_model_cards())
    assert {
        "ENGINEERING_GATE", "DATA_GATE", "MODEL_PREDICTIVE_GATE", "TRADING_EDGE_GATE",
        "MARKET_DATA_GATE", "CALENDAR_GATE", "TEMPORAL_ALIGNMENT_GATE",
    } <= set(gates)
    assert gates["TRADING_EDGE_GATE"]["status"] == "UNPROVEN"
    for g in gates.values():
        assert "status" in g and "reason" in g and "evidence" in g
        assert "evaluated_at" in g and "build_id" in g


def test_naive_baselines():
    import pandas as pd

    from market_ai_hub.services.validation import (
        drift_baseline,
        last_price_naive,
        moving_average_baseline,
        naive_forecast_path,
    )

    s = pd.Series(100 + np.arange(50) * 0.5)
    assert last_price_naive(s, 5) == pytest.approx(s.iloc[-1])
    assert drift_baseline(s, 5) > s.iloc[-1]  # 正漂移
    assert moving_average_baseline(s, 5) < s.iloc[-1]  # MA 落後上升趨勢
    path = naive_forecast_path(s, 3)
    assert len(path["last_price"]) == 3
    assert path["last_price"] == [s.iloc[-1]] * 3


def test_evaluate_against_baselines_detects_worse_than_naive():
    import pandas as pd

    from market_ai_hub.services.validation import evaluate_against_baselines

    rng = np.random.default_rng(5)
    s = pd.Series(100 + np.cumsum(rng.normal(0, 1, 100)))
    actuals = s.iloc[-20:].to_numpy()
    prevs = s.iloc[-21:-1].to_numpy()
    # 模型預測等於未來真實值（作弊好模型）
    ev = evaluate_against_baselines("X", actuals, prevs, actuals.tolist(), steps=1)
    assert ev["status"] == "OK"
    assert ev["beats_naive_mae"] is True
    # 亂猜模型
    bad = rng.normal(s.mean(), s.std(), 20).tolist()
    ev2 = evaluate_against_baselines("X", actuals, prevs, bad, steps=1)
    assert ev2["beats_naive_mae"] is False


def test_backtest_record_null_not_zero():
    from market_ai_hub.schemas.backtest import BacktestRecord
    from datetime import datetime, timezone

    rec = BacktestRecord(
        model="x", model_version="1", data_version="d", symbol="S", period="1y",
        horizon="1d", feature_set="f", timestamp=datetime.now(timezone.utc),
        directional_accuracy=0.3, mae=0.1, rmse=0.2, pinball_loss=0.05,
        hit_rate=0.2, average_return=0.0, expectancy=0.0, profit_factor=1.0,
        max_drawdown=-0.1, sharpe=-1.0, sortino=0.0, n_samples=10,
    )
    d = rec.model_dump()
    # 沒有資料 → None，不是 0
    assert d["mase"] is None
    assert d["accuracy"] is None
    assert d["brier_score"] is None
