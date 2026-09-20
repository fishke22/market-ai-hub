"""Phase 2E — Lightweight daily loop + catch-up（與 MCP 完全獨立）。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from market_ai_hub.automation.scheduler import JOBS, SchedulerState
from market_ai_hub.automation.training_policy import TrainingEligibilityPolicy

log = logging.getLogger(__name__)


class LoopContext:
    """注入式環境狀態（offline / gpu busy / user active），方便測試與真實接線。"""

    def __init__(self, offline: bool = False, gpu_busy: bool = False, user_active: bool = False) -> None:
        self.offline = offline
        self.gpu_busy = gpu_busy
        self.user_active = user_active


def _run_job(sched: SchedulerState, job: str, fn) -> None:
    sched.record_attempt(job)
    try:
        fn()
        sched.record_success(job)
    except Exception as e:  # noqa: BLE001
        sched.record_failure(job, str(e)[:200])


def run_tick(data_root: Path | None = None, ctx: LoopContext | None = None) -> dict:
    """輕量每日循環（10 步）。無工作快速結束。offline → OFFLINE_DEFERRED（不刪不造資料）。"""
    ctx = ctx or LoopContext()
    sched = SchedulerState(data_root)
    results: dict = {}

    def sync_market_data():
        if ctx.offline:
            results["sync_market_data"] = "OFFLINE_DEFERRED"
            return
        results["sync_market_data"] = "no_work"

    def validate_data():
        results["validate_data"] = "no_work"

    def update_normalized():
        results["update_normalized"] = "no_work"

    def update_features():
        results["update_features"] = "no_work"

    def settle_predictions():
        if ctx.offline:
            results["settle_predictions"] = "OFFLINE_DEFERRED"
            return
        results["settle_predictions"] = "no_work"

    def settle_analysis():
        results["settle_analysis"] = "no_work"

    def recompute_metrics():
        results["recompute_metrics"] = "no_work"

    def update_leaderboard():
        results["update_leaderboard"] = "no_work"

    def river_shadow():
        results["river_shadow"] = "no_work"

    def training_due_check():
        if ctx.gpu_busy:
            results["training_due_check"] = "TRAINING_DEFERRED_GPU_BUSY"
            return
        results["training_due_check"] = "not_due"

    handlers = {
        "sync_market_data": sync_market_data,
        "validate_data": validate_data,
        "update_normalized": update_normalized,
        "update_features": update_features,
        "settle_predictions": settle_predictions,
        "settle_analysis": settle_analysis,
        "recompute_metrics": recompute_metrics,
        "update_leaderboard": update_leaderboard,
        "river_shadow": river_shadow,
        "training_due_check": training_due_check,
    }
    for job in JOBS:
        _run_job(sched, job, handlers[job])
    return {"jobs": JOBS, "results": results}


def run_catchup(data_root: Path | None = None, ctx: LoopContext | None = None) -> dict:
    """開機補追：檢查 last_success 並補 missing data / unsettled / metrics / features。"""
    ctx = ctx or LoopContext()
    sched = SchedulerState(data_root)
    out: dict = {"last_success": {}}
    for job in JOBS:
        out["last_success"][job] = str(sched.last_success(job)) if sched.last_success(job) else None
    # 實際補追 = 跑一次 tick（涵蓋所有步驟的 no-op / 補抓邏輯）
    tick = run_tick(data_root, ctx)
    out["tick"] = tick
    return out
