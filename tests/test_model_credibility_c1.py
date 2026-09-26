"""C1 model-comparison correctness regressions."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from market_ai_hub.research.tournament.adapter import ForecastResult, ModelAdapter
from market_ai_hub.research.tournament.engine import ExamSpec, ModelRun, TournamentEngine


class _CompletePrice(ModelAdapter):
    name = "complete"
    task = "price"

    def forecast(self, df, steps):
        return ForecastResult(point=float(df["close"].iloc[-1]))


class _PartialPrice(ModelAdapter):
    name = "partial"
    task = "price"

    def forecast(self, df, steps):
        if len(df) % 2:
            return ForecastResult(point=None, warnings=["intentional abstention"])
        return ForecastResult(point=float(df["close"].iloc[-1]))


def _df(n=12):
    idx = pd.date_range("2026-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame({"timestamp_utc": idx, "close": np.arange(n, dtype=float) + 100.0})



def test_effective_sample_excludes_abstention_and_nonfinite():
    run = ModelRun(
        model="m",
        task="price",
        points=[100.0, None, float("nan")],
        p10=[None, None, None],
        p90=[None, None, None],
        directions=["up", "", ""],
        actuals=[101.0, 102.0, 103.0],
        origin_prices=[99.0, 101.0, 102.0],
        failures=0,
    )
    result = TournamentEngine()._summarize(run, 1)
    assert result["sample_size"] == 3
    assert result["effective_sample_size"] == 1
    assert result["abstention_count"] == 1
    assert result["nonfinite_count"] == 1
    assert result["coverage_rate"] == pytest.approx(1 / 3)
    assert result["mae"] == pytest.approx(1.0)
    assert np.isfinite(result["rmse"])


def test_pairwise_common_origins_reports_each_models_full_coverage():
    result = TournamentEngine().run(
        ExamSpec("X", "1d", "v1", "v1", min_train=4, n_origins=6),
        _df(),
        [_CompletePrice(), _PartialPrice()],
    )
    pair = result["pairwise_comparisons"][0]
    assert pair["model_a"] == "complete"
    assert pair["model_b"] == "partial"
    assert pair["common_origin_count"] < result["n_origins"]

    assert pair["model_a_coverage_rate"] == pytest.approx(1.0)
    assert pair["model_b_coverage_rate"] < 1.0
    assert pair["common_origin_coverage_rate"] == pair["model_b_coverage_rate"]
    assert pair["metric"] == "mae"
    assert pair["model_a_metric_common"] is not None
    assert pair["model_b_metric_common"] is not None
    assert len(pair["common_origin_indices"]) == pair["common_origin_count"]


def test_random_walk_respects_horizon_in_both_baseline_paths():
    from market_ai_hub.research.evaluation import random_walk
    from market_ai_hub.research.tournament.baselines import RandomWalk

    series = pd.Series([100.0, 101.0, 99.0, 103.0, 102.0, 105.0])
    one = random_walk(series, steps=1, seed=7)
    five = random_walk(series, steps=5, seed=7)
    assert five != pytest.approx(one)

    closes = series.copy()
    one_t = RandomWalk()._point(closes, 1)
    five_t = RandomWalk()._point(closes, 5)
    assert five_t != pytest.approx(one_t)


def test_classification_baseline_never_uses_test_answers_without_train_labels():
    from market_ai_hub.research.evaluation import classification_baselines, classification_metrics

    y_true = np.array([1, 1, 1, -1])
    bases = classification_baselines(y_true, train_labels=None)
    assert bases["majority_class"] is None

    metrics = classification_metrics(y_true, y_true, train_labels=None)
    assert metrics["majority_class_baseline_accuracy"] is None
    assert metrics["beats_majority_baseline"] is None



def test_rates_regime_uses_trailing_20_session_lookback():
    from market_ai_hub.regime.engine import MarketRegimeEngine

    idx = pd.date_range("2026-01-01", periods=30, freq="D", tz="UTC")
    us10 = np.r_[np.ones(10), np.ones(11) * 5.0, np.ones(9) * 2.0]
    panel = pd.DataFrame({"US10Y": us10, "US5Y": np.ones(30)}, index=idx)
    result = MarketRegimeEngine().compute(panel)["rates_regime"]

    assert result["status"] == "OK"
    assert result["label"] == "normal_rising"
    assert result["evidence"]["lookback_sessions"] == 20


def test_rates_regime_requires_aligned_21_observations():
    from market_ai_hub.regime.engine import MarketRegimeEngine

    idx = pd.date_range("2026-01-01", periods=25, freq="D", tz="UTC")
    panel = pd.DataFrame({"US10Y": np.arange(25, dtype=float), "US5Y": np.nan}, index=idx)
    panel.loc[idx[-10:], "US5Y"] = 1.0
    result = MarketRegimeEngine().compute(panel)["rates_regime"]
    assert result["status"] == "REGIME_EVIDENCE=INSUFFICIENT"
    assert result["sample_size"] == 10


def test_performance_store_persists_accounting_and_pairwise(tmp_path):
    from market_ai_hub.research.tournament.performance_store import PerformanceStore

    store = PerformanceStore(root=tmp_path)
    summary = {
        "model": "m1", "task": "price", "sample_size": 4, "effective_sample_size": 3,
        "failure_count": 0, "abstention_count": 1, "nonfinite_count": 0,
        "invalid_target_count": 0, "failure_rate": 0.0, "coverage_rate": 0.75,
        "mae": 1.0,
    }

    store.save("exam", "X", "1d", "normal", ("a", "b"), "r1", summary)
    rows = store.leaderboard(target="X", horizon="1d")
    assert rows[0]["accounting_schema_version"] == "C1.1"
    assert rows[0]["coverage_rate"] == pytest.approx(0.75)
    assert rows[0]["abstention_count"] == 1

    pair = {
        "model_a": "m1", "model_b": "m2", "task": "price",
        "common_origin_count": 2, "common_origin_coverage_rate": 0.5,
        "model_a_coverage_rate": 0.75, "model_b_coverage_rate": 0.5,
        "metric": "mae", "model_a_metric_common": 1.0,
        "model_b_metric_common": 1.5, "delta_a_minus_b": -0.5,
        "common_origin_indices": [4, 6],
    }
    store.save_pairwise(
        "exam", "X", "1d", "normal", ("a", "b"),
        {"m1": "r1", "m2": "r2"}, pair,
    )
    paired = store.pairwise(model_a="m1", model_b="m2")
    assert len(paired) == 1
    assert paired[0]["common_origin_count"] == 2
    assert paired[0]["common_origin_indices"] == [4, 6]


# ── C1-A addition: non-finite never enters aggregates / ranking / store ──
def _status_run(statuses, points, actuals=None, origin=None, task="price"):
    n = len(statuses)
    return ModelRun(
        model="m", task=task,
        points=list(points), p10=[None] * n, p90=[None] * n,
        directions=[""] * n,
        actuals=list(actuals if actuals is not None else [100.0 + i for i in range(n)]),
        origin_prices=list(origin if origin is not None else [99.0] * n),
        failures=sum(1 for x in statuses if x == "FAILED"),
        statuses=list(statuses),
    )


def test_five_case_accounting_keeps_every_attempt_visible():
    """1 valid + 1 explicit failure + 1 abstain + 1 NaN + 1 invalid target."""
    run = _status_run(
        ["VALID", "FAILED", "ABSTAINED", "NONFINITE", "INVALID_TARGET"],
        [101.0, None, None, float("nan"), None],
        actuals=[100.0, 101.0, 102.0, 103.0, 104.0],
    )
    r = TournamentEngine()._summarize(run, 1)
    assert r["sample_size"] == 5                     # attempted stays visible
    assert r["effective_sample_size"] == 1           # only the finite row is metric-eligible
    assert r["failure_count"] == 1
    assert r["abstention_count"] == 1
    assert r["nonfinite_count"] == 1
    assert r["invalid_target_count"] == 1
    assert r["coverage_rate"] == pytest.approx(0.2)
    assert r["mae"] == pytest.approx(1.0)            # only from the valid row


def test_engine_metrics_never_emit_nonfinite_values():
    """non-evaluable metrics are typed None, never NaN/Inf in the aggregate."""
    flat = _status_run(["VALID", "VALID"], [100.0, 100.0], actuals=[100.0, 100.0],
                       origin=[100.0, 100.0])
    mase = TournamentEngine()._summarize(flat, 1).get("mase")
    assert mase is None or np.isfinite(mase)         # naive_mae == 0 -> not evaluable

    dirs = _status_run(["VALID", "VALID", "VALID"], [None, None, None], task="direction")
    d = TournamentEngine()._summarize(dirs, 1)
    for key in ("balanced_accuracy", "macro_f1", "mcc"):
        assert d.get(key) is None or np.isfinite(d[key]), (key, d.get(key))


def test_insufficient_valid_samples_is_not_ranked():
    run = _status_run(["FAILED", "ABSTAINED", "FAILED"], [None, None, None])
    r = TournamentEngine()._summarize(run, 1)
    assert r["effective_sample_size"] == 0
    assert r["coverage_rate"] == pytest.approx(0.0)
    assert r.get("mae") is None and r.get("rmse") is None
    # the CLI ranking boundary must exclude it instead of inventing a score
    from market_ai_hub.research.tournament.cli import _best_baseline_and_model
    ranked = _best_baseline_and_model({run.model: r})
    assert ranked["best_model"] is None and ranked["best_baseline"] is None


def test_partial_coverage_cannot_win_best_model_summary():
    from market_ai_hub.research.tournament.cli import _best_baseline_and_model

    summaries = {
        "last_price_naive": {"model": "last_price_naive", "mae": 1.0, "coverage_rate": 1.0},
        "chronos-2": {"model": "chronos-2", "mae": 0.01, "coverage_rate": 0.5},
    }
    ranked = _best_baseline_and_model(summaries)
    assert ranked["best_baseline"] == "last_price_naive"
    assert ranked["best_model"] is None
    assert ranked["comparison_basis"] == "FULL_COVERAGE_ONLY"


def test_zero_mae_baseline_does_not_create_nonfinite_relative_delta():
    from market_ai_hub.research.tournament.cli import _best_baseline_and_model

    ranked = _best_baseline_and_model({
        "last_price_naive": {"model": "last_price_naive", "mae": 0.0, "coverage_rate": 1.0},
        "chronos-2": {"model": "chronos-2", "mae": 1.0, "coverage_rate": 1.0},
    })
    assert ranked["best_baseline_mae"] == 0.0
    assert ranked["model_vs_best_baseline_delta"] is None


def test_failed_adapter_is_counted_and_never_scored_end_to_end():
    class _Boom(ModelAdapter):
        name = "boom"
        task = "price"

        def forecast(self, df, steps):
            raise RuntimeError("intentional failure")

    result = TournamentEngine().run(
        ExamSpec("X", "1d", "v1", "v1", min_train=4, n_origins=6),
        _df(),
        [_CompletePrice(), _Boom()],
    )
    boom = result["summaries"]["boom"]
    assert boom["failure_count"] == boom["sample_size"] > 0
    assert boom["effective_sample_size"] == 0
    assert boom.get("mae") is None
    pair = result["pairwise_comparisons"][0]
    assert pair["common_origin_count"] == 0
    assert pair["model_a_metric_common"] is None and pair["model_b_metric_common"] is None
    assert pair["model_a_coverage_rate"] == pytest.approx(1.0)
    assert pair["model_b_coverage_rate"] == pytest.approx(0.0)


def test_store_rejects_nonfinite_metric_values(tmp_path):
    from market_ai_hub.research.tournament.performance_store import (
        NonFiniteMetricError, PerformanceStore,
    )

    store = PerformanceStore(root=tmp_path)
    base = {"model": "m1", "task": "price", "sample_size": 3, "effective_sample_size": 3,
            "failure_count": 0, "abstention_count": 0, "nonfinite_count": 0,
            "invalid_target_count": 0, "failure_rate": 0.0, "coverage_rate": 1.0}
    for field, value in (("mae", float("nan")), ("rmse", float("inf")),
                         ("mase", float("-inf")), ("pinball_loss", float("nan"))):
        with pytest.raises(NonFiniteMetricError) as exc:
            store.save("exam", "X", "1d", "normal", ("a", "b"), "r1", {**base, field: value})
        assert "BLOCKED_NONFINITE_METRIC" in str(exc.value)
        assert field in str(exc.value)
    # nothing polluted the leaderboard
    assert store.leaderboard(target="X", horizon="1d") == []


def test_store_rejects_nonfinite_pairwise_metrics(tmp_path):
    from market_ai_hub.research.tournament.performance_store import (
        NonFiniteMetricError, PerformanceStore,
    )

    store = PerformanceStore(root=tmp_path)
    pair = {"model_a": "a", "model_b": "b", "metric": "mae", "common_origin_count": 2,
            "common_origin_indices": [1, 2], "model_a_metric_common": float("nan"),
            "model_b_metric_common": 1.0, "delta_a_minus_b": float("inf")}
    with pytest.raises(NonFiniteMetricError):
        store.save_pairwise("exam", "X", "1d", "normal", ("s", "e"), {"a": "r1", "b": "r2"}, pair)
    assert store.pairwise(model_a="a", model_b="b") == []


def test_store_rejects_missing_c1_accounting(tmp_path):
    from market_ai_hub.research.tournament.performance_store import AccountingMismatchError, PerformanceStore

    store = PerformanceStore(root=tmp_path)
    incomplete = {"model": "m1", "task": "price", "sample_size": 2,
                  "effective_sample_size": 2, "failure_rate": 0.0, "coverage_rate": 1.0, "mae": 1.0}
    with pytest.raises(AccountingMismatchError) as exc:
        store.save("exam", "X", "1d", "normal", ("a", "b"), "r1", incomplete)
    assert "BLOCKED_ACCOUNTING_MISSING" in str(exc.value)
    assert store.leaderboard(target="X", horizon="1d") == []


def test_store_rejects_inflated_accounting(tmp_path):
    from market_ai_hub.research.tournament.performance_store import PerformanceStore

    store = PerformanceStore(root=tmp_path)
    bad = {"model": "m1", "task": "price", "sample_size": 2, "effective_sample_size": 2,
           "failure_count": 1, "abstention_count": 1, "nonfinite_count": 0,
           "invalid_target_count": 0, "failure_rate": 0.5, "coverage_rate": 1.0, "mae": 1.0}
    with pytest.raises(ValueError) as exc:
        store.save("exam", "X", "1d", "normal", ("a", "b"), "r1", bad)
    assert "BLOCKED_ACCOUNTING_MISMATCH" in str(exc.value)
    assert store.leaderboard(target="X", horizon="1d") == []


def test_pairwise_scope_is_constrainable(tmp_path):
    from market_ai_hub.research.tournament.performance_store import PerformanceStore

    store = PerformanceStore(root=tmp_path)
    pair = {"model_a": "a", "model_b": "b", "metric": "mae", "common_origin_count": 1,
            "common_origin_indices": [1], "model_a_metric_common": 1.0,
            "model_b_metric_common": 2.0, "delta_a_minus_b": -1.0}
    for target, horizon in (("X", "1d"), ("Y", "5d")):
        store.save_pairwise("exam", target, horizon, "normal", ("s", "e"),
                            {"a": "r1", "b": "r2"}, pair)
    assert len(store.pairwise(model_a="a", model_b="b")) == 2
    scoped = store.pairwise(model_a="a", model_b="b", target="X", horizon="1d")
    assert len(scoped) == 1
    assert (scoped[0]["target"], scoped[0]["horizon"]) == ("X", "1d")
    assert store.pairwise(model_a="a", model_b="b", target="Y", horizon="5d")[0]["target"] == "Y"


def test_leaderboard_isolates_legacy_accounting_schema(tmp_path):
    from market_ai_hub.research.tournament.performance_store import PerformanceStore

    store = PerformanceStore(root=tmp_path)
    store.init()
    with store._conn() as con:
        con.execute(
            "INSERT INTO results (exam_hash, model, target, horizon, mae) VALUES (?, ?, ?, ?, ?)",
            ["legacy", "old", "X", "1d", 0.01],
        )
    current = {"model": "new", "task": "price", "sample_size": 1, "effective_sample_size": 1,
               "failure_count": 0, "abstention_count": 0, "nonfinite_count": 0,
               "invalid_target_count": 0, "failure_rate": 0.0, "coverage_rate": 1.0, "mae": 1.0}
    store.save("current", "X", "1d", "normal", ("a", "b"), "r", current)
    assert [r["model"] for r in store.leaderboard(target="X", horizon="1d")] == ["new"]
    assert {r["model"] for r in store.leaderboard(target="X", horizon="1d",
                                                   accounting_schema_version=None)} == {"old", "new"}


def test_cli_run_persists_pairwise_and_compare_uses_common_origins(tmp_path, monkeypatch, capsys):
    from types import SimpleNamespace
    from market_ai_hub.research.tournament import cli, data_quality
    from market_ai_hub.research.tournament.performance_store import PerformanceStore

    store = PerformanceStore(root=tmp_path)
    summary = lambda name, mae, coverage: {
        "model": name, "task": "price", "sample_size": 2,
        "effective_sample_size": int(2 * coverage), "failure_count": 0,
        "abstention_count": 2 - int(2 * coverage), "nonfinite_count": 0,
        "invalid_target_count": 0, "failure_rate": 0.0, "coverage_rate": coverage, "mae": mae,
    }
    result = {
        "status": "OK", "target": "X", "horizon": "1d", "n_origins": 2,
        "summaries": {"m1": summary("m1", 1.0, 1.0), "m2": summary("m2", 0.5, 0.5)},
        "pairwise_comparisons": [{
            "model_a": "m1", "model_b": "m2", "task": "price", "common_origin_count": 1,
            "common_origin_coverage_rate": 0.5, "model_a_coverage_rate": 1.0,
            "model_b_coverage_rate": 0.5, "metric": "mae", "model_a_metric_common": 2.0,
            "model_b_metric_common": 0.5, "delta_a_minus_b": 1.5, "common_origin_indices": [4],
        }],
    }
    class Engine:
        def run(self, exam, df, adapters):
            return result
    class Validator:
        def validate(self, df):
            return {"status": "PASS", "evaluation_gate": "OPEN", "eligible_for_evaluation": True,
                    "reasons": [], "metrics": {"unique_price_count": 2, "price_std": 1.0}}

    monkeypatch.setattr(cli, "PerformanceStore", lambda: store)
    monkeypatch.setattr(cli, "TournamentEngine", Engine)
    monkeypatch.setattr(cli, "_fetch_frame", lambda target: _df())
    monkeypatch.setattr(cli, "build_adapters", lambda: [])
    monkeypatch.setattr(data_quality, "TargetDataQualityValidator", Validator)
    args = SimpleNamespace(targets="X", horizons="1d", min_train=4, n_origins=2)
    assert cli.cmd_run(args) == 0
    pair = store.pairwise(model_a="m1", model_b="m2", target="X", horizon="1d")
    assert len(pair) == 1 and pair[0]["common_origin_count"] == 1

    assert cli.cmd_compare(SimpleNamespace(model_a="m1", model_b="m2")) == 0
    output = capsys.readouterr().out
    assert "common_n=1" in output and "m1=2.0" in output and "m2=0.5" in output
    assert "full_coverage=1.0" in output and "full_coverage=0.5" in output
