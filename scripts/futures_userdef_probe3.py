# -*- coding: utf-8 -*-
"""FA 系列用「官方範例原始參數」重測（bhno|acno|suba，不帶 kind/FC/date）。"""
import io
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

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
        print("登入:", ok, "狀態:", c.logon_status)
        if not ok or c.logon_status != 2:
            print("登入失敗")
            return 1

        codes = ["FA%03d" % i for i in range(1, 26)]
        base = account_params(c.acc_list)
        print("重測 FA001~FA025（參數：bhno|acno|suba，來自登入 AccList）...")
        hits = []
        for code in codes:
            params = "Func=%s|%s" % (code, base)
            c.query_userdef(params, code)
            got = c.wait_userdef(5)
            r = ""
            if got and c.uf_result:
                r = c.uf_result.get("results", "")
            if got and r and "RETC=00000" in r.upper():
                hits.append((code, r))
                print()
                print("=== 成功: %s ===" % code)
                print(r[:900])
            else:
                short = (r[:70] if r else "(無回應)")
                print("  %-8s %s" % (code, short.replace("\n", " ")))
            time.sleep(0.4)

        print()
        print("===== 成功代碼總結 =====")
        for code, r in hits:
            print("  %s : %s" % (code, r[:250]))
        return 0
    except Exception as e:
        print("執行異常:", type(e).__name__, e)
        return 1
    finally:
        c.cleanup()


if __name__ == "__main__":
    sys.exit(main())
