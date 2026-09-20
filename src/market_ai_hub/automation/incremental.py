"""Phase 2E — Incremental download（missing-range detection / dedup / hash / atomic write）。"""
from __future__ import annotations

import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from market_ai_hub.automation.data_lake import content_hash


def missing_ranges(covered: tuple[str, str] | None, requested: tuple[str, str]) -> list[tuple[str, str]]:
    """回傳 requested 中「本地未覆蓋」的日期區段（YYYY-MM-DD）。

    covered=None 表示完全沒有 → 回整個 requested。
    """
    req_start = date.fromisoformat(requested[0])
    req_end = date.fromisoformat(requested[1])
    if covered is None:
        return [(requested[0], requested[1])]
    cov_start = date.fromisoformat(covered[0])
    cov_end = date.fromisoformat(covered[1])
    gaps: list[tuple[str, str]] = []
    if req_start < cov_start:
        gaps.append((requested[0], (cov_start - timedelta(days=1)).isoformat()))
    if req_end > cov_end:
        gaps.append(((cov_end + timedelta(days=1)).isoformat(), requested[1]))
    return gaps


def dedupe(df: pd.DataFrame, key_cols: list[str]) -> pd.DataFrame:
    """依 key_cols 去重（保留最後出現）。"""
    return df.drop_duplicates(subset=key_cols, keep="last").reset_index(drop=True)


def atomic_write(path: Path, data: bytes) -> None:
    """atomic write：寫 temp 再 rename，避免半寫入。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def dedupe_and_write(path: Path, df: pd.DataFrame, key_cols: list[str]) -> tuple[int, str]:
    """去重 + 若內容 hash 不變則不重寫；回傳 (row_count, hash)。"""
    df = dedupe(df, key_cols)
    payload = df.to_parquet(index=False)
    h = content_hash(payload)
    if path.exists():
        old = content_hash(path.read_bytes())
        if old == h:
            return len(df), h  # 內容相同，不重寫
    atomic_write(path, payload)
    return len(df), h
