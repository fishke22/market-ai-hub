# -*- coding: utf-8 -*-
"""深度分析：每日損益表 + 連敗後行為 + 前後手續費效應。"""
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
c = c.sort_values(["date", "order"]).reset_index(drop=True)

print("========== 每日損益表 ==========")
daily = c.groupby(c["date"].dt.date).agg(
    trades=("net", "count"),
    wins=("net", lambda s: (s > 0).sum()),
    net=("net", "sum"),
    mean=("net", "mean"),
)
daily["wr%"] = (100 * daily["wins"] / daily["trades"]).round(1)
daily["cum"] = daily["net"].cumsum()
print(daily.to_string())

print()
print("========== 連敗後行為（下單連動） ==========")
net = c["net"].tolist()
wins = (c["net"] > 0).astype(int).tolist()

# 前一筆是否賠 → 下一筆表現
prev_loss = [False] + [w == 0 for w in wins[:-1]]
after_loss = c[prev_loss]
print("前一筆賠 → 下一筆（共 %d 筆）: 勝率 %.1f%%  期望值 %+.0f" % (len(after_loss), 100 * (after_loss["net"] > 0).mean(), after_loss["net"].mean()))
after_win = c[[not p for p in prev_loss]]
print("前一筆賺 → 下一筆（共 %d 筆）: 勝率 %.1f%%  期望值 %+.0f" % (len(after_win), 100 * (after_win["net"] > 0).mean(), after_win["net"].mean()))

# 連續 2+ 筆賠後 → 下一筆（報復性交易檢測）
consec_loss = 0
after_2loss = []
after_3loss = []
for i in range(1, len(wins)):
    if wins[i - 1] == 0:
        consec_loss += 1
    else:
        consec_loss = 0
    if consec_loss >= 2:
        after_2loss.append(i)
    if consec_loss >= 3:
        after_3loss.append(i)
if after_2loss:
    sub = c.iloc[after_2loss]
    print("連續 2+ 筆賠後 → 下一筆（%d 筆）: 勝率 %.1f%%  期望值 %+.0f  平均賠 %+.0f" % (
        len(sub), 100 * (sub["net"] > 0).mean(), sub["net"].mean(), sub[sub["net"] < 0]["net"].mean() if (sub["net"] < 0).any() else 0))
if after_3loss:
    sub = c.iloc[after_3loss]
    print("連續 3+ 筆賠後 → 下一筆（%d 筆）: 勝率 %.1f%%  期望值 %+.0f" % (len(sub), 100 * (sub["net"] > 0).mean(), sub["net"].mean()))
else:
    print("（無連續 3+ 筆賠的情況）")

print()
print("========== 週別損益 ==========")
c["week"] = c["date"].dt.to_period("W")
wk = c.groupby("week")["net"].agg(["count", "sum"]).round(0)
print(wk.to_string())

print()
print("========== 大虧損(<-100000)交易日分布 ==========")
big = c[c["net"] < -100000]
print("大虧損筆數: %d  總額: %+.0f" % (len(big), big["net"].sum()))
print(big.groupby(big["date"].dt.date)["net"].agg(["count", "sum"]).to_string() if len(big) else "(無)")