# MARKET_AI_HUB 快捷提示詞範例

這些範例的目的是讓任何支援 MCP 的 AI Client 更容易正確使用 `market-ai` tools。

> 不需要逐字照抄。重點是告訴 AI：先用工具拿證據，再回答，不要自己補數字。

---

## 1. 先檢查系統是否正常

```text
先不要分析市場。
請呼叫 market-ai 的 health_check 與 get_system_info，告訴我：
1. MCP 是否正常
2. build_id
3. Chronos / TimesFM 是否 ready
4. CUDA 是否可用
5. 哪些資料來源正常、哪些需要設定
6. 如果發現版本或 runtime 不一致，先停止後續分析
```

適合：第一次連線、更新程式後、結果看起來怪怪的時候。

---

## 2. 快速分析大阪日經

```text
請使用 market-ai 分析大阪日經未來 5 個交易日。
先確認真正模型 Target 是什麼，不要把 ^N225 代理標的說成 OSE Micro。
請給我：
- 模型中心價
- 模型主要統計區間
- 最終研究中心與核心區間
- 偏多 / 基本 / 偏空三種情境
- 支撐、壓力、轉強與轉弱條件
- 目前資料與模型限制
最後用白話告訴我目前比較適合偏多、偏空還是等待。
若沒有足夠 Edge，直接回答 WAIT / NO_EDGE。
```

---

## 3. 大阪日經完整分析

```text
請做大阪日經完整分析。
先取得 market-ai 的資料、模型與 Research Gates，再整合可取得的跨市場資訊。
嚴格區分：
^N225 現貨、OSE Futures、OSE Mini、OSE Micro、CME Nikkei。

請分析：
- 最新有效價格與資料截止時間
- 最近完成的有效交易時段
- 技術與市場結構
- USDJPY、NQ、ES、SOX、VIX、美債等跨市場因素
- Chronos / TimesFM 價格預測
- XGBoost / LightGBM 方向分類
- Ensemble 與 Wrapper，但不得重複計票
- 模型是否真的優於 baseline
- Research Gates
- 重大事件風險
- 至少 2 個反方證據
- Bull / Base / Bear 三情境
- 失效條件

最後再用一般人看得懂的中文整理一次。
```

---

## 4. 只看模型，不做主觀市場判斷

```text
這次只做模型稽核，不要自行加入主觀市場方向。
請分別呼叫 Chronos、TimesFM、方向分類模型與 model performance / validation tools。

請告訴我：
1. 每個模型真正預測的 Target
2. Horizon 是否真的生效
3. forecast_target_dates
4. 模型資料截至時間
5. 價格模型的 P10/P50/P90
6. 分類模型的原始分類分數是否已 calibration
7. 是否優於 Naive / Majority baseline
8. 哪些模型 eligible，哪些不能參與正式投票
9. MODEL_PREDICTIVE_GATE 狀態

不要把 Engineering PASS 說成 Predictive VALIDATED。
```

---

## 5. 檢查 Chronos / TimesFM 是否真的有價值

```text
請使用 run_ts_validation 與可取得的歷史績效資料，檢查 Chronos 與 TimesFM。
不要只看 MAE / RMSE；請優先比較 Naive baseline 與 MASE。

我要知道：
- 測試樣本數
- OOS / walk-forward 是否成立
- MAE
- RMSE
- MASE
- 區間覆蓋率 / calibration（如果有）
- 是否真正優於簡單基準

若沒有打敗 baseline，請明確寫「目前沒有證據證明此模型提供額外預測優勢」。
```

---

## 6. 台股完整分析

把 `2330` 換成你要的股票。

```text
請使用 market-ai 與可取得的官方台股資料完整分析 2330。

先檢查：
- 公司行動 / 除權息 / 減資等價格校正
- 最新交易日與資料新鮮度
- 基本面
- 籌碼
- 技術面
- 相對大盤與產業強弱
- 海外相關市場
- 重大事件
- market-ai 模型
- Research Gates
- 反證與失效條件

模型只是證據之一。
最後請給我：
1. 目前市場狀態
2. 核心價格區間
3. 第一支撐 / 第二支撐
4. 第一壓力 / 第二壓力
5. 什麼條件才值得加碼
6. 什麼條件要減碼或退出
7. 若沒有 Edge，直接說等待
```

