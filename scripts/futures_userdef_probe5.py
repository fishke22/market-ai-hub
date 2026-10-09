# -*- coding: utf-8 -*-
"""聚焦 FA004/FA005/FA007（日期代碼）+ 長超時 25 秒。"""
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

        B = account_params(c.acc_list)
        tests = [
            ("FA004", B + "clear_date=2026/10/06"),
            ("FA004", B + "clear_date=20261006"),
            ("FA005", B + "start_date=2026/07/06|end_date=2026/10/06"),
            ("FA005", B + "start_date=20260706|end_date=20261006"),
            ("FA007", B + "from=2026/07/06|to=2026/10/06"),
        ]

        for code, params in tests:
            p = "Func=%s|%s" % (code, params)
            print()
            print("=== %s | %s ===" % (code, params))
            c.query_userdef(p, code)
            got = c.wait_userdef(25)  # 長超時
            r = ""
            if got and c.uf_result:
                r = c.uf_result.get("results", "")
                rc = c.uf_result.get("row_count")
                print("row_count:", rc)
                print(r[:1500] if r else "(空)")
            else:
                print("(25 秒無回應)")
            time.sleep(1)

        return 0
    except Exception as e:
        print("執行異常:", type(e).__name__, e)
        return 1
    finally:
        c.cleanup()


if __name__ == "__main__":
    sys.exit(main())
