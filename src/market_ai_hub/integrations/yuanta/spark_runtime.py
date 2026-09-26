"""Phase 2Y-C — Yuanta SPARK runtime（官方 pythonnet 載入 + RealYuantaSparkClient）。

- 依官方 Python 範例：load("coreclr") → clr.AddReference("YuantaSparkAPI") →
  from YuantaOneAPI import (...) → YuantaSparkAPITrader() → OnResponse += handler。
- 不使用 Assembly.GetTypes() 完整 reflection（ReflectionTypeLoadException 不阻擋公開 API）。
- enum 值 runtime 反射：PROD=2 / UAT=1 / OSE=207（以 installed DLL 為準，不硬 cast 猜值）。
- Login() return True 只代表 accepted；真正結果來自 OnResponse 的 LoginResult.LoginStatus.MsgCode。
- 只允許明確列出的 quote-only lifecycle/query 方法；無 generic invoke、無 order method。
"""
from __future__ import annotations

import os
import sys
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
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

# OnResponse intMark=0 / dwIndex 官方系統狀態碼。
SYSTEM_OTHER = 0
SYSTEM_CONNECT = 1
SYSTEM_DISCONNECT = 2
SYSTEM_NETWORK_ERROR = 3
SYSTEM_UPDATE_REQUIRED = 4
SYSTEM_NOT_CONNECTED = 5
SYSTEM_ANNOUNCEMENT = 6

_CONNECTION_STATE_BY_CODE = {
    SYSTEM_CONNECT: "CONNECTED",
    SYSTEM_DISCONNECT: "DISCONNECTED",
    SYSTEM_NETWORK_ERROR: "NETWORK_ERROR",
    SYSTEM_UPDATE_REQUIRED: "UPDATE_REQUIRED",
    SYSTEM_NOT_CONNECTED: "NOT_CONNECTED",
}
_CONNECTION_FAULT_CODES = {
    SYSTEM_DISCONNECT, SYSTEM_NETWORK_ERROR, SYSTEM_UPDATE_REQUIRED, SYSTEM_NOT_CONNECTED,
}

PKG_ROOT = Path(__file__).resolve().parents[4] / "vendor" / "yuanta_spark" / "2.2026.0918.0" / "YuantaSparkAPI_win-x64_Python"


@dataclass
class LoginOutcome:
    msg_code: str | None = None
    count: int = 0
    received: bool = False


@dataclass
class TickDetailRequestTrace:
    request_id: str
    request_time_utc: datetime
    market_no: int
    stock_code: str
    last_count: int
    accepted: bool | None = None


@dataclass(frozen=True)
class TickDetailCallbackTrace:
    request_id: str
    callback_received_at_utc: datetime
    callback_mark: int
    callback_index: str
    returned_market_no: int | None
    returned_stock_code: str


