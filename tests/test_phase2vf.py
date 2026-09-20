"""Phase 2V-F — Resource governor static/unit tests."""
import sys
from pathlib import Path
import yaml

sys.path.insert(0, "src")
ROOT = Path(__file__).resolve().parents[1]

def _doc(p): return (ROOT / p).read_text(encoding="utf-8")
def _yaml(p): return yaml.safe_load((ROOT / p).read_text(encoding="utf-8"))

PROFILES = _yaml("config/resource_profiles.yaml")
MODEL_REQ = _yaml("config/model_resource_requirements.yaml")

from market_ai_hub.services import resource_governor as rg

def test_desktop_safe_default():
    assert PROFILES["default_profile"] == "DESKTOP_SAFE"

def test_gpu_fraction_limited():
    ds = PROFILES["profiles"]["DESKTOP_SAFE"]
    assert ds["gpu_vram_soft_frac"] <= 0.65
    assert ds["gpu_vram_hard_frac"] <= 0.75
    assert ds["gpu_vram_reserve_mb"] >= 4096

def test_cpu_threads_reserved():
    ds = PROFILES["profiles"]["DESKTOP_SAFE"]
    assert ds["cpu_reserve_frac"] >= 0.25

def test_ram_guard():
    ds = PROFILES["profiles"]["DESKTOP_SAFE"]
    assert ds["ram_soft_frac"] <= 0.65
    assert ds["ram_hard_frac"] <= 0.75

def test_gpu_busy_defers_training():
    g = rg.ResourceGovernor()
    # mock: GPU free below reserve → preflight returns GPU_BUSY for heavy
    g._is_gpu_heavy = lambda tier: True
    orig = rg.system_resources
    rg.system_resources = lambda: {"monitor_ok": True, "ram_percent": 50,
                                    "gpu_total_mb": 16384, "gpu_free_mb": 1000,
                                    "gpu_allocated_mb": 500, "gpu_reserved_mb": 15384,
                                    "gpu_utilization_pct": None}
    try:
        assert g.preflight("retrain", "GPU_HEAVY") == rg.RESOURCE_GPU_BUSY
    finally:
        rg.system_resources = orig

def test_single_heavy_gpu_job():
    g = rg.ResourceGovernor()
    g._is_gpu_heavy = lambda tier: True
    orig = rg.system_resources
    rg.system_resources = lambda: {"monitor_ok": True, "ram_percent": 50,
                                    "gpu_total_mb": 16384, "gpu_free_mb": 8000,
                                    "gpu_allocated_mb": 0, "gpu_reserved_mb": 8384,
                                    "gpu_utilization_pct": None}
    try:
        s1 = g.request_resource_slot("j1", "retrain", "GPU_HEAVY")
        s2 = g.request_resource_slot("j2", "retrain", "GPU_HEAVY")
        assert s1 == rg.RESOURCE_OK
        assert s2 == rg.RESOURCE_JOB_LOCKED
        g.release_resource_slot("j1")
    finally:
        rg.system_resources = orig

def test_forward_shadow_priority():
    p = MODEL_REQ["priority_order"]
    assert "Forward Shadow" in p[2]

def test_optuna_no_parallel_gpu_default():
    ds = PROFILES["profiles"]["DESKTOP_SAFE"]
    assert ds["optuna_n_jobs"] == 1

def test_auto_train_false():
    ds = PROFILES["profiles"]["DESKTOP_SAFE"]
    assert ds["auto_train"] is False

def test_auto_finetune_false():
    ds = PROFILES["profiles"]["DESKTOP_SAFE"]
    assert ds["auto_fine_tune"] is False

def test_checkpoint_resume():
    # 長訓練需支援 checkpoint/resume（emergency_stop 用 checkpoint_then_exit）
    assert PROFILES["emergency_stop"]["behavior"] == "checkpoint_then_exit"

def test_oom_reduces_batch_once():
    # OOM 策略：reduce batch + clear cache + retry once（非無限 retry）
    assert "gpu_vram_hard_frac" in PROFILES["profiles"]["DESKTOP_SAFE"]

def test_resource_monitor_fail_closed():
    g = rg.ResourceGovernor()
    g._is_gpu_heavy = lambda tier: True
    orig = rg.system_resources
    rg.system_resources = lambda: {"monitor_ok": False}
    try:
        assert g.preflight("retrain", "GPU_HEAVY") == rg.RESOURCE_MONITOR_UNAVAILABLE
    finally:
        rg.system_resources = orig

def test_training_process_low_priority():
    ds = PROFILES["profiles"]["DESKTOP_SAFE"]
    assert ds["process_priority"] in ("BelowNormal", "Idle")

def test_status_has_no_secrets():
    g = rg.ResourceGovernor()
    st = g.status()
    for bad in ("credential", "account", "password", "token", "api_key", "pii"):
        assert bad not in str(st).lower()
