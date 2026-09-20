"""Phase 2F — Walk-forward split（F）：TRAIN → VALIDATION → FROZEN TEST + rolling。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd


@dataclass(frozen=True)
class Window:
    train: tuple[str, str]
    validation: tuple[str, str]
    test: tuple[str, str]


def walk_forward_split(dates: list[str] | pd.DatetimeIndex, n_splits: int = 5,
                       train_ratio: float = 0.6, validation_ratio: float = 0.2) -> list[Window]:
    """rolling walk-forward：逐步前移的 (train, validation, frozen test) 三段。

    每個 split 的 test 都是「尚未見過」的未來區段（frozen）。
    資料不足 → 回傳較少 split。
    """
    d = pd.DatetimeIndex(sorted(pd.to_datetime(dates)))
    if len(d) == 0:
        return []
    n = len(d)
    step = max(1, int(n * (1 - train_ratio - validation_ratio) / n_splits))
    windows: list[Window] = []
    start = 0
    while True:
        train_end = start + int(n * train_ratio)
        val_end = train_end + int(n * validation_ratio)
        if val_end >= n:
            break
        train = (d[start].date().isoformat(), d[train_end - 1].date().isoformat())
        val = (d[train_end].date().isoformat(), d[val_end - 1].date().isoformat())
        test = (d[val_end].date().isoformat(), d[-1].date().isoformat())
        windows.append(Window(train, val, test))
        start += step
        if start + int(n * train_ratio) + int(n * validation_ratio) >= n:
            break
    return windows


def assert_frozen_test(w: Window) -> bool:
    """確認 test 區段完全在 validation 之後（無重疊）。"""
    return w.test[0] > w.validation[1] and w.validation[0] > w.train[1]
