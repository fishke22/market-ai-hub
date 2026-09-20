"""Phase 2V-F — Compute Resource Governor（safe training scheduler）。

確保任何 model retraining / fine-tuning / feature rebuild / Optuna / GPU batch
不得吃滿整台電腦、造成 Windows 卡死或 GPU OOM / RAM swap 爆滿。

預設 INTERACTIVE_DESKTOP_PRIORITY：training 永遠是 background workload。
Heavy GPU jobs 同時間最多一個；monitor 讀取失敗 → fail closed（不啟動 heavy training）。
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

import yaml

from market_ai_hub.config.settings import project_root

log = logging.getLogger(__name__)

try:
    import psutil
    _HAS_PSUTIL = True
except Exception:  # pragma: no cover
    _HAS_PSUTIL = False

try:
    import torch
    _HAS_TORCH = True
except Exception:  # pragma: no cover
    _HAS_TORCH = False

# 統一資源狀態
RESOURCE_OK = "RESOURCE_OK"
RESOURCE_GPU_BUSY = "RESOURCE_GPU_BUSY"
RESOURCE_LOW_RAM = "RESOURCE_LOW_RAM"
RESOURCE_HIGH_CPU = "RESOURCE_HIGH_CPU"
RESOURCE_HIGH_TEMP = "RESOURCE_HIGH_TEMP"
RESOURCE_DESKTOP_ACTIVE = "RESOURCE_DESKTOP_ACTIVE"
RESOURCE_JOB_LOCKED = "RESOURCE_JOB_LOCKED"
RESOURCE_DEFERRED = "RESOURCE_DEFERRED"
RESOURCE_PAUSED = "RESOURCE_PAUSED"
RESOURCE_RESUMED = "RESOURCE_RESUMED"
RESOURCE_MONITOR_UNAVAILABLE = "RESOURCE_MONITOR_UNAVAILABLE"

PROFILES_PATH = project_root() / "config" / "resource_profiles.yaml"


def interactive_n_jobs() -> int:
    """interactive inference/fit 的 bounded thread 數（DESKTOP_SAFE）。禁止 n_jobs=-1 吃滿 CPU。"""
    cores = os.cpu_count() or 1
    reserve = max(1, int(cores * 0.25))
    return max(1, min(4, cores - reserve))


def load_profile(name: str | None = None) -> dict:
    data = yaml.safe_load(PROFILES_PATH.read_text(encoding="utf-8"))
    name = name or data.get("default_profile", "DESKTOP_SAFE")
    return data["profiles"][name], name


def _cuda_available() -> bool:
    return _HAS_TORCH and torch.cuda.is_available()


def system_resources() -> dict:
    """讀取系統資源（CPU/RAM/GPU）。任何讀取失敗 → 標 unavailable。"""
    out = {"monitor_ok": True}

    cpu = os.cpu_count() or 0
    out["cpu_logical_cores"] = cpu

    if _HAS_PSUTIL:
        vm = psutil.virtual_memory()
        out["ram_total_mb"] = round(vm.total / (1024 ** 2), 0)
        out["ram_used_mb"] = round(vm.used / (1024 ** 2), 0)
        out["ram_available_mb"] = round(vm.available / (1024 ** 2), 0)
        out["ram_percent"] = vm.percent
    else:
        out["monitor_ok"] = False
        out["ram_total_mb"] = None
        out["ram_percent"] = None

    if _cuda_available():
        props = torch.cuda.get_device_properties(0)
        out["gpu_total_mb"] = round(props.total_memory / (1024 ** 2), 0)
        out["gpu_allocated_mb"] = round(torch.cuda.memory_allocated() / (1024 ** 2), 0)
        out["gpu_reserved_mb"] = round(torch.cuda.memory_reserved() / (1024 ** 2), 0)
        out["gpu_free_mb"] = round((props.total_memory - torch.cuda.memory_reserved()) / (1024 ** 2), 0)
        out["gpu_utilization_pct"] = _gpu_utilization()
    else:
        out["gpu_total_mb"] = None
        out["gpu_free_mb"] = None
        out["gpu_utilization_pct"] = None

    return out


def _gpu_utilization() -> float | None:
    """best-effort GPU utilization；無 sensor → None（不 BLOCK）。"""
    return None  # 無 pynvml；utilization 非必須


class ResourceGovernor:
    """全域單例資源治理。request_resource_slot() 於任何 model load 前呼叫。"""

    def __init__(self, profile_name: str | None = None) -> None:
        self.profile, self.profile_name = load_profile(profile_name)
        self._lock = threading.Lock()
        self._heavy_job: dict | None = None
        self._queue: list[dict] = []
        # 2Q-F：status 輸出改到 DATA_ROOT/research_outputs/status/
        from market_ai_hub.config.runtime_paths import status_outputs_root

        self._status_path = status_outputs_root() / "RESOURCE_GOVERNOR_STATUS.json"
        self._usage_log = project_root() / "data" / "resource_usage_log.jsonl"

    # ── limits ──
    def gpu_vram_limits_mb(self) -> tuple[float | None, float | None]:
        res = system_resources()
        total = res.get("gpu_total_mb")
        if total is None:
            return None, None
        soft = total * self.profile["gpu_vram_soft_frac"]
        hard = total * self.profile["gpu_vram_hard_frac"]
        return round(soft, 0), round(hard, 0)

    def cpu_max_threads(self) -> int:
        cores = os.cpu_count() or 1
        reserve = max(1, int(cores * self.profile["cpu_reserve_frac"]))
        return max(1, cores - reserve)

    def ram_limits_mb(self) -> tuple[float | None, float | None]:
        res = system_resources()
        total = res.get("ram_total_mb")
        if total is None:
            return None, None
        return round(total * self.profile["ram_soft_frac"], 0), round(total * self.profile["ram_hard_frac"], 0)

    # ── preflight ──
    def preflight(self, job_type: str, model_tier: str) -> str:
        """訓練前檢查。回傳 resource state；非 OK 時 heavy job 不得啟動。"""
        res = system_resources()
        if not res["monitor_ok"]:
            return RESOURCE_MONITOR_UNAVAILABLE

        # RAM guard
        if res.get("ram_percent") is not None:
            hard = self.profile["ram_hard_frac"] * 100
            if res["ram_percent"] >= hard:
                return RESOURCE_LOW_RAM

        # GPU headroom（heavy job 才需 GPU）
        if self._is_gpu_heavy(model_tier):
            free = res.get("gpu_free_mb")
            reserve = self.profile["gpu_vram_reserve_mb"]
            if free is not None and free < reserve:
                return RESOURCE_GPU_BUSY

        # heavy job lock
        with self._lock:
            if self._heavy_job is not None:
                return RESOURCE_JOB_LOCKED

        return RESOURCE_OK

    def _is_gpu_heavy(self, model_tier: str) -> bool:
        req = yaml.safe_load((project_root() / "config" / "model_resource_requirements.yaml").read_text(encoding="utf-8"))
        tiers = req["model_resource_tiers"]
        return tiers.get(model_tier, {}).get("heavy", False)

    # ── slot ──
    def request_resource_slot(self, job_id: str, job_type: str, model_tier: str) -> str:
        """heavy job 取得 slot（同時間最多一個）。"""
        state = self.preflight(job_type, model_tier)
        if state != RESOURCE_OK:
            return state
        with self._lock:
            if self._heavy_job is not None:
                return RESOURCE_JOB_LOCKED
            self._heavy_job = {
                "job_id": job_id, "job_type": job_type, "model_tier": model_tier,
                "started_at": time.time(),
            }
        self._set_low_priority()
        self._log_usage("start", job_id, job_type, model_tier)
        return RESOURCE_OK

    def release_resource_slot(self, job_id: str) -> None:
        with self._lock:
            if self._heavy_job and self._heavy_job["job_id"] == job_id:
                self._log_usage("end", job_id)
                self._heavy_job = None
        if _cuda_available():
            torch.cuda.empty_cache()

    def _set_low_priority(self) -> None:
        """Windows training process → BelowNormal（不 High/Realtime）。"""
        if not _HAS_PSUTIL:
            return
        try:
            p = psutil.Process()
            if os.name == "nt":
                p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
            else:
                p.nice(10)
        except Exception as e:  # pragma: no cover
            log.warning("set priority failed: %s", e)

    # ── queue ──
    def enqueue(self, job_id: str, job_type: str, model_tier: str, priority: int = 5) -> None:
        with self._lock:
            self._queue.append({
                "job_id": job_id, "job_type": job_type, "model_tier": model_tier,
                "priority": priority, "created_at": time.time(), "status": "queued",
            })
            self._queue.sort(key=lambda x: x["priority"])

    def _log_usage(self, event: str, job_id: str, job_type: str = "", model_tier: str = "") -> None:
        """記錄 resource usage（不記 credential/account/PII）。"""
        try:
            res = system_resources()
            rec = {
                "ts": time.time(), "event": event, "job_id": job_id,
                "job_type": job_type, "model_tier": model_tier,
                "ram_percent": res.get("ram_percent"),
                "gpu_allocated_mb": res.get("gpu_allocated_mb"),
                "gpu_free_mb": res.get("gpu_free_mb"),
            }
            self._usage_log.parent.mkdir(parents=True, exist_ok=True)
            with open(self._usage_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
        except Exception as e:  # pragma: no cover
            log.warning("resource log failed: %s", e)

    # ── status ──
    def status(self) -> dict:
        res = system_resources()
        soft_vram, hard_vram = self.gpu_vram_limits_mb()
        with self._lock:
            active = dict(self._heavy_job) if self._heavy_job else None
            queued = list(self._queue)
        return {
            "profile": self.profile_name,
            "profile_label": self.profile.get("label", ""),
            "cpu_logical_cores": res.get("cpu_logical_cores"),
            "cpu_max_threads_for_training": self.cpu_max_threads(),
            "ram_percent": res.get("ram_percent"),
            "ram_soft_mb": self.ram_limits_mb()[0],
            "ram_hard_mb": self.ram_limits_mb()[1],
            "gpu_total_mb": res.get("gpu_total_mb"),
            "gpu_allocated_mb": res.get("gpu_allocated_mb"),
            "gpu_free_mb": res.get("gpu_free_mb"),
            "gpu_vram_soft_mb": soft_vram,
            "gpu_vram_hard_mb": hard_vram,
            "active_job": active,
            "queued_jobs": queued,
            "auto_train": self.profile.get("auto_train", False),
            "auto_fine_tune": self.profile.get("auto_fine_tune", False),
        }

    def write_status(self) -> None:
        self._status_path.parent.mkdir(parents=True, exist_ok=True)
        self._status_path.write_text(json.dumps(self.status(), indent=2, default=str), encoding="utf-8")


_GLOBAL_GOVERNOR: Optional[ResourceGovernor] = None
_GOV_LOCK = threading.Lock()


def get_governor() -> ResourceGovernor:
    global _GLOBAL_GOVERNOR
    with _GOV_LOCK:
        if _GLOBAL_GOVERNOR is None:
            _GLOBAL_GOVERNOR = ResourceGovernor()
        return _GLOBAL_GOVERNOR
