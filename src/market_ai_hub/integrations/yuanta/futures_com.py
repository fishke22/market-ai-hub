"""Phase 2Y-E — Yuanta Futures Quote COM client（quote-only，32-bit sidecar，STA + message pump）。

COM 元件：YUANTAQUOTE.YuantaQuoteCtrl.1（ActiveX OCX，32-bit，STA，需 window + message pump）。
登入：SetMktLogon(account, password, host, port, reqType, 0)（T 盤 80 / T+1 盤 82）。
行情：AddMktReg / DelMktReg。登入結果以事件 OnMktStatusChange 為準。

安全：quote-only（無 order/account/position/balance）；無 generic COM invoke；
password 只 process memory；STA + bounded message pump；CoUninitialize 於 finally。
"""
from __future__ import annotations

import ctypes
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

PROG_ID = "YUANTAQUOTE.YuantaQuoteCtrl.1"
CLSID_STR = "{8E7FB42A-1137-467E-98C6-830C9B02EA82}"
TYPELIB_STR = "{350F911B-4F62-42AF-BCD5-83B431A4BBDF}"
OCX_VERSION = "2.1.2.9"
QUOTE_HOST = "apiquote.yuantafutures.com.tw"
MKT_LOGON_T = (QUOTE_HOST, "80", 1)     # T 盤
MKT_LOGON_TP1 = (QUOTE_HOST, "82", 2)   # T+1 盤

# FuturesAuthState（§10）
STATE_NOT_STARTED = "NOT_STARTED"
STATE_CONNECTING = "CONNECTING"
STATE_LOGIN_REQUESTED = "LOGIN_REQUESTED"
STATE_AUTHENTICATED = "AUTHENTICATED"
STATE_FAILED = "FAILED"
STATE_TIMEOUT = "TIMEOUT"
STATE_DISCONNECTED = "DISCONNECTED"


def require_32bit() -> bool:
    return sys.maxsize <= 2**32


@dataclass
class FuturesAuthState:
    state: str = STATE_NOT_STARTED
    events: list[dict] = field(default_factory=list)


