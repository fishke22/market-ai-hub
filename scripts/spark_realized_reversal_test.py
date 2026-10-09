"""Spark 已實現損益 + 沖銷明細 唯讀查詢測試（reuse SparkRuntime，不改現有模組）。

流程（唯讀，絕不呼叫任何下單函式）：
  Login → GetHisRealizedGainLoss(帳號, 起日, 訖日) → 對 JNU 商品逐筆 GetStkHistoryReportReversal
輸出：mask 帳號；不顯示密碼。
"""
import io
import os
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"D:\MARKET_AI_HUB\src")

from market_ai_hub.integrations.yuanta.spark_runtime import SparkRuntime


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


def mask_account(a):
    if not a:
        return "(空)"
    a = str(a)
    return (a[:2] + "****" + a[-2:]) if len(a) > 4 else "****"


def main() -> int:
    pkg_root = os.environ.get("QROS_YUANTA_DLL_DIR") or r"C:\Users\fishk\Documents\元大期貨\YuantaSparkAPI_win-x64_Python\YuantaSparkAPI_win-x64_Python"
    if not os.path.isdir(pkg_root):
        print("DLL 目錄不存在:", pkg_root)
        return 1

    account, password = read_cred("MARKET_AI_HUB/YUANTA/SECURITIES")
    if not password:
        account, password = read_cred("QROS/Yuanta/SecuritiesReadonly")
    if not password:
        print("找不到證券憑證（Windows Credential Manager）")
        return 1
    print("登入帳號:", mask_account(account), "（不顯示密碼）")

    gainloss_objs = []  # 保留原始 RealizedGainLoss 物件（供沖銷明細呼叫）

    def handler(intMark, strIndex, objValue):
        idx = str(strIndex)
        if idx == "GetHisRealizedGainLoss":
            try:
                lst = objValue.RealizedGainLossList
            except Exception as e:
                print("已實現損益回傳解析失敗:", e)
                return
            print("已實現損益查詢回傳: %d 筆" % lst.Count)
            for i in range(lst.Count):
                r = lst[i]
                gainloss_objs.append(r)
                print("  [%d] Mkt=%s 商品=%s 成交日=%s kind=%s 價=%s 量=%s 損益=%s 單號=%s" % (
                    i, r.MarketNo, r.StkCode, r.TradeDate, r.TradeKind,
                    r.Price, r.Qty, r.ProfitLoss, r.OrderNo,
                ))
        elif idx == "GetStkHistoryReportReversal":
            try:
                lst = objValue.ReversalReportList
            except Exception as e:
                print("沖銷明細回傳解析失敗:", e)
                return
            print("沖銷明細回傳: %d 筆" % lst.Count)
            for i in range(lst.Count):
                r = lst[i]
                print("  [%d] 被沖抵成交日=%s 被沖抵成交價=%s 量=%s 沖抵損益=%s" % (
                    i, r.ReversalDate, r.ReversalPrice, r.ReversalQty, r.GlAmt,
                ))
        else:
            print("  [其他回呼]", idx, type(objValue).__name__)

    rt = SparkRuntime(pkg_root=Path(pkg_root))
    try:
        rt._load()
        rt.instantiate()
        rt.on_quote_callback = handler
        rt.open_prod()
        if not rt.wait_connected(20):
            print("連線失敗")
            return 1
        print("連線: 成功")

        rt.login(account, password)
        outcome = rt.wait_login(25)
        print("登入結果:", getattr(outcome, "msg_code", None), "筆數:", getattr(outcome, "count", None))
        if not outcome or outcome.msg_code not in ("0001", "00001"):
            print("登入未成功")
            return 1

        # 已實現損益查詢：2026/07/06 ~ 2026/10/06（區間 < 1 年，符合限制）
        try:
            ok = bool(rt._api.GetHisRealizedGainLoss(account, "2026/07/06", "2026/10/06", rt.enumLangType.UTF8))
        except Exception:
            ok = bool(rt._api.GetHisRealizedGainLoss(account, "2026/07/06", "2026/10/06"))
        print("GetHisRealizedGainLoss 送出:", ok)
        time.sleep(8)  # 等待回呼

        print("已實現損益筆數:", len(gainloss_objs))

        # 對 JNU / OSE 商品呼叫沖銷明細
        jnu = [o for o in gainloss_objs if "JNU" in str(o.StkCode).upper() or "OSE" in str(o.MarketNo).upper()]
        print("JNU/OSE 相關筆數:", len(jnu))
        for obj in jnu[:5]:  # 先測前 5 筆
            try:
                ok2 = bool(rt._api.GetStkHistoryReportReversal(account, obj, rt.enumLangType.UTF8))
            except Exception:
                ok2 = bool(rt._api.GetStkHistoryReportReversal(account, obj))
            print("  GetStkHistoryReportReversal 送出:", ok2, "商品:", obj.StkCode)
            time.sleep(3)

        time.sleep(3)
        return 0
    except Exception as e:
        print("執行異常:", type(e).__name__, e)
        return 1
    finally:
        try:
            rt.cleanup()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