---

## 7. 只要白話版本

```text
請先在內部使用 market-ai 完成必要的工具與模型檢查，但回答時不要列大量 JSON 或專業術語。

最後只告訴我：
- 目前最重要的結論
- 比較可能的價格中心與區間
- 多方轉強價位
- 空方轉弱價位
- 我現在比較適合做什麼
- 最大風險是什麼
- 什麼情況需要重新分析

如果模型沒有被驗證，也要用一句白話提醒我。
```

---

## 8. 檢查模型是否重複計票

```text
請稽核本次 market-ai 分析的模型計票方式。

把結果分成：
A. Independent Base Models
B. Ensemble
C. Analysis Wrapper

確認 Ensemble 沒有被當成另一個獨立模型票，Wrapper 也沒有再算一票。
請列出 independent_base_model_count、eligible_direction_vote_count、eligible_price_reference_count。
如果 eligible_direction_vote_count = 0，不得硬做「多數決方向」。
```

---

## 9. 檢查資料是不是過期

```text
請不要先判斷方向。
先檢查本次分析所有主要資料的：
- source_timestamp
- received_at
- quote_age_seconds
- freshness_status
- market_open
- tradable_now
- session_status
- usable_for_live_decision

請特別指出：
哪些資料是 LIVE / RECENT，哪些是 STALE / HISTORICAL。
不要因為 timestamp 看起來新，就假設市場正在交易。
```

---

## 10. 週末分析大阪日經

```text
現在是週末，請分析下一個大阪日經相關交易時段。
不要只退回星期五 ^N225 現貨收盤。

請先分清楚：
- ^N225 現貨最後收盤
- OSE / CME 是否有更晚的價格發現資訊
- 使用中的模型 Target 到底是哪個商品
- 下一個真正交易時段與交易日曆

如果目前拿不到真正 OSE 最新價格，要明確寫 N/A，不能用 CME 或 ^N225 冒充。
```

---

## 11. 只看 Research Gates

```text
請呼叫 get_research_gates，逐項用白話解釋：
ENGINEERING_GATE
MARKET_DATA_GATE
CALENDAR_GATE
TEMPORAL_ALIGNMENT_GATE
DATA_GATE
MODEL_PREDICTIVE_GATE
TRADING_EDGE_GATE

請特別回答：
「目前哪些事情已被證明？哪些事情還沒有被證明？」
不要把 UNPROVEN 說成 FAIL，也不要把 PASS 說成已證明獲利。
```

---

## 12. 強制反方審查

```text
請完成正常分析後，再當一次反方 Reviewer。
至少找出 2 個最可能讓目前結論失效的證據。

優先檢查：
- Target 是否混用
- Proxy 是否冒充真期貨
- 模型資料是否比最新市場舊
- Calendar / Session 是否錯
- 模型是否輸給 baseline
- 跨市場證據是否互相矛盾
- 是否有即將公布的重大事件

如果反方證據很強，請降低研究信心或改成 WAIT。
```

---

## 13. 比較不同預測期間

```text
請分別研究 1d、2d、5d、10d 預測。
確認 effective_horizon_steps、forecast_path 與 forecast_target_dates 真正不同。
如果不同 horizon 回傳異常相同結果，請標記「預測期間完整性警告」，必要時呼叫 run_ts_validation。
不要只因 tool 接受 horizon 參數，就假設 horizon 真的有生效。
```

---

## 14. 不要為了回答而硬給交易訊號

```text
請分析目前市場，但這次有一條硬規則：
如果資料、模型與市場結構沒有形成足夠優勢，最終答案必須是 WAIT 或 NO_EDGE。

不要因為我問「怎麼操作」就硬產生多空方向。
請告訴我需要看到哪些價格或證據出現後，才值得重新考慮進場。
```

---

# 使用原則

好的 Prompt 通常不需要把所有技術規則重複一遍。

如果你已經使用完整 System Prompt，可以直接問：

```text
分析大阪日經未來 5 個交易日
```

或：

```text
完整分析 2330，最後給我白話操作地圖
```

如果沒有完整 System Prompt，再使用上面的長版快捷提示詞，可以降低 AI 誤用 MCP 結果的機率。
