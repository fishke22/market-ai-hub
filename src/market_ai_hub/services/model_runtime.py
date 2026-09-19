"""Model runtime singletons（V1.1 runtime consistency）。

問題：gate evaluation / 每次 tool call 都 new adapter → 重複載入模型進 VRAM，
長期執行會累積 OOM → status 變 FAIL → ENGINEERING_GATE 掉到 PARTIAL。
修法：每個 process 只載入一次，之後全部共用（thread-safe enough for stdio single loop）。
"""
from __future__ import annotations

import logging
import threading

log = logging.getLogger(__name__)

_lock = threading.Lock()
_chronos = None
_timesfm = None


def get_chronos():
    global _chronos
    with _lock:
        if _chronos is None:
            from market_ai_hub.models.chronos_model import ChronosAdapter

            _chronos = ChronosAdapter()
        return _chronos


def get_timesfm():
    global _timesfm
    with _lock:
        if _timesfm is None:
            from market_ai_hub.models.timesfm_model import TimesFM3Adapter

            _timesfm = TimesFM3Adapter()
        return _timesfm
