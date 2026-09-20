"""FinCast smoke（optional，integration）：隔離 venv subprocess bridge。"""
import pytest

from pathlib import Path
_REPO = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.optional_model


def test_status():
    from market_ai_hub.models.fincast_model import FinCastAdapter

    st = FinCastAdapter().status()
    assert st in ("ready", "unavailable", "not-installed")


@pytest.mark.skipif(
    not __import__("pathlib").Path(str(_REPO / ".venv-fincast" / "Scripts" / "python.exe")).exists(),
    reason="fincast venv not present",
)
def test_predict_bridge():
    import numpy as np

    from market_ai_hub.models.fincast_model import FinCastAdapter

    a = FinCastAdapter()
    if a.status() != "ready":
        pytest.skip("fincast checkpoint missing")
    x = np.sin(np.arange(128) / 8) * 10 + 100
    r = a.predict(x, horizon=7)
    assert len(r["point"]) == 7
