# -*- coding: utf-8 -*-
"""UserDefinsFunc 探測 v2（正確參數，不帶 kind；找歷史沖銷明細代碼）。"""
import io
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 直接讀 v1 的類別與工具函式（去掉 main + stdout 重設）
src = open(r"D:\MARKET_AI_HUB\scripts\futures_userdef_probe.py", "r", encoding="utf-8").read()
head = src[: src.index("def main()")]
head = head.replace('sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")', "")
exec(compile(head, "probe_common", "exec"))


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

        codes = ["FA%03d" % i for i in range(1, 26)] + ["RA%03d" % i for i in range(1, 11)]

        base = account_params(c.acc_list)
        variants = [
            ("basic", base),
            ("withfc", base + "|FC=N"),
            ("withdate", base + "|sdate=2026/07/06|edate=2026/10/06"),
        ]

        print("開始探測 %d 個代碼 x %d 種參數..." % (len(codes), len(variants)))
        hits = []
        for code in codes:
            found_ok = False
            last_err = "(無回應)"
            for pname, pval in variants:
                params = "Func=%s|%s" % (code, pval)
                c.query_userdef(params, code)
                got = c.wait_userdef(5)
                r = ""
                if got and c.uf_result:
                    r = c.uf_result.get("results", "")
                if got and r and "RETC=00000" in r.upper():
                    hits.append((code, pname, r))
                    print()
                    print("=== 成功: %s (%s) ===" % (code, pname))
                    print(r[:700])
                    found_ok = True
                    break
                if got and r:
                    last_err = r[:70].replace("\n", " ")
                time.sleep(0.35)
            if not found_ok:
                print("  %-8s %s" % (code, last_err))

        print()
        print("===== 成功代碼總結 =====")
        for code, pname, r in hits:
            print("  %s (%s) : %s" % (code, pname, r[:220]))
        return 0
    except Exception as e:
        print("執行異常:", type(e).__name__, e)
        return 1
    finally:
        c.cleanup()


if __name__ == "__main__":
    sys.exit(main())
