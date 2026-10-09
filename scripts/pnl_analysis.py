# -*- coding: utf-8 -*-
"""平倉損益條件化分析（569 筆已實現損益交易）。"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import pandas as pd

f = r"C:\Users\fishk\Downloads\平倉損益查詢結果_20260610223405.xls"
df = pd.read_excel(f, engine="xlrd")
df.columns = ["order", "product", "bs", "date", "price", "qty_raw", "gl", "ccy", "fee", "tax", "net"]
df["qty"] = df["qty_raw"].astype(str).str.extract(r"(\d+)").astype(float)
df["is_close"] = df["qty_raw"].astype(str).str.contains("平")
df["date"] = pd.to_datetime(df["date"])
c = df[df["is_close"]].copy()
c["side"] = c["bs"].str.strip().map({"買": "做多", "賣": "做空"}).fillna(c["bs"])


def stats(d, name):
    n = len(d)
    wins = (d["net"] > 0).sum()
    losses = (d["net"] < 0).sum()
    avg_w = d.loc[d["net"] > 0, "net"].mean() if wins else 0
    avg_l = d.loc[d["net"] < 0, "net"].mean() if losses else 0
    exp = d["net"].mean()
    rr = abs(avg_w / avg_l) if avg_l else float("inf")
    print(
        "  %-12s 筆=%-4d 總損益=%10.0f 勝率=%5.1f%% 平均賺=%7.0f 平均賠=%7.0f 盈虧比=%.2f 期望值/筆=%7.0f"
        % (name, n, d["net"].sum(), 100 * wins / n, avg_w, avg_l, rr, exp)
    )
    return dict(n=n, total=d["net"].sum(), wr=100 * wins / n, avg_w=avg_w, avg_l=avg_l, rr=rr, exp=exp)


print("========== 平倉交易（已實現損益）==========")
stats(c, "全部")
print()
print("--- 做多 vs 做空 ---")
stats(c[c["side"] == "做多"], "做多")
stats(c[c["side"] == "做空"], "做空")
print()
print("--- 口數分組 ---")
for q in sorted(c["qty"].unique()):
    stats(c[c["qty"] == q], "口數%d" % int(q))
print()
print("--- 商品分組 ---")
for p in sorted(c["product"].unique()):
    stats(c[c["product"] == p], str(p)[:14])
print()
print("--- 日期維度（每日） ---")
daily = c.groupby(c["date"].dt.date)["net"].agg(["count", "sum", "mean"])
days_n = len(daily)
print("  交易日數: %d  賺錢日: %d  賠錢日: %d" % (days_n, (daily["sum"] > 0).sum(), (daily["sum"] < 0).sum()))
print("  最佳日: %s (%+.0f)  最差日: %s (%+.0f)" % (daily["sum"].idxmax(), daily["sum"].max(), daily["sum"].idxmin(), daily["sum"].min()))
print("  平均每日損益: %+.0f  中位數: %+.0f" % (daily["sum"].mean(), daily["sum"].median()))
print("  交易最多的一天: %s (%d 筆)" % (daily["count"].idxmax(), daily["count"].max()))
print()
print("--- 連勝/連敗（依日期+委託序） ---")
c2 = c.sort_values(["date", "order"])
streak = 0
max_w = 0
max_l = 0
cur_w = 0
cur_l = 0
for v in (c2["net"] > 0):
    if v:
        cur_w += 1
        cur_l = 0
        max_w = max(max_w, cur_w)
    else:
        cur_l += 1
        cur_w = 0
        max_l = max(max_l, cur_l)
print("  最長連勝: %d 筆   最長連敗: %d 筆" % (max_w, max_l))
print()
print("--- 手續費影響 ---")
print("  平倉損益總和: %+.0f   淨損益總和: %+.0f   手續費總計: %+.0f" % (c["gl"].sum(), c["net"].sum(), c["fee"].sum()))
print("  平均每筆手續費: %.0f" % c["fee"].mean())
print()
print("--- 單筆最大/最小 ---")
print("  最大獲利: %+.0f  最大虧損: %+.0f" % (c["net"].max(), c["net"].min()))
print("  獲利分佈: P75=%+.0f P50=%+.0f P25=%+.0f" % (c["net"].quantile(0.75), c["net"].median(), c["net"].quantile(0.25)))