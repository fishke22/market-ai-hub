"""Phase 2A MLflow 基礎 tracking（local file store，不啟動 server）。

保存：run_id / model / revision / dataset_version / feature_version / seed / config /
metrics / artifact reference。

禁止保存：broker account / password / secret / PII。
"""
from __future__ import annotations

import logging
from pathlib import Path

from market_ai_hub.config.settings import project_root

log = logging.getLogger(__name__)

# MLflow 3.x 棄用 filesystem backend，改用 sqlite backend（本地，不需 server）。
_TRACKING_DB = project_root() / "mlflow.db"
TRACKING_URI = "sqlite:///" + str(_TRACKING_DB).replace("\\", "/")


def set_tracking_uri(uri: str | None = None) -> None:
    import mlflow

    mlflow.set_tracking_uri(uri or TRACKING_URI)


def start_run(experiment: str, params: dict, metrics: dict | None = None,
              artifact_ref: str = "") -> dict:
    """啟動一個 MLflow run，記錄 params/metrics/artifact reference。回傳 run 摘要。"""
    import mlflow

    set_tracking_uri()
    mlflow.set_experiment(experiment)
    with mlflow.start_run() as run:
        for k, v in params.items():
            mlflow.log_param(k, v)
        for k, v in (metrics or {}).items():
            try:
                mlflow.log_metric(k, float(v))
            except (TypeError, ValueError):
                log.warning("skip non-numeric metric %s=%s", k, v)
        if artifact_ref:
            mlflow.set_tag("artifact_reference", artifact_ref)
        return {
            "run_id": run.info.run_id,
            "experiment": experiment,
            "tracking_uri": mlflow.get_tracking_uri(),
        }


def sanitize_params(params: dict) -> dict:
    """防止誤存敏感資訊：移除明顯的 secret / PII key。"""
    forbidden = ("token", "key", "secret", "password", "passwd", "credential", "api_key",
                 "authorization", "cookie", "account", "email", "pii")
    return {k: v for k, v in params.items() if not any(f in k.lower() for f in forbidden)}