class SparkRuntime:
    """官方 pythonnet 載入 + YuantaSparkAPITrader 生命周期。"""

    def __init__(self, pkg_root: Path | None = None) -> None:
        self.pkg_root = pkg_root or PKG_ROOT
        self._api = None
        self._delegate = None
        self._login_event = threading.Event()
        self._system_event = threading.Event()
        self._connection_fault_event = threading.Event()
        self._connection_state = "INITIAL"
        self._connection_system_code: int | None = None
        self._login_outcome = LoginOutcome()
        self._callbacks = deque(maxlen=1000)
        self._system_messages = deque(maxlen=100)
        self.on_quote_callback = None  # optional callable(intMark, strIndex, objValue)
        self.on_tick_detail_callback = None  # optional typed GetStkTickDetail result hook
        self._tick_detail_request_seq = 0
        self._tick_detail_requests = deque(maxlen=32)
        self._tick_detail_callbacks = deque(maxlen=32)
        self._clock = lambda: datetime.now(timezone.utc)
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
            enumStkTickSelectType,
        )

        self.YuantaSparkAPITrader = YuantaSparkAPITrader
        self.OnResponseEventHandler = OnResponseEventHandler
        self.enumEnvironmentMode = enumEnvironmentMode
        self.enumLangType = enumLangType
        self.enumLogType = enumLogType
        self.enumMarketType = enumMarketType
        self.enumQuoteIndexType = enumQuoteIndexType
        self.enumStkTickSelectType = enumStkTickSelectType

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

    def _ensure_connection_state(self) -> None:
        if not hasattr(self, "_system_event"):
            self._system_event = threading.Event()
        if not hasattr(self, "_connection_fault_event"):
            self._connection_fault_event = threading.Event()
        if not hasattr(self, "_connection_state"):
            self._connection_state = "INITIAL"
        if not hasattr(self, "_connection_system_code"):
            self._connection_system_code = None

    def connection_snapshot(self) -> dict:
        """PII-free last official system-event state; fault is latched until a new Open()."""
        self._ensure_connection_state()
        return {
            "state": self._connection_state,
            "system_code": self._connection_system_code,
            "faulted": self._connection_fault_event.is_set(),
        }

    def _on_response(self, intMark, dwIndex, strIndex, objHandle, objValue) -> None:
        try:
            type_name = type(objValue).__name__ if objValue is not None else "None"
            self._callbacks.append({"intMark": int(intMark), "strIndex": str(strIndex), "type": type_name})
            if int(intMark) == 0:
                # 官方 OnResponse：dwIndex=1 才是 Connect；2/3/4/5 都不可當 connected。
                self._ensure_connection_state()
                system_code = int(dwIndex)
                self._connection_system_code = system_code
                try:
                    self._system_messages.append(str(objValue)[:200])
                except Exception:
                    self._system_messages.append("<unprintable>")
                if system_code in _CONNECTION_STATE_BY_CODE:
                    self._connection_state = _CONNECTION_STATE_BY_CODE[system_code]
                if system_code == SYSTEM_CONNECT:
                    # A later Connect may update current state, but never erases a fault that
                    # occurred after Open: subscription continuity would be unknown.
                    self._system_event.set()
                elif system_code in _CONNECTION_FAULT_CODES:
                    self._connection_fault_event.set()
            if str(strIndex) == "Login":
                status = objValue.LoginStatus
                self._login_outcome = LoginOutcome(
                    msg_code=str(status.MsgCode),
                    count=int(status.Count),
                    received=True,
                )
                self._login_event.set()
            elif str(strIndex) == "GetStkTickDetail":
                self._record_tick_detail_callback(int(intMark), str(strIndex), objValue)
                if self.on_tick_detail_callback is not None:
                    self.on_tick_detail_callback(int(intMark), objValue)
            elif self.on_quote_callback is not None:
                # quote-only: bounded probe hook; no persistent stream
                self.on_quote_callback(int(intMark), str(strIndex), objValue)
        except Exception:
            self._login_event.set()

    def wait_connected(self, timeout: float = 15.0) -> bool:
        """Wait only for official Connect (intMark=0,dwIndex=1); fault statuses fail closed."""
        self._ensure_connection_state()
        deadline = time.monotonic() + max(0.0, float(timeout))
        while True:
            if self._connection_fault_event.is_set():
                return False
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            if self._system_event.wait(min(0.05, remaining)):
                return True

    def system_messages(self) -> list[str]:
        return list(self._system_messages)

    def callback_diagnostics(self) -> list[dict]:
        """回呼記錄（無 PII：只 intMark / strIndex / type 名）。"""
        return list(self._callbacks)

    # --- quote-only 公開方法（無 order / 無 generic invoke）---
    def open_prod(self) -> None:
        self._ensure_connection_state()
        self._system_event.clear()
        self._connection_fault_event.clear()
        self._connection_state = "CONNECTING"
        self._connection_system_code = None
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

    def _ensure_tick_detail_trace_state(self) -> None:
        if not hasattr(self, "_tick_detail_request_seq"):
            self._tick_detail_request_seq = 0
        if not hasattr(self, "_tick_detail_requests"):
            self._tick_detail_requests = deque(maxlen=32)
        if not hasattr(self, "_tick_detail_callbacks"):
            self._tick_detail_callbacks = deque(maxlen=32)
        if not hasattr(self, "_clock"):
            self._clock = lambda: datetime.now(timezone.utc)

    def _record_tick_detail_callback(self, mark: int, index: str, obj_value) -> None:
        self._ensure_tick_detail_trace_state()
        received = self._clock().astimezone(timezone.utc)
        try:
            returned_market = int(getattr(obj_value, "MarketNo"))
        except Exception:
            returned_market = None
        returned_code = str(getattr(obj_value, "StockCode", "") or "").strip()
        used_ids = {x.request_id for x in self._tick_detail_callbacks if x.request_id}
        candidates = []
        for req in self._tick_detail_requests:
            if req.request_id in used_ids:
                continue
            if returned_market is not None and req.market_no != returned_market:
                continue
            if returned_code and req.stock_code != returned_code:
                continue
            candidates.append(req)
        # GetStkTickDetail callback does not expose our local request id.  Never
        # guess when two outstanding requests have the same returned identity.
        request_id = candidates[0].request_id if len(candidates) == 1 else ""
        self._tick_detail_callbacks.append(TickDetailCallbackTrace(
            request_id=request_id,
            callback_received_at_utc=received,
            callback_mark=int(mark),
            callback_index=str(index),
            returned_market_no=returned_market,
            returned_stock_code=returned_code,
        ))

    def tick_detail_runtime_traces(self) -> dict:
        """Return bounded request/callback metadata only; never includes account or prices."""
        self._ensure_tick_detail_trace_state()
        return {
            "requests": [asdict(x) for x in self._tick_detail_requests],
            "callbacks": [asdict(x) for x in self._tick_detail_callbacks],
        }

    def latest_tick_detail_request(self):
        """Return the latest typed tick-detail request trace, if any."""
        self._ensure_tick_detail_trace_state()
        return self._tick_detail_requests[-1] if self._tick_detail_requests else None

    def latest_tick_detail_exchange(self):
        """Return latest correlated typed request/callback pair when complete."""
        self._ensure_tick_detail_trace_state()
        requests = {x.request_id: x for x in self._tick_detail_requests}
        for callback in reversed(self._tick_detail_callbacks):
            request = requests.get(callback.request_id)
            if request is not None and request.accepted is not None:
                return request, callback
        return None

    def request_tick_detail_last(self, account: str, market_no: int, stock_code: str,
                                 last_count: int = 20) -> bool:
        """Submit bounded read-only GetStkTickDetail and retain correlation metadata."""
        if not str(account or "").strip():
            raise ValueError("account required")
        code = str(stock_code or "").strip()
        if not code or len(code) > 64 or any(ch in code for ch in "\r\n\t"):
            raise ValueError("invalid stock_code")
        count = int(last_count)
        if count < 1 or count > 20:
            raise ValueError("last_count must be 1..20")
        self._ensure_tick_detail_trace_state()
        self._tick_detail_request_seq += 1
        trace = TickDetailRequestTrace(
            request_id=f"tick_detail_{self._tick_detail_request_seq}",
            request_time_utc=self._clock().astimezone(timezone.utc),
            market_no=int(market_no),
            stock_code=code,
            last_count=count,
        )
        self._tick_detail_requests.append(trace)
        try:
            accepted = bool(self._api.GetStkTickDetail(
                account,
                self.enumMarketType(int(market_no)),
                code,
                self.enumStkTickSelectType(1),
                "00:00:00",
                "23:59:59",
                count,
                self.enumLangType.UTF8,
            ))
        except Exception:
            trace.accepted = False
            raise
        trace.accepted = accepted
        return accepted

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
