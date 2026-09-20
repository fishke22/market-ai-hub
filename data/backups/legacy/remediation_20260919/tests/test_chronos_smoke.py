"""Chronos-2 smoke（integration，模型快取後 ~數十秒）。"""
import numpy as np
import pytest

pytestmark = pytest.mark.integration


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


def test_synthetic_forecast_quantiles(adapter_cpu):
    t = np.arange(0, 128)
    synthetic = np.sin(t / 8.0) * 10 + 100 + t * 0.05
    pred = adapter_cpu.predict(synthetic, horizon=7, quantiles=[0.1, 0.5, 0.9])
    assert set(pred.keys()) == {"p10", "p50", "p90"}
    assert pred["p10"] <= pred["p50"] <= pred["p90"]
