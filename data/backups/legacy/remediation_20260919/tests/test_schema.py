from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from market_ai_hub.schemas.market_data import DataGrade, ForecastOutput, MarketBar


def test_market_bar_roundtrip():
    now = datetime.now(timezone.utc)
    bar = MarketBar(
        timestamp_utc=now,
        timestamp_local=now,
        symbol="^N225",
        open=1, high=2, low=0.5, close=1.5, volume=100,
        provider="yfinance", data_grade=DataGrade.RESEARCH_PROXY, retrieved_at=now,
    )
    assert bar.symbol == "^N225"
    assert bar.data_grade == DataGrade.RESEARCH_PROXY


def test_naive_datetime_rejected():
    with pytest.raises(ValidationError):
        MarketBar(
            timestamp_utc=datetime(2026, 1, 1),  # naive!
            timestamp_local=datetime(2026, 1, 1),
            symbol="X", open=1, high=2, low=0.5, close=1.5,
            provider="p", data_grade=DataGrade.DELAYED, retrieved_at=datetime(2026, 1, 1),
        )


def test_forecast_output_shape():
    fo = ForecastOutput(
        model="chronos-2", symbol="^N225", as_of=datetime.now(timezone.utc),
        horizon="1d", point_forecast=100.0, expected_return=0.01,
        quantiles={"p10": 99.0, "p50": 100.0, "p90": 101.0},
        direction="up", confidence=0.8, data_grade=DataGrade.RESEARCH_PROXY,
    )
    assert set(fo.quantiles.keys()) == {"p10", "p50", "p90"}
    assert fo.warnings == []