class YuantaFuturesQuoteClient:
    def __init__(self, message_timeout: float = 60.0) -> None:
        if not require_32bit():
            raise RuntimeError("Yuanta Futures COM OCX is 32-bit; run in .venv-yuanta-futures-x86")
        self.message_timeout = message_timeout
        self._quote = None
        self._events = None
        self._hwnd = None
        self._class_atom = None
        self._com_initialized = False
        self._auth_state = FuturesAuthState()
        self._event = threading.Event()

    # --- 事件 handler（登入結果在此）---
    # 官方 TLinkStatus 語義（Quote API 文件）：
    #   -2 = LinkFail（網路連線失敗）  -1 = LinkBroken  0 = Idle  1 = Connected  2 = LogonOK
    # 注意：status=-2 是「連線失敗」，不是 permission denied。
    # 只有 Msg[0]=='3' 才代表「無權限」（官方可驗證 code）。
    TLINK_STATUS = {-2: "LinkFail", -1: "LinkBroken", 0: "Idle", 1: "Connected", 2: "LogonOK"}

    @staticmethod
    def _decode_msg(msg) -> str:
        """元大 COM 回傳 Big5 中文，Python/comtypes 誤當 Latin-1 → 還原正確 Unicode。"""
        try:
            return str(msg).encode("latin-1", "replace").decode("big5", "replace")
        except Exception:
            return str(msg)

    @staticmethod
    def _message_category(message_code: str) -> str:
        if message_code == "3":
            return "PERMISSION_DENIED"
        if message_code == "0":
            return "OK"
        return "UNKNOWN"

    def OnMktStatusChange(self, this, Status, Msg, ReqType):
        raw_msg = self._decode_msg(Msg)
        msg_code = raw_msg[0] if raw_msg else ""
        self._auth_state.events.append({
            "req_type": int(ReqType),
            "status": int(Status),
            "status_label": self.TLINK_STATUS.get(int(Status), "UNKNOWN"),
            "message_code": msg_code,
            "message_category": self._message_category(msg_code),
            "sanitized_message": raw_msg[:200],
            "received_at": datetime.now(timezone.utc).isoformat(),
        })
        self._event.set()

    def OnRegError(self, this, symbol, updmode, ErrCode, ReqType):
        self._auth_state.events.append({"reg_error": int(ErrCode), "symbol": str(symbol)})

    def OnGetMktQuote(self, this, symbol, DisClosure, Duration, ReqType):
        self._auth_state.events.append({"event": "OnGetMktQuote", "symbol": str(symbol)})
        self._event.set()

    def OnGetMktData(self, this, PriType, symbol, Qty, Pri, ReqType):
        self._auth_state.events.append({"event": "OnGetMktData", "symbol": str(symbol)})
        self._event.set()

    # --- STA / window / ActiveX ---
    def _coinit(self) -> None:
        import pythoncom

        pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
        self._com_initialized = True

    def _couninit(self) -> None:
        if self._com_initialized:
            import pythoncom

            pythoncom.CoUninitialize()
            self._com_initialized = False

    def _create_hidden_window(self) -> int:
        import win32api
        import win32gui

        hinst = win32api.GetModuleHandle(None)
        wc = win32gui.WNDCLASS()
        wc.hInstance = hinst
        wc.lpszClassName = "YuantaFuturesQuoteHost"
        wc.lpfnWndProc = win32gui.DefWindowProc
        self._class_atom = win32gui.RegisterClass(wc)
        hwnd = win32gui.CreateWindow(
            self._class_atom, "YuantaFuturesQuoteHost",
            0, 0, 0, 0, 0, 0, 0, hinst, None,
        )
        if not hwnd:
            raise RuntimeError("CreateWindow failed for Yuanta futures ActiveX host")
        return hwnd

    def connect(self) -> None:
        from ctypes import POINTER, byref
        from comtypes import GUID, IUnknown
        from comtypes.client import GetBestInterface, GetEvents

        self._coinit()
        self._auth_state.state = STATE_CONNECTING
        self._hwnd = self._create_hidden_window()
        atl = ctypes.windll.atl
        Iwindow = POINTER(IUnknown)()
        Icontrol = POINTER(IUnknown)()
        Ievent = POINTER(IUnknown)()
        atl.AtlAxCreateControlEx(PROG_ID, self._hwnd, None, byref(Iwindow),
                                 byref(Icontrol), byref(GUID()), Ievent)
        self._quote = GetBestInterface(Icontrol)
        self._events = GetEvents(self._quote, self)

    # --- bounded message pump ---
    def _pump_until(self, predicate, timeout: float) -> bool:
        import pythoncom

        deadline = time.time() + timeout
        while time.time() < deadline:
            pythoncom.PumpWaitingMessages()
            if predicate():
                return True
            time.sleep(0.05)
        return False

    # --- quote-only 公開方法 ---
    def login(self, account: str, password: str) -> None:
        self._auth_state.state = STATE_LOGIN_REQUESTED
        self._event.clear()
        self._auth_state.events.clear()
        self._quote.SetMktLogon(account, password, *MKT_LOGON_T, 0)
        self._quote.SetMktLogon(account, password, *MKT_LOGON_TP1, 0)

    def wait_login(self, timeout: float | None = None, settle_seconds: float = 8.0) -> FuturesAuthState:
        """等 OnMktStatusChange；首事件後再 settle 數秒收集「登入結果」事件。

        「行情連線成功,等待登入中」是連線階段，非登入確認；登入結果可能是後續事件，
        故 settle 一段時間收集全部事件。
        """
        import pythoncom

        t = timeout or self.message_timeout
        deadline = time.time() + t
        while time.time() < deadline and not self._event.is_set():
            pythoncom.PumpWaitingMessages()
            time.sleep(0.05)
        settle_deadline = time.time() + settle_seconds
        while time.time() < settle_deadline:
            pythoncom.PumpWaitingMessages()
            time.sleep(0.05)
        if self._auth_state.events:
            self._auth_state.state = STATE_AUTHENTICATED
        else:
            self._auth_state.state = STATE_TIMEOUT
        return self._auth_state

    def register_quote_symbol(self, symbol: str, mode: str, ret_type: int) -> int:
        return int(self._quote.AddMktReg(symbol, mode[0] if mode else 0, ret_type, 0))

    def unregister_quote_symbol(self, symbol: str, ret_type: int) -> int:
        return int(self._quote.DelMktReg(symbol, ret_type))

    def pump_quote(self, timeout: float) -> list[dict]:
        """quote probe：bounded 收報價事件，不回傳 PII。"""
        self._auth_state.events.clear()
        self._pump_until(lambda: len(self._auth_state.events) > 0, timeout)
        return list(self._auth_state.events)

    def disconnect(self) -> None:
        import win32gui

        if self._hwnd:
            try:
                win32gui.DestroyWindow(self._hwnd)
            except Exception:
                pass
            self._hwnd = None

    def cleanup(self) -> None:
        try:
            self.disconnect()
        except Exception:
            pass
        self._auth_state.state = STATE_DISCONNECTED
        self._couninit()
