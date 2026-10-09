"""元大期貨交易 API (YTFutOrdAP) 唯讀測試 — 登入（歸戶 ID 由 Windows Credential Manager 讀取） + 查詢。

COM: Yuanta.YuantaOrdCtrl.1（32-bit OCX，已註冊）
登入: SetFutOrdConnection(歸戶ID, 密碼, api.yuantafutures.com.tw, 443) -> OnLogonS
查詢: RfDealQuery(國外成交) / RfReportQuery(國外委託) / UserDefinsFunc(RA004 外期未平倉明細)
唯讀：絕不呼叫 SendOrderF / RfSendOrder（下單）。
"""
import io
import os
import sys
import threading
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROG_ID = "Yuanta.YuantaOrdCtrl.1"
HOST = "api.yuantafutures.com.tw"
PORT = "443"


def require_32bit():
    return sys.maxsize <= 2**32


def read_cred(target: str):
    try:
        import win32cred

        c = win32cred.CredRead(target, win32cred.CRED_TYPE_GENERIC)
        user = c.get("UserName", "")
        if isinstance(user, bytes):
            user = user.decode("utf-8", "replace")
        blob = c.get("CredentialBlob", b"")
        if isinstance(blob, bytes):
            pw = None
            for enc in ("utf-16-le", "utf-8", "mbcs"):
                try:
                    pw = blob.decode(enc).rstrip("\x00")
                    if pw:
                        break
                except Exception:
                    continue
            if not pw:
                pw = blob.decode("latin-1", "replace")
        else:
            pw = str(blob)
        return str(user), str(pw)
    except Exception:
        return None, None


def decode_big5(s):
    try:
        return str(s).encode("latin-1", "replace").decode("big5", "replace")
    except Exception:
        return str(s)


class YuantaFuturesTradeClient:
    def __init__(self):
        if not require_32bit():
            raise RuntimeError("32-bit 需要，請用 .venv-yuanta-futures-x86")
        self._trade = None
        self._hwnd = None
        self._class_atom = None
        self._com = False
        self._logon_evt = threading.Event()
        self._deal_evt = threading.Event()
        self._report_evt = threading.Event()
        self._uf_evt = threading.Event()
        self.logon_status = None
        self.acc_list = None
        self.casq = None
        self.deal_result = None
        self.report_result = None
        self.uf_result = None

    # ---- 事件 handlers ----
    def OnLogonS(self, *args):
        try:
            self.logon_status = int(args[0]) if args else None
            self.acc_list = decode_big5(args[1]) if len(args) > 1 else None
            self.casq = str(args[2]) if len(args) > 2 else None
        except Exception:
            pass
        self._logon_evt.set()

    def OnRfDealQuery(self, *args):
        try:
            self.deal_result = {
                "args_count": len(args),
                "arg0": str(args[0]) if args else "",
                "arg1": decode_big5(args[1]) if len(args) > 1 else "",
            }
        except Exception:
            self.deal_result = {"raw": str(args)}
        self._deal_evt.set()

    def OnRfReportQuery(self, *args):
        try:
            self.report_result = {
                "args_count": len(args),
                "arg0": str(args[0]) if args else "",
                "arg1": decode_big5(args[1]) if len(args) > 1 else "",
            }
        except Exception:
            self.report_result = {"raw": str(args)}
        self._report_evt.set()

    def OnUserDefinsFuncResult(self, *args):
        try:
            self.uf_result = {
                "row_count": args[0] if args else None,
                "results": decode_big5(args[1]) if len(args) > 1 else "",
            }
        except Exception:
            self.uf_result = {"raw": str(args)}
        self._uf_evt.set()

    # ---- STA / window / ActiveX ----
    def _coinit(self):
        import pythoncom

        pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
        self._com = True

    def _couninit(self):
        if self._com:
            import pythoncom

            pythoncom.CoUninitialize()
            self._com = False

    def _create_hidden_window(self):
        import win32api
        import win32gui

        hinst = win32api.GetModuleHandle(None)
        wc = win32gui.WNDCLASS()
        wc.hInstance = hinst
        wc.lpszClassName = "YuantaFuturesTradeHost"
        wc.lpfnWndProc = win32gui.DefWindowProc
        self._class_atom = win32gui.RegisterClass(wc)
        hwnd = win32gui.CreateWindow(self._class_atom, "YuantaFuturesTradeHost", 0, 0, 0, 0, 0, 0, 0, hinst, None)
        if not hwnd:
            raise RuntimeError("CreateWindow failed")
        return hwnd

    def connect(self):
        import ctypes
        from ctypes import POINTER, byref

        from comtypes import GUID, IUnknown
        from comtypes.client import GetBestInterface, GetEvents

        self._coinit()
        self._hwnd = self._create_hidden_window()
        atl = ctypes.windll.atl
        Iwindow = POINTER(IUnknown)()
        Icontrol = POINTER(IUnknown)()
        Ievent = POINTER(IUnknown)()
        atl.AtlAxCreateControlEx(PROG_ID, self._hwnd, None, byref(Iwindow), byref(Icontrol), byref(GUID()), Ievent)
        self._trade = GetBestInterface(Icontrol)
        self._events = GetEvents(self._trade, self)

    def _pump_until(self, pred, timeout):
        import pythoncom

        deadline = time.time() + timeout
        while time.time() < deadline:
            pythoncom.PumpWaitingMessages()
            if pred():
                return True
            time.sleep(0.05)
        return False

    # ---- 唯讀操作 ----
    def login(self, user_id, password):
        self._logon_evt.clear()
        self._trade.SetFutOrdConnection(user_id, password, HOST, PORT)

    def wait_logon(self, timeout=60):
        return self._pump_until(self._logon_evt.is_set, timeout)

    def query_deal(self, bhno, acno, suba="", exch="*"):
        self._deal_evt.clear()
        self.deal_result = None
        self._trade.RfDealQuery(bhno, acno, suba, exch)

    def wait_deal(self, timeout=30):
        return self._pump_until(self._deal_evt.is_set, timeout)

    def query_report(self, bhno, acno, suba="", stus="0", cflg="0", exch="*"):
        self._report_evt.clear()
        self.report_result = None
        self._trade.RfReportQuery(bhno, acno, suba, stus, cflg, exch)

    def wait_report(self, timeout=30):
        return self._pump_until(self._report_evt.is_set, timeout)

    def query_userdef(self, params, work_id):
        self._uf_evt.clear()
        self.uf_result = None
        self._trade.UserDefinsFunc(params, work_id)

    def wait_userdef(self, timeout=30):
        return self._pump_until(self._uf_evt.is_set, timeout)

    def disconnect(self):
        import win32gui

        if self._hwnd:
            try:
                win32gui.DestroyWindow(self._hwnd)
            except Exception:
                pass
            self._hwnd = None

    def cleanup(self):
        try:
            self.disconnect()
        except Exception:
            pass
        self._couninit()


