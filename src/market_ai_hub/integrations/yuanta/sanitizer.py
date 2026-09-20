"""Phase 2Y-A — 敏感欄位 sanitizer + masked account。"""
from __future__ import annotations


def mask_account(account: str) -> str:
    """遮罩帳號：只保留前 2 + 後 2，其餘 *。"""
    if not account:
        return ""
    if len(account) <= 4:
        return "*" * len(account)
    return account[:2] + "*" * (len(account) - 4) + account[-2:]


# LoginResult 可能包含的敏感欄位（全部不得輸出）
SENSITIVE_FIELDS = ("Account", "Name", "InvestorID", "SellerNo", "UserName", "Password")

# 允許回傳給 MCP/LLM 的欄位
ALLOWED_LOGIN_FIELDS = ("connected", "profile", "masked_account", "status_code",
                        "permission_state", "timestamp")


def sanitize_login_result(raw: dict) -> dict:
    """把元大 LoginResult 轉成安全 subset（只回允許欄位，遮罩帳號）。"""
    out = {
        "connected": bool(raw.get("connected", False)),
        "status_code": raw.get("status_code"),
        "permission_state": raw.get("permission_state", "UNKNOWN"),
        "timestamp": raw.get("timestamp"),
    }
    acct = raw.get("Account") or raw.get("account") or raw.get("UserName") or ""
    out["masked_account"] = mask_account(str(acct))
    out["profile"] = raw.get("profile", "")
    # Name / InvestorID / SellerNo 一律不回
    return out


def assert_no_sensitive(raw: dict) -> list[str]:
    """回傳 dict 中出現的敏感欄位名（用於測試/防護）。"""
    return [k for k in SENSITIVE_FIELDS if k in raw]
