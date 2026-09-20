"""Phase 2Y-A — Yuanta Credential Store（Windows Credential Manager only，fail-closed）。

- backend：Windows Credential Manager（win32cred）。
- 非 Windows Credential Manager → FAIL CLOSED（不寫、不讀）。
- credential targets：MARKET_AI_HUB/YUANTA/FUTURES、MARKET_AI_HUB/YUANTA/SECURITIES。
- repository 永不保存 full account / password / PFX password / certificate secret。
"""
from __future__ import annotations

import ctypes
import logging
from dataclasses import dataclass

from market_ai_hub.integrations.yuanta.sanitizer import mask_account

log = logging.getLogger(__name__)

CRED_TARGET_FUTURES = "MARKET_AI_HUB/YUANTA/FUTURES"
CRED_TARGET_SECURITIES = "MARKET_AI_HUB/YUANTA/SECURITIES"
CRED_TARGET_LEGACY_LOGIN_ID = "MARKET_AI_HUB/YUANTA/LEGACY_LOGIN_ID"

# 既有 target（其他專案已設定於 Windows Credential Manager，整機共用）。
# 作為 fallback 重複使用，不複製密碼、不讀印內容。
CRED_FALLBACK_TARGETS = {
    "futures": ["QROS/Yuanta/FuturesReadonly"],
    "securities": ["QROS/Yuanta/SecuritiesReadonly"],
    "legacy_login_id": [],
}

CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2


class CredentialBackendError(Exception):
    """backend 非 Windows Credential Manager → fail closed。"""


@dataclass
class StoredCredential:
    target: str
    username: str
    password: str


def _require_wincred():
    """確認 backend 真的為 Windows Credential Manager，否則 fail closed。"""
    try:
        import win32cred  # noqa: F401
    except ImportError as e:
        raise CredentialBackendError(
            "win32cred unavailable; only Windows Credential Manager is supported (fail-closed)"
        ) from e
    if not hasattr(ctypes, "windll"):
        raise CredentialBackendError("not on Windows; credential backend unavailable (fail-closed)")


def write_credential(target: str, username: str, password: str) -> None:
    """寫入 Windows Credential Manager（不 echo / 不 log 內容）。"""
    _require_wincred()
    import win32cred

    cred = {
        "Type": CRED_TYPE_GENERIC,
        "TargetName": target,
        "UserName": username,
        "CredentialBlob": password,
        "Persist": CRED_PERSIST_LOCAL_MACHINE,
    }
    win32cred.CredWrite(cred)


def read_credential(target: str, fallback: tuple = ()) -> StoredCredential | None:
    _require_wincred()
    import win32cred

    for t in (target,) + tuple(fallback):
        try:
            c = win32cred.CredRead(t, CRED_TYPE_GENERIC)
        except Exception:
            continue
        if c is None:
            continue
        return StoredCredential(
            target=t,
            username=c.get("UserName") or "",
            password=c.get("CredentialBlob") or "",
        )
    return None


def read_profile_credential(profile: str) -> StoredCredential | None:
    """讀 futures/securities/legacy_login_id 憑證（primary target → 既有 fallback target）。"""
    if profile == "futures":
        return read_credential(CRED_TARGET_FUTURES, fallback=CRED_FALLBACK_TARGETS.get("futures", ()))
    if profile == "securities":
        return read_credential(CRED_TARGET_SECURITIES, fallback=CRED_FALLBACK_TARGETS.get("securities", ()))
    if profile == "legacy_login_id":
        return read_credential(CRED_TARGET_LEGACY_LOGIN_ID, fallback=CRED_FALLBACK_TARGETS.get("legacy_login_id", ()))
    return None


def delete_credential(target: str) -> bool:
    _require_wincred()
    import win32cred

    try:
        win32cred.CredDelete(target, CRED_TYPE_GENERIC)
        return True
    except Exception:
        return False


def status() -> dict:
    """唯讀狀態（不讀密碼內容）。"""
    _require_wincred()
    out = {}
    for label, target in (("futures", CRED_TARGET_FUTURES), ("securities", CRED_TARGET_SECURITIES)):
        c = read_credential(target, fallback=CRED_FALLBACK_TARGETS.get(label, ()))
        out[label] = {
            "configured": c is not None,
            "credential_target": c.target if c else target,
            "masked_account": mask_account(c.username) if c else None,
        }
    return out
