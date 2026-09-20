"""Phase 2Y-B — Yuanta SPARK auth policy（login 安全結構，無真實 SPARK interop 依賴）。

- 每次 auth_probe 最多 1 次 Login（禁止暴力 retry）。
- 官方 status 0102（密碼凍結/未啟用）、0112（API/function permission unavailable）→ 立即 ABORT。
- LoginResult 只 sanitize（不回 Name/InvestorID/SellerNo/full Account）。
"""
from __future__ import annotations

from dataclasses import dataclass

SPARK_STATUS_FROZEN = "0102"
SPARK_STATUS_PERMISSION_UNAVAILABLE = "0112"

ABORT_CODES = {SPARK_STATUS_FROZEN, SPARK_STATUS_PERMISSION_UNAVAILABLE}

MODE_QUOTE_ONLY = "QUOTE_ONLY"
ENV_FORMAL = "FORMAL"


@dataclass
class AuthProbeConfig:
    profile: str = "YUANTA FUTURES"
    environment: str = ENV_FORMAL
    mode: str = MODE_QUOTE_ONLY
    orders: str = "DISABLED"


def should_abort(status_code: str) -> bool:
    """0102 / 0112 → 立即 ABORT（不得 retry）。"""
    return str(status_code).strip() in ABORT_CODES


def classify_login_failure(status_code: str) -> str:
    if str(status_code).strip() == SPARK_STATUS_FROZEN:
        return "PASSWORD_FROZEN_OR_INACTIVE"
    if str(status_code).strip() == SPARK_STATUS_PERMISSION_UNAVAILABLE:
        return "API_PERMISSION_UNAVAILABLE"
    return "OTHER"


def sanitized_login_outcome(raw: dict) -> dict:
    """回傳 sanitized login 結果（只 mask + status，無 PII）。"""
    from market_ai_hub.integrations.yuanta.sanitizer import mask_account, sanitize_login_result

    s = sanitize_login_result(raw)
    s["status_code"] = raw.get("status_code")
    s["profile"] = raw.get("profile", "YUANTA FUTURES")
    s["mode"] = MODE_QUOTE_ONLY
    return s
