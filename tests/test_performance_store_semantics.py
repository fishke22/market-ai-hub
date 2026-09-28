from __future__ import annotations

from datetime import datetime, timezone

import duckdb

from market_ai_hub.schemas.backtest import BacktestRecord
from market_ai_hub.storage.performance import PerformanceStore


def _legacy_v2_table(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(path)) as con:
        con.execute(
            """
            CREATE TABLE backtests_v2 (
                model VARCHAR, model_version VARCHAR, data_version VARCHAR,
                symbol VARCHAR, period VARCHAR, horizon VARCHAR, feature_set VARCHAR,
                timestamp TIMESTAMP,
                directional_accuracy DOUBLE, mae DOUBLE, rmse DOUBLE, pinball_loss DOUBLE,
                brier_score DOUBLE,
                hit_rate DOUBLE, average_return DOUBLE, expectancy DOUBLE,
                profit_factor DOUBLE, max_drawdown DOUBLE, sharpe DOUBLE, sortino DOUBLE,
                n_samples BIGINT,
                task_type VARCHAR, classes VARCHAR, flat_threshold DOUBLE,
                accuracy DOUBLE, balanced_accuracy DOUBLE, macro_f1 DOUBLE, mcc DOUBLE, mase DOUBLE,
                class_distribution VARCHAR,
                uniform_random_baseline_accuracy DOUBLE, majority_class_baseline_accuracy DOUBLE,
                baseline_threshold DOUBLE, beats_majority_baseline BOOLEAN,
                engineering_status VARCHAR, predictive_validation_status VARCHAR,
                eligible_for_direction_vote BOOLEAN,
                baseline_results VARCHAR, sample_size BIGINT, date_range VARCHAR
            )
            """
        )


def test_performance_store_additive_migration_preserves_legacy_table(tmp_path):
    store = PerformanceStore(root=tmp_path)
    _legacy_v2_table(store.db_path)

    rec = BacktestRecord(
        model="lightgbm",
        model_version="3",
        data_version="TAIWAN_STOCK_REFERENCE_RESET_CONTINUITY_V1",
        symbol="3706.TW",
        period="1y",
        horizon="1d",
        feature_set="base-v1",
        timestamp=datetime.now(timezone.utc),
        directional_accuracy=0.4,
        mae=None,
        rmse=None,
        pinball_loss=None,
        hit_rate=0.5,
        average_return=0.001,
        expectancy=0.002,
        profit_factor=1.1,
        max_drawdown=-0.1,
        sharpe=0.2,
        sortino=0.3,
        n_samples=20,
        task_type="classification",
        classes=[-1, 0, 1],
        flat_threshold=0.005,
        accuracy=0.4,
        balanced_accuracy=0.36,
        macro_f1=0.35,
        mcc=0.02,
        majority_class=0,
        majority_class_train_prevalence=0.55,
        uniform_random_baseline_accuracy=1 / 3,
        uniform_random_baseline_balanced_accuracy=1 / 3,
        majority_class_baseline_accuracy=0.5,
        majority_class_baseline_balanced_accuracy=1 / 3,
        majority_class_baseline_macro_f1=0.22,
        baseline_threshold=1 / 3,
        baseline_metric="accuracy+balanced_accuracy+macro_f1",
        baseline_semantics="FOLD_LOCAL_TRAIN_MAJORITY_SAME_OOS_ORIGINS_V2",
        beats_majority_baseline=False,
        economic_metrics_status="GROSS_REALIZED_RETURN_DIAGNOSTIC_NO_COSTS",
        economic_return_semantics="POSITION_TIMES_REALIZED_NEXT_BAR_RETURN",
        transaction_costs_included=False,
        n_active_trades=12,
        dataset_semantics="TAIWAN_STOCK_REFERENCE_RESET_CONTINUITY_V1",
        adjustment_semantics="FORWARD_EFFECTIVE_DATE_REFERENCE_RESET_V1",
        source_semantics="RAW_DAILY_PLUS_FINMIND_REFERENCE_EVENTS_V1",
        engineering_status="PASS",
        predictive_validation_status="DEGRADED",
        eligible_for_direction_vote=False,
        sample_size=20,
        date_range={"start": "2026-01-01", "end": "2026-09-01"},
    )

    store.save(rec)
    latest = store.latest_by_model()["lightgbm"]

    assert latest["mae"] is None
    assert latest["rmse"] is None
    assert latest["baseline_semantics"] == "FOLD_LOCAL_TRAIN_MAJORITY_SAME_OOS_ORIGINS_V2"
    assert latest["economic_metrics_status"] == "GROSS_REALIZED_RETURN_DIAGNOSTIC_NO_COSTS"
    assert latest["transaction_costs_included"] is False
    assert latest["dataset_semantics"] == "TAIWAN_STOCK_REFERENCE_RESET_CONTINUITY_V1"
