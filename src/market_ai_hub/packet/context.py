"""Phase 2I-A — Shared AnalysisExecutionContext（§3）。

同一次 get_analysis_packet：Feature/Regime/Model/Scenario/Edge 共用
同一 data snapshot、同一 information_cutoff、同一 feature snapshot，
禁止每層各自重新 fetch/normalize/算 features。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class AnalysisExecutionContext:
    def __init__(self, information_cutoff: datetime | None = None) -> None:
        self.information_cutoff = information_cutoff or datetime.now(timezone.utc)
        self.panel = None            # 共用 cross-asset panel（同一次分析只抓一次）
        self.coverage = None         # 共用 coverage summary
        self.regime = None           # 共用 regime 結果
        self._feature_snapshot = None

    def set_panel(self, panel) -> None:
        self.panel = panel

    def feature_snapshot(self) -> Any:
        """memoized feature snapshot：多層共用同一份，不重算。"""
        if self._feature_snapshot is None:
            self._feature_snapshot = {"cutoff": self.information_cutoff, "panel_hash": id(self.panel)}
        return self._feature_snapshot
