# MARKET_AI_HUB 跨對話上下文快照

快照日期：2026-09-25（Asia/Taipei）。用途：上傳 ChatGPT 專案資料來源。此檔是查核資料，不是新的執行授權。後續應替換此快照，避免多份「最新」並存。

## 1. 先讀這段

本專案已超過第一階段。公開 main 已有 Phase 2、多輪安全與資料語義修正、Price/Probability Map 基礎，以及 V2-A 至 V2-I 2I.1。不要把「第二階段施工」解讀成 V2-I 尚未存在，也不要重做它們。

實際施工 repo 是 `D:\MARKET_AI_HUB`；本次 Codex 的 `C:\Users\fishk\Documents\ChatGPT\MARKET_AI_HUB` 原先只是空 Git 倉庫，現在只存本交接包，不能混為同一 repo。

GitHub：https://github.com/fishke22/market-ai-hub

2026-09-25 W3.1 治理工作包交接：

W1/W2 已完成的修補與離線資料鏈不重做。W3.1 implementation commit 為 `95289de6722c1477c5183e172384a3fd196050fd`；工作分支仍為 `codex/quote-hub-correctness`。runtime build_id = `98fe354dcc4fb275`。PR/remote/CI 的最終發布狀態以 handoff 與本次回報為準。

V2-H 已升到 2H.3：prediction identity 可在結果出現前封存 `sample_origin` 與 label window；有封存 window 時，outcome 未到期或 target_period 不符會在寫入邊界直接拒絕。W3.1 再要求明確 `evaluation_as_of` 與同 target/model/version/event/label/sample-origin scope，forward precommitted 與 retrospective replay 不得混算，duplicate logical sample / superseded selection fail closed；通過後才交給既有 2I.1 指標引擎。

最新 code/test 驗證：W3/V2-H/V2-I focused 85 passed；W3 + PPM/packet broader 236 passed、1 deselected；audit path/build 74 passed；default suite 1749 passed、23 deselected、132 warnings，172.00s，exit 0。本輪 implementation/test secret scan 0 命中，`git diff --check` PASS。

**這仍不是 CALIBRATED。** W3.1 測試樣本是 temporary synthetic audit records，只證明 governance/leakage engine。真實 `FORWARD_PRECOMMITTED` 預測仍需在結果前實際封存並等 horizon 自然到期；W4 fitting 必須等足夠真實、同 scope 的成熟樣本。

**現場 recorder 仍明確為 RUNTIME_ADOPTION_PENDING。** 本棒沒有 broker login/訂閱/登出/重啟/下單/帳務操作；受控重啟仍需使用者明確維護窗口授權。

## 2. 查核深度與限制

完成當時 650 文字檔結構/hash/UTF-8/AST 盤點，重點審閱架構、V2-H/I、PPM、公用 packet/gate、路徑、安裝/CI、完整 recorder。未宣稱全部逐行審計，未讀全部私有資料/權重。
最初88 tests與三個反例屬修補前證據；後續正式 regression 是修補後證據。完整 hash inventory 保留在本機 AUDIT_EVIDENCE.json，不要每棒讀全部。執行能力：本輪先用 Remote，依使用者最新偏好改為 Codex 原生工具；未修改 OpenCode 設定。

## 3. 系統用途與資料流

```text
官方/免費日線與總經、既有元大行情
  → provider / quote recorder
  → 原始來源與 immutable snapshot、as-of/session/contract 語義
  → feature store / factor routing / label engine
  → baseline、價格模型、方向分類器、研究 challenger
  → direct / joint / scenario / dynamic ensemble（分開保存）
  → prediction + forecast artifact + factor lineage
  → 到期 outcome → evaluation → 獨立 calibration / OOS / forward
  → public-safe Analysis Packet / MCP
  → 任意相容平台的 LLM 用白話解釋
```

上圖是既有元件與目標資料流；**不是宣稱每段均已接通**。W2 離線鏈已接到 read-only model-input boundary；W3.1 已完成 prediction/outcome maturity 與 evaluation-as-of/scope governance。現有 broker `TICK` 對現有 `1d` 模型仍明確回 `INCOMPATIBLE_FREQUENCY`，所以沒有把 tick 假造成日線，也沒有宣稱 broker DATA READY。現場 recorder 尚未 adoption；真實 forward 樣本與 calibration fitting 也尚未成立。

核心產品是研究 MCP 系統，不依賴 Cherry Studio 專屬能力。ChatGPT/OpenCode/其他 agent 是工程或解讀客戶端；不同平台用同一份具時間、來源、版本、限制的結構化輸出。

## 4. 模型角色

| 層 | 既有內容 | 正確解讀 |
|---|---|---|
| 基線 | last value、drift、seasonal naive、MA、ridge、VAR、Kalman 等研究基準 | 必須保留；打不贏基線可直接選基線 |
| 價格預測 | Chronos-2、TimesFM-3.0 | 有 adapter/登錄不等於對每個市場有有效預測證據 |
| 方向分類 | XGBoost、LightGBM | class score 不能直接稱校準機率 |
| 額外模型 | FinCast optional/partial；NHITS/NBEATSx、Kronos-TW、Sundial、TTM、Moirai challenger | 實際可用、依賴、授權、runtime 與成績分開核對 |
| 統合 | direct、joint、rule scenario、dynamic ensemble | 不混成一個不可追溯 final price；scenario 權重不自稱機率 |
| 主腦 LLM | 解釋、工具選擇、呈現限制 | 不手改中心/機率/ensemble 權重，不創造不存在的訊號 |

