"""Cloud P5 persistence/scheduling guards."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from market_ai_hub.research.accuracy_v2_p5_engine import precommit_p5_forward
from market_ai_hub.research.v2 import prediction_audit as PA
from scripts.run_accuracy_v2_p5_cloud_cycle import _seconds_until_today
from scripts.sync_accuracy_v2_p5_cloud_state import merge_cloud_p5_audit

ROOT = Path(__file__).resolve().parents[1]


def _series():
    idx = pd.date_range("2026-08-01", periods=56, freq="D", tz="UTC")
    return pd.Series(np.linspace(59000.0, 60000.0, len(idx)), index=idx, name="settlement")


def _meta():
    return {
        "status": "OK",
        "contract_month": "202610",
        "quote_code": "JNU2610",
        "sample_count": 56,
        "first_date": "2026-08-01",
        "latest_date": "2026-09-25",
        "latest_settlement": 60000.0,
        "source": "fixture",
        "series_semantics": "EXACT_CONTRACT",
        "price_semantics": "SETTLEMENT",
    }


def _receipts():
    return pd.DataFrame([{
        "contract_month": "202610",
        "date": "2026-09-25",
        "settlement": 60000.0,
        "_received_at": datetime(2026, 9, 28, 0, 4, tzinfo=timezone.utc),
        "source_hash": "refhash",
        "source_url": "https://example.invalid/ref",
        "_source_path": "fixture-ref",
    }])


def _robust():
    return {
        "status": "OK",
        "point_reference": {"price": 60000.0},
        "empirical_interval": {"status": "INSUFFICIENT_DEVELOPMENT_HISTORY"},
        "lightgbm_quantile_challenger": {
            "status": "INSUFFICIENT_DEVELOPMENT_HISTORY",
            "price_quantiles": {},
        },
    }


def test_cloud_workflow_is_public_only_and_has_primary_backup_schedule():
    text = (ROOT / ".github" / "workflows" / "p5-cloud-public-forward.yml").read_text(encoding="utf-8")
    assert 'cron: "40 7 * * 1-5"' in text
    assert 'cron: "15 8 * * 1-5"' in text
    assert text.count('timezone: "Asia/Taipei"') == 2
    assert "pull_request:" in text
    assert "workflow_dispatch:" in text
    assert "contents: read" in text
    assert "actions: read" in text
    assert "cancel-in-progress: false" in text
    assert "requirements-p5-cloud.txt" in text
    assert "p5-cloud-state" in text
    assert "github.event_name != 'pull_request'" in text
    assert "p5-cloud-pr-smoke-${{ github.run_id }}" in text
    assert 'MARKET_AI_DATA_ROOT: ${{ runner.temp }}' not in text
    assert 'MARKET_AI_DATA_ROOT=$RUNNER_TEMP/market-ai-p5-data' in text
    assert "Yuanta" not in text
    assert "secrets." not in text


def test_cloud_requirements_exclude_foundation_models_and_broker_sdk():
    text = (ROOT / "requirements-p5-cloud.txt").read_text(encoding="utf-8").lower()
    packages = {
        line.split("==", 1)[0].split("[", 1)[0].strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert "lightgbm" in packages
    assert "duckdb" in packages
    assert "torch" not in packages
    assert "chronos-forecasting" not in packages
    assert "timesfm" not in packages
    assert not any("yuanta" in package for package in packages)


def test_cloud_wait_uses_taipei_same_day_boundary():
    now = datetime(2026, 9, 29, 7, 45, tzinfo=ZoneInfo("Asia/Taipei"))
    target = datetime.strptime("08:01:00", "%H:%M:%S").time()
    assert _seconds_until_today(target, now=now) == 16 * 60
    late = datetime(2026, 9, 29, 8, 2, tzinfo=ZoneInfo("Asia/Taipei"))
    assert _seconds_until_today(target, now=late) == 0


def test_cloud_p5_merge_is_scope_limited_and_idempotent(tmp_path):
    cloud_path = tmp_path / "cloud.duckdb"
    local_path = tmp_path / "local.duckdb"
    cloud = PA.PredictionAuditDB(cloud_path)
    out = precommit_p5_forward(
        now=datetime(2026, 9, 28, 0, 6, tzinfo=timezone.utc),
        db=cloud,
        current_series=_series(),
        current_meta=_meta(),
        receipts=_receipts(),
        robust_analysis=_robust(),
    )
    assert out.status == "PRECOMMITTED"
    first = merge_cloud_p5_audit(cloud_path, local_path)
    second = merge_cloud_p5_audit(cloud_path, local_path)
    assert first["p5_predictions"] == 1
    assert second["p5_predictions"] == 1
    local = PA.PredictionAuditDB(local_path, read_only=True)
    assert local.list_prediction_ids() == [out.prediction_id]
    assert local.verify_prediction(out.prediction_id)


def test_cloud_sync_registration_is_evening_only_and_no_overwrite():
    text = (ROOT / "scripts" / "register_accuracy_v2_p5_cloud_sync_task.ps1").read_text(encoding="utf-8")
    assert 'planned_time = "19:05"' in text
    assert "-At 19:05" in text
    assert "local_audit_overwrite = $false" in text
    assert "broker_used = $false" in text
    assert "order_action = $false" in text