# 歸戶登入 ID 只存 Windows Credential Manager，源碼永不寫死。
LOGIN_ID_CRED_TARGET = "MARKET_AI_HUB/YUANTA/LEGACY_LOGIN_ID"


def get_login_id() -> str:
    """讀 WinCred 取得歸戶登入 ID；未設定則 fail closed，不回退到任何寫死值。"""
    user, _ = read_cred(LOGIN_ID_CRED_TARGET)
    if not user:
        raise RuntimeError(
            "WinCred target %s 未設定，無法取得登入 ID" % LOGIN_ID_CRED_TARGET
        )
    return str(user)


def main() -> int:
    user_id = get_login_id()
    pw = None
    for target in (
        "MARKET_AI_HUB/YUANTA/SECURITIES",
        "QROS/Yuanta/SecuritiesReadonly",
        "QROS/Yuanta/FuturesTradingQueryReadonly",
        "QROS/Yuanta/FuturesReadonly",
    ):
        _, pw = read_cred(target)
        if pw:
            break
    if not pw:
        print("找不到密碼（credential store）")
        return 1
    masked_id = (user_id[:2] + "***" + user_id[-2:]) if len(user_id) >= 4 else "***"
    print("登入 ID:", masked_id, "（不顯示密碼）")

    c = YuantaFuturesTradeClient()
    try:
        c.connect()
        print("COM 已建立")
        c.login(user_id, pw)
        ok = c.wait_logon(60)
        print("登入事件:", ok, "| 連線狀態:", c.logon_status, "(2=LogonOK)")
        print("帳號清單:", c.acc_list)
        print("憑證序號:", c.casq)
        if not ok or c.logon_status != 2:
            print("登入未成功")
            return 1

        # 解析 AccList：市場別-Branch-Account-SubAccount-姓名
        fut_accounts = []
        if c.acc_list:
            for part in str(c.acc_list).split(";"):
                part = part.strip()
                if not part:
                    continue
                f = part.split("-")
                if len(f) >= 3 and f[0].strip() == "2":
                    fut_accounts.append({
                        "bhno": f[1].strip(),
                        "acno": f[2].strip(),
                        "suba": f[3].strip() if len(f) > 3 else "",
                        "name": f[4].strip() if len(f) > 4 else "",
                    })
        print("期貨帳號:", fut_accounts)
        if not fut_accounts:
            print("AccList 無期貨帳號")
            return 1

        acc = fut_accounts[0]
        print("使用帳號: bhno=%s acno=%s suba=%s" % (acc["bhno"], acc["acno"], acc["suba"]))

        # 1) 國外期貨成交回報查詢
        c.query_deal(acc["bhno"], acc["acno"], acc["suba"], "*")
        ok2 = c.wait_deal(30)
        print("=== 國外成交回報（ok=%s） ===" % ok2)
        print(str(c.deal_result)[:1200])

        # 2) 國外期貨委託回報查詢
        c.query_report(acc["bhno"], acc["acno"], acc["suba"], "0", "0", "*")
        ok3 = c.wait_report(30)
        print("=== 國外委託回報（ok=%s） ===" % ok3)
        print(str(c.report_result)[:1200])

        # 3) 外期未平倉明細（RA004 / EasyWin 0672）
        params = "Func=RA004|bhno=%s|acno=%s|suba=%s|FC=N" % (acc["bhno"], acc["acno"], acc["suba"])
        c.query_userdef(params, "RA004")
        ok4 = c.wait_userdef(30)
        print("=== 外期未平倉明細 RA004（ok=%s） ===" % ok4)
        print(str(c.uf_result)[:900])

        return 0
    except Exception as e:
        print("執行異常:", type(e).__name__, e)
        return 1
    finally:
        c.cleanup()


if __name__ == "__main__":
    sys.exit(main())
