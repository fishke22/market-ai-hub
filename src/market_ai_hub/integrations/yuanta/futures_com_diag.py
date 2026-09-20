"""Phase 2Y-D — Yuanta Futures COM diagnostic（只輸出 component/runtime/status，無 credential）。"""
from __future__ import annotations

import json
import platform
import sys

DIAG_PATH = "YUANTA_FUTURES_COM_DIAGNOSTIC.json"


def _com_registration() -> dict:
    import winreg

    clsid = "{8E7FB42A-1137-467E-98C6-830C9B02EA82}"
    info = {"registered_32bit": False, "inproc": "", "typelib": ""}
    try:
        k = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, f"CLSID\\{clsid}\\InprocServer32",
                           0, winreg.KEY_READ | winreg.KEY_WOW64_32KEY)
        info["inproc"] = winreg.QueryValue(k, None)
        info["registered_32bit"] = True
    except FileNotFoundError:
        pass
    try:
        k = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, f"CLSID\\{clsid}\\TypeLib",
                           0, winreg.KEY_READ | winreg.KEY_WOW64_32KEY)
        info["typelib"] = winreg.QueryValue(k, None)
    except FileNotFoundError:
        pass
    return info


def main() -> int:
    result = {
        "component": "YuantaQuote_v2.1.2.9.ocx",
        "progid": "YUANTAQUOTE.YuantaQuoteCtrl.1",
        "clsid": "{8E7FB42A-1137-467E-98C6-830C9B02EA82}",
        "version": "2.1.2.9",
        "architecture": "x86 (32-bit ActiveX OCX)",
        "threading_model": "Apartment (STA)",
        "python_bits": 64 if sys.maxsize > 2**32 else 32,
        "registration": _com_registration(),
        "interop_status": "READY_32BIT_SIDECAR" if sys.maxsize > 2**32 else "READY",
        "note": "32-bit OCX 需 32-bit Python sidecar (.venv-yuanta-futures-x86)；主環境為 64-bit",
    }
    with open(DIAG_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nwritten -> {DIAG_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