動態集成已有依 loss、calibration、failure rate、sample shrinkage 計算權重的設計。不要另造一套；驗證它使用的績效窗口是否在預測時已可用，並比較 equal-weight 與 best baseline。模型分位數的平均只可作研究摘要，不自動成為 mixture predictive quantile。

## 5. 凍結架構與目前門檻

| 元件 | schema |
|---|---|
| as-of、session truth、factor routing | 2A.2 |
| gap/session | 2B.1 |
| daily labels | 2C.2 |
| state machine | 2D.4 |
| extension/exhaustion | 2E.3 |
| catalyst response | 2F.3 |
| sequential updating | 2G.2 |
| prediction audit DB | 2H.3 |
| evaluation governance | W3.1 |
| calibration evaluation | 2I.1 |
| Price/Probability Map | 3A.2.3 |

V2-I 2I.1 是 evaluation engine，不是 fitting。已具 manifest、artifact/outcome pairing、typed rejection、Brier/log-loss/reliability/ECE/MCE、point/quantile/interval 評估；adapter 只可出 `INSUFFICIENT_EVIDENCE` 或 `EVALUATED_UNCALIBRATED`。`MIN_PROBABILITY_SAMPLES=2` 是計算描述統計的程式下限，不是足以認證機率的統計門檻。

公開研究狀態文件記錄：Osaka direct historical bars 有統計預測證據，但不可成交且沒有經濟優勢；proxy OOS 無證據；forward 尚未建立已驗證優勢；台股/台灣指數不得繼承 Osaka 成績。這些是 repo 中的狀態，這次未重算其研究實驗。歷史報告按資料集/階段解讀，不能把不同 scope 的證據混成全系統結論。

`AUTO_TRAIN / AUTO_FINE_TUNE / AUTO_PROMOTE = false`；`RESEARCH_ONLY / NO ORDER` 保持。新增行情不會自動訓練，也不等於已累積足量樣本。

## 6. 元大最新狀態必須分兩個層次

**歷史 PR #53 回報：** SPARK securities login 0001，TAIFEX/OSE subscription accepted 無 callback；futures profile 0112。保留為歷史證據。

**已合併 PR #54：** guide/matrix 記錄 SPARK 證券 profile 已收到 TAIFEX/OSE/CME/CBOT/CBOE/NYBOT matching callback，Legacy Quote 國內 T+1 也成功；目前 recorder 狀態檔可見活動。這批原功能已在 PR #54 發布；本次修補未重新做各市場 live probe。

三個 family：

1. SPARK securities profile 可支援多市場行情；不代表 futures profile 權限開通。
2. YuantaQuote COM 是獨立的 32-bit 行情 sidecar；不是 YuantaOrd。
3. YuantaOrd trading API 不接 runtime，不查帳務、不下單。

SPARK 日/夜碼與 Legacy 盤別規則不能互換。9/24 guide 指出 SPARK 可能要 PM 代碼；Legacy T+1 仍用 base symbol 加 ReqType=2。不要永久硬編當天代碼。

NQ/ES 不是現貨指數，VX 不是 VIX cash，JY 不是 USDJPY spot，ZN/ZF 價格不是殖利率。保留 representation 與方向/單位，不能直接替換原因子。

## 7. 跨對話需要真正維護的檔案

沿用 `AGENTS.md`、`scripts/agent_bootstrap.ps1`、`docs/development/AGENT_HANDOFF.md` 和 `project-status.md`，不要再造互相競爭的狀態中心。建議當前摘要只保留目前 phase/next/gates/evidence；歷史長報告留 research 目錄。

每棒交接最少包含：時間、repo/branch/HEAD/dirty、build_id、完成範圍、測試命令和 exit code、未驗證項、資料/校準/優勢狀態、commit/PR/remote/CI、下一工作包與復原方法。若工作樹有新修改，必須列出不能由 published HEAD 代表的檔案。

ChatGPT 專案資料來源是上傳快照，不會因 GitHub push 自動變成新版本。每棒另產出更新快照，提醒使用者替換舊檔。不要保存帳號、WinCred、行情全集或私有報告內容到雲端。

截圖顯示「僅限專案記憶」，「已停用」在庫存取權欄位；不能依此前述「記憶功能停用」當真。即使專案能參考其他對話，也不應依賴它逐字記得每個工程決策。官方說明：https://help.openai.com/en/articles/10169521-projects-in-chatgpt

## 8. 下一棒

先核對 PR #55/HEAD/dirty/remote SHA 與現場 recorder。W2 離線鏈與 W3.1 governance engine 已完成，不要重做。下一個不需維護窗口的工作是把真正的 precommitted forward prediction/outcome cycle 接到 2H.3/W3.1 並開始累積可稽核樣本；若使用者提供維護窗口，則可先按尾端落盤/rollback/單一 owner 步驟受控交接 recorder。W4 fitting 仍須等足夠真實成熟樣本；不因 tests PASS 或 recorder RUNNING 就宣稱 DATA READY、CALIBRATED 或可準確交易。
