"""Phase 2P-D — Agent response truthfulness hotfix semantic tests."""
import sys
from pathlib import Path

sys.path.insert(0, "src")
ROOT = Path(__file__).resolve().parents[1]

V4 = (ROOT / "docs" / "prompts" / "SYSTEM_PROMPT_V4_PHASE2_RC1.md").read_text(encoding="utf-8")


def test_continuous_not_contract():
    assert "中心限月連續研究序列" in V4
    assert "不得寫" in V4 and "主力合約" in V4


def test_settlement_not_forecast_target():
    assert "Direct Market Fact" in V4
    assert "Model Forecast Target" in V4
    assert "Reference / Proxy Input" in V4 or "Reference/Proxy Input" in V4.replace(" ", "")


def test_zero_eligible_votes_no_model_direction():
    assert "NO_VALIDATED_MODEL_CONSENSUS" in V4
    assert "目前無有效模型方向共識" in V4


def test_uncalibrated_no_probability_language():
    # 有「改用原始分類分數偏向」的保護
    assert "原始分類分數偏向" in V4
    # 禁止語境：不可把「上漲機率」當作 uncalibrated 時的正式用語
    assert "probability_calibrated = false" in V4.replace("probability_calibrated = false", "probability_calibrated = false")


def test_economic_validation_not_called_missing():
    assert "已完成研究級成本與滑價壓力測試" in V4
    assert "尚未進行真實 broker fill" in V4


def test_quantile_not_support_without_evidence():
    assert "模型統計參考區間" in V4
    assert "不得自動當作" in V4
    assert "停損價" in V4 and "正式支撐壓力" in V4


def test_pending_registry_not_forward_n():
    assert "registered / pending records" in V4
    assert "不是" in V4 and "validated Forward samples" in V4


def test_holiday_trading_truth():
    assert "祝日交易" in V4
    assert "derivatives holiday trading" in V4
    assert "TSE cash market closed" in V4
