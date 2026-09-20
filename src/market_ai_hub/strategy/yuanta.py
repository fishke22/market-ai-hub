"""Phase 2F — Yuanta 未來 placeholder（O）。

保留 YuantaQuoteOnlyGateway / Recorder contract / credential infrastructure，
但 realtime_recorder_enabled=false。本棒不要求長時間開機。
"""
from __future__ import annotations


class YuantaQuoteOnlyGateway:
    """唯讀行情 gateway placeholder（未來啟用；本棒不實作、不連線）。"""

    realtime_recorder_enabled = False
    quote_only = True  # 無下單能力

    def __init__(self) -> None:
        self.credential = None  # 保留 credential infrastructure 佔位

    def is_realtime_recorder_enabled(self) -> bool:
        return self.realtime_recorder_enabled


class YuantaRecorderContract:
    """Tick/L2 Recorder contract placeholder。啟用後才需市場交易期間保持電腦開機。"""

    enabled = False
    note = "未來啟用 Tick/L2 Recorder 才需要市場交易期間保持電腦開機。"
