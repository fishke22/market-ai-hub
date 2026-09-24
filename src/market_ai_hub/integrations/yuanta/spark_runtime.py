"""Phase 2Y-C — Yuanta SPARK runtime（官方 pythonnet 載入 + RealYuantaSparkClient）。

- 依官方 Python 範例：load("coreclr") → clr.AddReference("YuantaSparkAPI") →
  from YuantaOneAPI import (...) → YuantaSparkAPITrader() → OnResponse += handler。
- 不使用 Assembly.GetTypes() 完整 reflection（ReflectionTypeLoadException 不阻擋公開 API）。
- enum 值 runtime 反射：PROD=2 / UAT=1 / OSE=207（以 installed DLL 為準，不硬 cast 猜值）。
- Login() return True 只代表 accepted；真正結果來自 OnResponse 的 LoginResult.LoginStatus.MsgCode。
- 只允許 open_prod / login / logout / close / dispose；無 generic invoke、無 order method。
"""
from __future__ import annotations

import os
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

# 官方 enum 值（2026-09-19 由 installed DLL runtime 反射確認）
ENUM_ENVIRONMENT_PROD = 2
ENUM_ENVIRONMENT_UAT = 1
ENUM_MARKET_OSE = 207

# MsgCode 語義（官方）
MSG_SUCCESS = "0001"          # 亦見 "00001"
MSG_EXEC_FAILED = "0000"
MSG_PASSWORD_FROZEN = "0102"
MSG_PERMISSION_UNAVAILABLE = "0112"

PKG_ROOT = Path(__file__).resolve().parents[4] / "vendor" / "yuanta_spark" / "2.2026.0918.0" / "YuantaSparkAPI_win-x64_Python"


@dataclass
class LoginOutcome:
    msg_code: str | None = None
    count: int = 0
    received: bool = False


class SparkRuntime:
    """官方 pythonnet 載入 + YuantaSparkAPITrader 生命周期。"""

    def __init__(self, pkg_root: Path | None = None) -> None:
        self.pkg_root = pkg_root or PKG_ROOT
        self._api = None
        self._delegate = None
        self._login_event = threading.Event()
        self._system_event = threading.Event()
        self._login_outcome = LoginOutcome()
        self._callbacks = deque(maxlen=1000)
        self._system_messages = deque(maxlen=100)
        self.on_quote_callback = None  # optional callable(intMark, strIndex, objValue)
        self.enum_values: dict = {}
        self._load()

    def _load(self) -> None:
        from pythonnet import load

        load("coreclr")
        import clr

        sys.path.append(str(self.pkg_root))
        if sys.platform == "win32":
            self._dll_handle = os.add_dll_directory(str(self.pkg_root))
        clr.AddReference("YuantaSparkAPI")

        from YuantaOneAPI import (
            OnResponseEventHandler,
            YuantaSparkAPITrader,
            enumEnvironmentMode,
            enumLangType,
            enumLogType,
            enumMarketType,
            enumQuoteIndexType,
        )

        self.YuantaSparkAPITrader = YuantaSparkAPITrader
        self.OnResponseEventHandler = OnResponseEventHandler
        self.enumEnvironmentMode = enumEnvironmentMode
        self.enumLangType = enumLangType
        self.enumLogType = enumLogType
        self.enumMarketType = enumMarketType
        self.enumQuoteIndexType = enumQuoteIndexType

        self.enum_values = {
            "environment_prod": int(enumEnvironmentMode.PROD),
            "environment_uat": int(enumEnvironmentMode.UAT),
            "market_ose": int(enumMarketType.OSE),
        }

    def instantiate(self) -> None:
        self._api = self.YuantaSparkAPITrader()
        # 保留 delegate 強引用（避免 pythonnet 回收導致 callback 不觸發）
        self._delegate = self.OnResponseEventHandler(self._on_response)
        self._api.OnResponse += self._delegate
        # 最小 log（避免記 credential/response PII）
        lt = self.enumLogType
        if hasattr(lt, "NONE"):
            self._api.SetLogType(lt.NONE)
        else:
            self._api.SetLogType(lt.COMMON)

    def _on_response(self, intMark, dwIndex, strIndex, objHandle, objValue) -> None:
        try:
            type_name = type(objValue).__name__ if objValue is not None else "None"
            self._callbacks.append({"intMark": int(intMark), "strIndex": str(strIndex), "type": type_name})
            if int(intMark) == 0:
                # 系統回報（連線狀態）：記 message（masked），觸發 connected event
                try:
                    self._system_messages.append(str(objValue)[:200])
                except Exception:
                    self._system_messages.append("<unprintable>")
                self._system_event.set()
            if str(strIndex) == "Login":
                status = objValue.LoginStatus
                self._login_outcome = LoginOutcome(
                    msg_code=str(status.MsgCode),
                    count=int(status.Count),
                    received=True,
                )
                self._login_event.set()
            elif self.on_quote_callback is not None:
                # quote-only: bounded probe hook; no persistent stream
                self.on_quote_callback(int(intMark), str(strIndex), objValue)
        except Exception:
            self._login_event.set()

    def wait_connected(self, timeout: float = 15.0) -> bool:
        """等 Open 後的系統/連線回報（intMark=0）。首次連線需 ~1-12s。"""
        return self._system_event.wait(timeout)

    def system_messages(self) -> list[str]:
        return list(self._system_messages)

    def callback_diagnostics(self) -> list[dict]:
        """回呼記錄（無 PII：只 intMark / strIndex / type 名）。"""
        return list(self._callbacks)

    # --- quote-only 公開方法（無 order / 無 generic invoke）---
    def open_prod(self) -> None:
        self._api.Open(self.enumEnvironmentMode.PROD)

    def pump(self, seconds: float) -> None:
        """Bounded wait so CLR event-thread callbacks can fire (no background stream)."""
        time.sleep(max(0.0, float(seconds)))

    def enum_quote_index_default(self):
        """Default quote index flag (成交/總覽) from the installed enum."""
        et = getattr(self, "enumQuoteIndexType", None)
        if et is None:
            return None
        try:
            for name in ("成交", "總覽"):
                if hasattr(et, name):
                    return getattr(et, name)
        except Exception:
            pass
        try:
            return et(0)
        except Exception:
            return None

    def login(self, account: str, password: str) -> bool:
        """Login() 回傳 True 只代表 accepted；真正結果來自 OnResponse。"""
        self._login_outcome = LoginOutcome()
        self._login_event.clear()
        return bool(self._api.Login(account, password))

    def wait_login(self, timeout: float = 20.0) -> LoginOutcome:
        self._login_event.wait(timeout)
        return self._login_outcome

    def logout(self) -> None:
        if self._api is not None:
            self._api.LogOut()

    def close(self) -> None:
        if self._api is not None:
            self._api.Close()

    def dispose(self) -> None:
        if self._api is not None:
            self._api.Dispose()
            self._api = None

    def cleanup(self) -> None:
        """finally：logout → close → dispose，不留背景 connection。"""
        for fn in (self.logout, self.close, self.dispose):
            try:
                fn()
            except Exception:
                pass
