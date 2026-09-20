"""Chronos-2 smoke（integration，模型快取後 ~數十秒）。

V1 remediation 修改：predict 回傳 per-step path（{"path": {"p10"/"p50"/"p90": [...]}}），
不再 horizon 平均。此檔案原先驗證「flat quantile dict」，已依新 API 更新。
"""
import numpy as np
import pytest

pytestmark = pytest.mark.optional_model


@pytest.fixture(scope="module")
def adapter_cpu():
    from market_ai_hub.models.chronos_model import ChronosAdapter

    a = ChronosAdapter(device="cpu")
    a.load()
    return a


def test_cpu_load(adapter_cpu):
    assert adapter_cpu._pipeline is not None


@pytest.mark.skipif(not __import__("torch").cuda.is_available(), reason="no CUDA")
def test_cuda_load():
    import torch

    from market_ai_hub.models.chronos_model import ChronosAdapter

    a = ChronosAdapter(device="cuda")
    a.load()
    assert a._pipeline is not None
    assert torch.cuda.is_available()


def test_synthetic_forecast_path_quantiles(adapter_cpu):
    t = np.arange(0, 128)
    synthetic = np.sin(t / 8.0) * 10 + 100 + t * 0.05
    pred = adapter_cpu.predict(synthetic, horizon=7, quantiles=[0.1, 0.5, 0.9])
    assert set(pred.keys()) == {"path"}
    path = pred["path"]
    assert set(path.keys()) == {"p10", "p50", "p90"}
    assert all(len(path[q]) == 7 for q in path)
    for i in range(7):
        assert path["p10"][i] <= path["p50"][i] <= path["p90"][i]
