"""Phase 2Y-A — SafeYuantaLogger（禁止 log 敏感欄位）。"""
from __future__ import annotations

import logging
import re

from market_ai_hub.integrations.yuanta.sanitizer import mask_account

# 敏感 key = value 形式，值一律 REDACT
_SECRET_PATTERNS = [
    (re.compile(r"(?i)(password|passwd|pwd|credentialblob|pfx|certificate)\s*[:=]\s*\S+"), r"\1=<REDACTED>"),
    (re.compile(r"(?i)(account|username|investorid|sellerno|name)\s*[:=]\s*\S+"), r"\1=<REDACTED>"),
]


class SafeYuantaLogger:
    """元大專用 logger：只 log masked，不 log password/full account/InvestorID/Name。"""

    def __init__(self, name: str = "yuanta") -> None:
        self._log = logging.getLogger(name)

    def _redact(self, msg: str) -> str:
        for pat, repl in _SECRET_PATTERNS:
            msg = pat.sub(repl, msg)
        return msg

    def info(self, msg: str, **kw) -> None:
        self._log.info(self._redact(msg))

    def warning(self, msg: str, **kw) -> None:
        self._log.warning(self._redact(msg))

    def error(self, msg: str, **kw) -> None:
        self._log.error(self._redact(msg))

    def log_account(self, account: str) -> None:
        self._log.info("account=%s", mask_account(account))
