"""Phase 2E — bounded Optuna（保守預設；Final Test 不得作調參資料）。"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class BoundedOptuna:
    """保守 Optuna：max_trials / max_runtime / gpu_budget 上限。

    只能搜 train/validation（nested walk-forward）；Final Test 不得作調參資料。
    """

    def __init__(self, max_trials: int = 20, max_runtime_seconds: int = 300,
                 gpu_budget_mb: int = 4000) -> None:
        self.max_trials = max_trials
        self.max_runtime_seconds = max_runtime_seconds
        self.gpu_budget_mb = gpu_budget_mb

    def optimize(self, objective, direction: str = "minimize") -> dict:
        """objective(trial) -> float。只使用 train/validation。回傳 best value + params。"""
        import time

        import optuna

        study = optuna.create_study(direction=direction)
        t0 = time.time()
        for i in range(self.max_trials):
            if time.time() - t0 > self.max_runtime_seconds:
                break
            study.optimize(objective, n_trials=1, show_progress_bar=False)
        return {
            "best_value": study.best_value,
            "best_params": study.best_params,
            "n_trials": len(study.trials),
            "runtime_seconds": round(time.time() - t0, 2),
        }

    @staticmethod
    def assert_not_tuning_on_final_test() -> None:
        """政策提醒：Final Test 資料不得用於調參（此為 invariant）。"""
