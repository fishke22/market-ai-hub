"""Phase 2F — Strategy Search（C）：可解釋條件規則 → forward returns distribution。

先從簡單可解釋 rule：forecast direction / strength / trend / risk / rates / JPY / event。
不做複雜 RL。找「多窗口仍成立」的 rule。
"""
from __future__ import annotations

import itertools

import pandas as pd

from market_ai_hub.strategy.edge_store import HistoricalEdge, compute_edge


def search_edges(dataset: pd.DataFrame, market: str, instrument: str,
                 horizons: tuple = ("fwd_1d", "fwd_2d", "fwd_5d", "fwd_10d"),
                 condition_cols: tuple = ("direction", "trend_regime", "risk_regime",
                                          "rates_regime", "fx_regime", "event_state"),
                 min_sample: int = 30) -> list[HistoricalEdge]:
    """對 dataset 的每個 (horizon × 單一條件值) 組合計算 Edge。回傳 sorted by status 優先。

    單一條件值（depth-1）先找穩定 rule；depth-2+ 由呼叫方自行組合。
    """
    edges: list[HistoricalEdge] = []
    for h in horizons:
        if h not in dataset.columns:
            continue
        for col in condition_cols:
            if col not in dataset.columns:
                continue
            for val in dataset[col].dropna().unique():
                mask = dataset[col] == val
                sub = dataset.loc[mask, h].dropna()
                if len(sub) < min_sample:
                    continue
                e = compute_edge(sub, market=market, instrument=instrument, horizon=h,
                                 conditions={col: str(val)}, min_sample=min_sample)
                edges.append(e)
    order = {"EDGE_FOUND": 0, "NO_EDGE": 1, "INSUFFICIENT_EVIDENCE": 2}
    return sorted(edges, key=lambda e: (order[e.status], -(e.sample_size or 0)))


def conditional_returns(dataset: pd.DataFrame, conditions: dict[str, str],
                        horizon: str = "fwd_1d") -> pd.Series:
    """依 conditions（多欄位 AND）篩選，回傳該 horizon 的 forward returns。"""
    mask = pd.Series(True, index=dataset.index)
    for col, val in conditions.items():
        if col not in dataset.columns:
            mask &= False
        else:
            mask &= dataset[col] == val
    return dataset.loc[mask, horizon].dropna()


def search_condition_combos(dataset: pd.DataFrame, market: str, instrument: str,
                            horizon: str = "fwd_1d",
                            base_cols: tuple = ("trend_regime", "risk_regime", "fx_regime"),
                            max_depth: int = 3, min_sample: int = 30) -> list[HistoricalEdge]:
    """深度 1~max_depth 條件組合搜尋（可解釋、AND 組合）。"""
    edges: list[HistoricalEdge] = []
    present = [c for c in base_cols if c in dataset.columns]
    for depth in range(1, max_depth + 1):
        for combo in itertools.combinations(present, depth):
            for vals in itertools.product(*(dataset[c].dropna().unique() for c in combo)):
                cond = dict(zip(combo, (str(v) for v in vals)))
                r = conditional_returns(dataset, cond, horizon)
                if len(r) < min_sample:
                    continue
                e = compute_edge(r, market=market, instrument=instrument, horizon=horizon,
                                 conditions=cond, min_sample=min_sample)
                edges.append(e)
    order = {"EDGE_FOUND": 0, "NO_EDGE": 1, "INSUFFICIENT_EVIDENCE": 2}
    return sorted(edges, key=lambda e: (order[e.status], -(e.sample_size or 0)))


def stable_across_horizons(edges: list[HistoricalEdge], min_horizons: int = 2) -> list[dict]:
    """找「多窗口仍成立」的 rule：同 conditions 在 ≥ min_horizons 個 horizon 皆 EDGE_FOUND。"""
    by_cond: dict[str, list[HistoricalEdge]] = {}
    for e in edges:
        if e.status != "EDGE_FOUND":
            continue
        key = json_safe(e.conditions)
        by_cond.setdefault(key, []).append(e)
    out = []
    for key, es in by_cond.items():
        horizons = {e.horizon for e in es}
        if len(horizons) >= min_horizons:
            out.append({"conditions": json_load(key), "horizons": sorted(horizons),
                        "n_horizons": len(horizons), "min_sample": min(e.sample_size or 0 for e in es)})
    return sorted(out, key=lambda x: (-x["n_horizons"], -x["min_sample"]))


def json_safe(d: dict) -> str:
    return ",".join(f"{k}={v}" for k, v in sorted(d.items()))


def json_load(s: str) -> dict:
    return dict(part.split("=", 1) for part in s.split(",") if part)
