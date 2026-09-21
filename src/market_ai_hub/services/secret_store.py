"""Phase 2Q-F.6 — central secret store（Windows Credential Manager 優先）。

Resolution priority：
1. Windows Credential Manager（pywin32 win32cred，target MARKET_AI_HUB/<NAME>）
2. process environment compatibility fallback

不得 log value / prefix / suffix / length / hash。只回 configured=true/false, source=WINCRED/ENV/NONE。
"""
from __future__ import annotations

import os

CRED_PREFIX = "MARKET_AI_HUB/"

# canonical env names（+ legacy alias）
CANONICAL_SECRETS = {
    "FRED_API_KEY": ["FRED_API_KEY"],
    "FINMIND_API_TOKEN": ["FINMIND_API_TOKEN", "FINMIND_TOKEN"],
}

# legacy alias → canonical
ALIASES = {"FINMIND_TOKEN": "FINMIND_API_TOKEN"}


def _canonical(name: str) -> str:
    return ALIASES.get(name, name)


def _wincred_get(name: str) -> str | None:
    try:
        import win32cred

        cred = win32cred.CredRead(CRED_PREFIX + name, win32cred.CRED_TYPE_GENERIC, 0)
        blob = cred.get("CredentialBlob")
        if blob is None:
            return None
        return blob.decode("utf-16-le") if isinstance(blob, (bytes, bytearray)) else str(blob)
    except Exception:
        return None


def _wincred_set(name: str, value: str) -> bool:
    try:
        import win32cred

        win32cred.CredWrite({
            "Type": win32cred.CRED_TYPE_GENERIC,
            "TargetName": CRED_PREFIX + name,
            "UserName": name,
            "CredentialBlob": value,
            "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE,
        }, 0)
        return True
    except Exception:
        return False


def _wincred_delete(name: str) -> bool:
    try:
        import win32cred

        win32cred.CredDelete(CRED_PREFIX + name, win32cred.CRED_TYPE_GENERIC, 0)
        return True
    except Exception:
        return False


def get_secret(name: str) -> str:
    """回 secret value（WinCred → env）。找不到 → ""。不得 log。"""
    name = _canonical(name)
    v = _wincred_get(name)
    if v:
        return v
    for env_name in CANONICAL_SECRETS.get(name, [name]):
        ev = os.environ.get(env_name)
        if ev:
            return ev
    return ""


def secret_status(name: str) -> dict:
    """只回 configured / source，不回 value（無 prefix/suffix/length/hash）。"""
    name = _canonical(name)
    if _wincred_get(name):
        return {"name": name, "configured": True, "source": "WINCRED"}
    for env_name in CANONICAL_SECRETS.get(name, [name]):
        if os.environ.get(env_name):
            return {"name": name, "configured": True, "source": "ENV"}
    return {"name": name, "configured": False, "source": "NONE"}


def set_secret(name: str, value: str) -> bool:
    return _wincred_set(name, value)


def delete_secret(name: str) -> bool:
    return _wincred_delete(name)


def has_wincred() -> bool:
    try:
        import win32cred  # noqa: F401

        return True
    except Exception:
        return False
