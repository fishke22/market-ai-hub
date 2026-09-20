# 每天怎麼用（新手版）

> 每天要做什麼？其實很簡單：**問一句話就夠了。**

---

## 最簡單的用法

打開 Cherry Studio，問：

> 幫我分析今天大阪日經。

AI 會自動處理一切。**你不需要手動跑一堆指令。**

## 分時段建議

### 早上 / 開盤前
- 問一句：「今天資料是不是最新的？」
- 如果 225LABO 沒更新，看下方「收盤後」。

### 交易期間
- 需要時問：「幫我分析大阪日經現在情況。」
- 系統只是**研究參考**，不會幫你下單。

### 收盤後（重要）
1. 如果今天有新資料：先更新 225LABO（見 [DATA_UPDATE_FOR_BEGINNERS.md](DATA_UPDATE_FOR_BEGINNERS.md)）。
2. 讓系統產生今天的預測並封存（Forward Shadow）。
3. 問：「Forward Shadow 累積多少筆了？」

### 每週
- 問：「模型最近有沒有失準？」（看漂移）
- 問：「資料品質有沒有問題？」

### 每月 / 證據回顧
- 問：「目前有沒有可以交易的證據？」（答案通常是：還沒有）
- 問：「離可交易還有多遠？」

---

## 進階（技術使用者才需要）

一般使用者**不需要**跑下面這些。只有想自己操作的人才看：

```powershell
# 匯入新 225LABO 資料
scripts\import_latest_225labo_micro.ps1

# 每日 forward cycle（匯入 → 預測 → 結算 → 狀態）
scripts\run_daily_forward_cycle.ps1

# 看資源狀態
scripts\resource_status.ps1
```

## 電腦關機了怎麼辦？

- 資料可以之後補下載。
- 但**那天漏掉的預測，不能事後補成「真正 forward」**（只能標 MISSED_FORWARD_ORIGIN）。

這不是系統壞掉，是「誠實記錄」——因為真正 forward 必須在「當時、答案還沒出現前」建立。

## 狀態用語對照

| 系統顯示 | 白話 |
|---------|------|
| FRESH | 資料新鮮（正常） |
| STALE | 資料過期 |
| MISSING_CURRENT_SESSION | 等待資料 |
| NEEDS_CONFIG | 需要設定 |
| RESEARCH_ONLY | 僅研究 |
| NONE_YET | 還沒有 |
| NON_EXECUTABLE | 不可執行（不可交易） |
