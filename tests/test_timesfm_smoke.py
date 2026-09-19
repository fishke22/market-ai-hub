"""TimesFM-3 smoke（integration，模型快取後 ~數十秒）。

V1 remediation 修改：predict 回傳 per-step path；原 flat quantile dict 測試已更新。
"""
import numpy as np
import pytest

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def adapter():
    import torch

    from market_ai_hub.models.timesfm_model import TimesFM3Adapter

    a = TimesFM3Adapter(device="cuda" if torch.cuda.is_available() else "cpu")
    a.load()
    return a


def test_load(adapter):
    assert adapter._model is not None


def test_univariate_quantile_path(adapter):
    t = np.arange(0, 128)
    synthetic = np.sin(t / 8.0) * 10 + 100 + t * 0.05
    pred = adapter.predict(synthetic, horizon=7, quantiles=[0.1, 0.5, 0.9])
    path = pred["path"]
    assert set(path.keys()) == {"p10", "p50", "p90"}
    assert all(len(path[q]) == 7 for q in path)
    for i in range(7):
        assert path["p10"][i] <= path["p50"][i] <= path["p90"][i]


def test_multivariate(adapter):
    t = np.arange(0, 128)
    synthetic = np.sin(t / 8.0) * 10 + 100
    mv = np.stack([synthetic, synthetic * 0.5 + 50])
    out = adapter.predict_multivariate(mv, horizon=7)
    assert out.shape[-1] == 7


def test_past_only_covariates(adapter):
    t = np.arange(0, 128)
    synthetic = np.sin(t / 8.0) * 10 + 100
    cov = np.ones(128)
    pred = adapter.predict(synthetic, horizon=7, quantiles=[0.1, 0.5, 0.9], past_only_covariates=cov)
    assert "p50" in pred["path"]


def test_license_warning_present():
    from market_ai_hub.models.timesfm_model import LICENSE_TAG

    assert LICENSE_TAG == "TIMESFM3_NON_COMMERCIAL_ONLY"
