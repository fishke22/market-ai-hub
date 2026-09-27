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
_timesfm_research = None


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

            # This singleton is a user-facing serving path; TimesFM-3 weights are research-only.
            # The adapter purpose gate therefore blocks load fail-closed.
            _timesfm = TimesFM3Adapter(purpose="SERVING")
        return _timesfm


def get_timesfm_research(acknowledgement: str):
    """Explicit local personal-research singleton; never used by serving/ensemble."""
    global _timesfm_research
    from market_ai_hub.models.timesfm_model import MODEL_CACHE, TimesFM3Adapter
    from market_ai_hub.services.model_governance import (
        require_timesfm3_research_access,
    )

    # Revalidate explicit authorization on every call, including after the
    # singleton has already been initialized.
    require_timesfm3_research_access(
        acknowledgement,
        cache_dir=MODEL_CACHE,
    )
    with _lock:
        if _timesfm_research is None:
            _timesfm_research = TimesFM3Adapter(purpose="RESEARCH")
        return _timesfm_research
