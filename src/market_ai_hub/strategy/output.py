"""Phase 2F — 研究輸出（J）：TRADE_CANDIDATE / WAIT / NO_EDGE 三態皆合法。"""
from __future__ import annotations

from market_ai_hub.strategy.contract import RESEARCH_OUTPUTS, StrategyCandidate
from market_ai_hub.strategy.edge_store import HistoricalEdge
from market_ai_hub.strategy.overfitting import MIN_TRADE_COUNT, guard_edge


def classify_output(candidate: StrategyCandidate, edge: HistoricalEdge | None,
                    n_horizons_valid: int = 1, min_trades: int = MIN_TRADE_COUNT) -> str:
    """依 edge + candidate 產生合法研究輸出。

    - 無 edge 或樣本不足 → NO_EDGE
    - edge 但 regime/條件未對齊或有疑慮 → WAIT
    - edge 且通過 overfitting guard → TRADE_CANDIDATE
    """
    if edge is None or edge.status != "EDGE_FOUND":
        return "NO_EDGE"
    ok, _ = guard_edge(edge.sample_size or 0, edge.positive_rate,
                       n_horizons_valid=n_horizons_valid, min_trades=min_trades)
    if not ok:
        return "WAIT"
    return "TRADE_CANDIDATE"


def is_valid_output(x: str) -> bool:
    return x in RESEARCH_OUTPUTS
