"""pytest conftest：sys.path + DEFAULT profile 的 runtime data isolation。

Phase 2Q-F.3 HIGH-2 remediation：default pytest 不得讀寫使用者真正 runtime data root。
session-scoped autouse fixture 把 MARKET_AI_DATA_ROOT 指到 session temp，
使所有 DuckDB / registry / cache / logs / validation / archive 都進 temp。
使用者若明確 export MARKET_AI_DATA_ROOT（如 private_data test）則尊重不覆寫。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _isolate_runtime_data_root(tmp_path_factory):
    if os.environ.get("MARKET_AI_DATA_ROOT"):
        yield  # 使用者明確指定（private_data / 手動）→ 尊重
        return
    tmp = tmp_path_factory.mktemp("market_ai_data")
    os.environ["MARKET_AI_DATA_ROOT"] = str(tmp)
    yield
