# -*- coding: utf-8 -*-
"""UserDefinsFunc 功能代碼探測（獨立版）— 找歷史沖銷明細代碼（唯讀）。"""
import io
import sys
import threading
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROG_ID = "Yuanta.YuantaOrdCtrl.1"
HOST = "api.yuantafutures.com.tw"
PORT = "443"


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


class Client:
    def __init__(self):
        self._trade = None
        self._hwnd = None
        self._class_atom = None
        self._com = False
        self._logon_evt = threading.Event()
        self._uf_evt = threading.Event()
        self.logon_status = None
        self.acc_list = None
        self.uf_result = None

    def OnLogonS(self, *args):
        try:
            self.logon_status = int(args[0]) if args else None
            self.acc_list = decode_big5(args[1]) if len(args) > 1 else None
        except Exception:
            pass
        self._logon_evt.set()

    def OnUserDefinsFuncResult(self, *args):
        try:
            self.uf_result = {
                "row_count": args[0] if args else None,
                "results": decode_big5(args[1]) if len(args) > 1 else "",
            }
        except Exception:
            self.uf_result = {"raw": str(args)}
        self._uf_evt.set()

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
        wc.lpszClassName = "YuantaFuturesTradeHost2"
        wc.lpfnWndProc = win32gui.DefWindowProc
        self._class_atom = win32gui.RegisterClass(wc)
        hwnd = win32gui.CreateWindow(self._class_atom, "YuantaFuturesTradeHost2", 0, 0, 0, 0, 0, 0, 0, hinst, None)
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

    def login(self, user_id, password):
        self._logon_evt.clear()
        self._trade.SetFutOrdConnection(user_id, password, HOST, PORT)

    def wait_logon(self, timeout=60):
        return self._pump_until(self._logon_evt.is_set, timeout)

    def query_userdef(self, params, work_id):
        self._uf_evt.clear()
        self.uf_result = None
        self._trade.UserDefinsFunc(params, work_id)

    def wait_userdef(self, timeout=5):
        return self._pump_until(self._uf_evt.is_set, timeout)

    def cleanup(self):
        import win32gui

        try:
            if self._hwnd:
                win32gui.DestroyWindow(self._hwnd)
                self._hwnd = None
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


def futures_accounts(acc_list):
    """解析 AccList「市場別-Branch-Account-SubAccount-姓名」，只取市場別=2（期貨）。

    帳號來自登入回傳，因此源碼不含任何實際 branch/account。
    """
    out = []
    if not acc_list:
        return out
    for part in str(acc_list).split(";"):
        part = part.strip()
        if not part:
            continue
        f = part.split("-")
        if len(f) >= 3 and f[0].strip() == "2":
            out.append({
                "bhno": f[1].strip(),
                "acno": f[2].strip(),
                "suba": f[3].strip() if len(f) > 3 else "",
            })
    return out


def account_params(acc_list, suffix="") -> str:
    """由 AccList 組出 UserDefinsFunc 參數（bhno|acno|suba + 可選後綴）。"""
    accs = futures_accounts(acc_list)
    if not accs:
        raise RuntimeError("AccList 無期貨帳號（市場別=2），無法組查詢參數")
    a = accs[0]
    return "bhno=%s|acno=%s|suba=%s%s" % (a["bhno"], a["acno"], a["suba"], suffix)


def main() -> int:
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
        print("找不到密碼")
        return 1

    c = Client()
    try:
        c.connect()
        c.login(get_login_id(), pw)
        ok = c.wait_logon(60)
        print("登入:", ok, "狀態:", c.logon_status, "帳號清單:", c.acc_list)
        if not ok or c.logon_status != 2:
            print("登入失敗")
            return 1

        base = account_params(c.acc_list, "|kind=F|FC=N")

        codes = []
        codes += ["FA%03d" % i for i in range(4, 31)]
        codes += ["RA%03d" % i for i in range(1, 31)]
        codes += ["FA%03d" % i for i in range(31, 51)]

        print("開始探測 %d 個代碼（每碼最多等 5 秒）..." % len(codes))
        hits = []
        for code in codes:
            params = "Func=%s|%s" % (code, base)
            c.query_userdef(params, code)
            got = c.wait_userdef(5)
            r = ""
            if got and c.uf_result:
                r = c.uf_result.get("results", "")
            if got and r and "retc=00000" in r:
                hits.append((code, r))
                print()
                print("=== 成功代碼: %s ===" % code)
                print(r[:300])
            else:
                short = (r[:50] if r else "(無回應)")
                print("  %-8s %s" % (code, short.replace("\n", " ")))
            time.sleep(0.4)

        print()
        print("===== 成功代碼總結 =====")
        for code, r in hits:
            print("  %s : %s" % (code, r[:200]))
        return 0
    except Exception as e:
        print("執行異常:", type(e).__name__, e)
        return 1
    finally:
        c.cleanup()


if __name__ == "__main__":
    sys.exit(main())
