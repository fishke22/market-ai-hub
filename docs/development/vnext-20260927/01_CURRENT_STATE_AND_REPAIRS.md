# MARKET_AI_HUB：2026-09-27 稽核與接續基準

本文件取代舊 PDF、9/24 報告及較早聊天中的「目前狀態」。這是版本化快照，不是永久記憶；每次施工仍以實際 Git、程式、資料與測試重新確認。附件內的命令與停止條款只作設計參考，並未直接執行。

## 本次範圍與身分

- 實際程式庫：`D:\MARKET_AI_HUB`，遠端 https://github.com/fishke22/market-ai-hub 。路徑是本機定位資訊，不得成為新程式的固定依賴。
- 稽核起點 main：`ff109f22c86895ee2c8b719bd8fcf986b859adf0`，含 PR #72、#73。
- 修復分支：`codex/vnext-audit-handoff`。修復後 runtime source build：`dff534ae24a053c7`。Git commit／PR／測試最終結果見本包 `05_DELIVERY_EVIDENCE.md`。
- 檢查了治理交接、V2/W3/W4/W5 狀態、JNU direct、歷史回放及封存、共用 quantile 與 feature 邊界、路徑解析、相關測試、46 頁舊 PDF、新 vNext 全文及上游官方資料。這不是對所有外部 API、模型權重、每個 runtime 分支的無錯誤保證。
- 全程未操作券商登入、下單、帳戶／部位／餘額，未停止或接管現有 recorder，未重新計算已打開的最終留出集，未安裝新框架。
- 原有未追蹤 `scripts/register_jpx_micro_sync_task.ps1`、`scripts/run-hidden.vbs` 保留；不屬本次提交，也未執行排程註冊。

## 已修正的錯誤

| 問題 | 原本後果 | 修復與可重現檢查 |
|---|---|---|
| 回放把下一筆資料當下一 OSE 交易日 | 缺假日資料時，多日價格變化被當 1d 評分 | builder 檢查 OSE 下一交易日；讀取旧封存摘要同樣檢查，違反則 BLOCKED_HORIZON_MISMATCH，不重新評分 |
| 最終留出 CLI 在檢查封存前呼叫模型 | 重跑指令可再次打開 final；事後拒寫也阻止不了偷看 | 先讀已有封存；沒有才獨占建立 FINAL_HOLDOUT_ATTEMPTED，再載入模型；失敗不自動刪 marker 重試 |
| 相同 evidence_id 但預測內容不同仍當冪等 | 變動被掩蓋；同時首次寫入也可能互相覆蓋 | 完整內容相同才接受冪等；exclusive create；NaN 不可 JSON 封存；中斷殘檔需人工稽核，不自動覆寫 |
| 只因 training_cutoff 有字串就標 CLEAN OOS | 截止日比測試晚或無法證明 publication availability 也可能被升級 | 已知字串只標 OOS_NOT_VERIFIED；未知仍 TRAINING_CUTOFF_UNKNOWN；不自動認證 |
| 預測路徑未嚴格檢查 | inf、交叉分位、非正價格、錯誤 horizon 可進入 JNU ensemble／回放績效 | 共用 validate_price_path：三分位長度必須吻合、逐步有限／正值／有序；共用 scalar quantile 拒絕 inf；資料清算價排除 inf |
| cross_market_features 使用整數列索引對齊時間索引 | 正常輸入可能全部變 NaN；重複時間混淆資料 | 依 timestamp 對齊各商品序列、拒絕重複 symbol/time |
| pct_change 預設補值 | 缺價／零價被偷偷補成前價，製造報酬資料 | 明確 fill_method=None，維持缺值；後續由模型／資料契約決定缺值策略 |
| HPQ1 可接受非 1 步 protocol | metrics／target 仍只算一步 | 非 1 步與空模型集合直接拒絕 |

回歸檢查集中 `tests/test_vnext_evidence_guards.py`；沿用原有測試架構，未新增測試框架或依賴。

## 重要：已存在的歷史證據降級

本機 SEALED.json evidence ID：`3f28cec82268445d7d377356`。
SHA256：`56bddc0d409f89eab8885bdd7bc91ed8df169c0b21ed658100c2c6f708a3341e`。

原檔有 131 個 origins（43 development、40 validation、48 final），兩模型共用這些 origins。其中 **2026-09-18 → 2026-09-24** 不符合 next OSE session；下一交易日是 **2026-09-21**，21／22／23 都有假日交易。官方 Daily Report 對假日資料有合併發布規則，因此不能假裝每個交易日都有獨立清算報價。來源：[JPX 假日交易](https://www.jpx.co.jp/english/derivatives/rules/holidaytrading/index.html)、[Daily Report 發布說明](https://www.jpx.co.jp/english/markets/statistics-derivatives/daily/index.html)。

原報告 final MASE 1.1228、CI [-24.34,229.28]、coverage 0.8333 是**歷史存檔數字**，現在不得作為已通過 horizon 檢查的一天期證據。新摘要阻擋整批，不挑掉不利樣本後宣稱重新通過。封存檔保留不變；final 已看過，不能再命名為 untouched final。若要產生修正診斷，可在新 protocol 下明確標 POST_HOC_DIAGNOSTIC，不能替代新預先登記的 forward／holdout。

## 現在到底完成什麼

- V2-A..I、2H.4 audit、W3.1 governance、W3.2 forward-cycle、W3.2-EP1 event producer、W4.1 calibration fitting、W5.1 first-passage 的**引擎已存在**。不可重建同義系統。
- C2.3 recorder adoption 曾完成；舊 PDF 的「尚未 adoption」已過時。但本次未重新驗證或切換 live recorder 的版本。
- 本次實際只讀 actual_evaluation_readiness 回報預設 audit DB 不存在、settled event probability samples=0、INSUFFICIENT_EVIDENCE／NONE_YET，且沒有建立DB。這不等於其他自訂資料根也沒有資料；本次沒有啟动收集或新增樣本。
- W4 的 50 calibration + 50 validation + 50 final，以及每類／時間跨度等，是既定 protocol 門檻，不是「150 筆就精確」的統計定律。不同商品／事件／horizon 要分開；不能為湊數混用。
- Chronos／TimesFM 目前仍是研究 challenger，不能靠增加模型數變得可信；training cutoff 未知仍要如實標示。
- SPARK 的 API 支援範圍、帳戶 entitlement、登入、訂閱接受、live callback、持續歷史覆蓋各自獨立。9/24 的 NO_CALLBACK 不自動覆蓋較新的 recorder 證據，也不能把較新的個別 callback 推廣到所有商品。
- WebCodex 本次 status 及 work_on_project 身分讀取成功：服務 v0.4.1、runner online、定位正確 repo/HEAD。這證明連線與讀取，不等於已用 WebCodex 遠端寫入和跑完測試；修復在本機 Codex 完成。

## 尚需處理的設計限制（不得寫成已實作）

1. 決定 next trading session 與 next published settlement 兩種目標，分開 identity／日曆；Daily Report 約次營業日 09:00 JST 才發布，15:45 的合成 session timestamp 不代表當時資料可取得。
2. 現行 front selection 以有可評 outcome 的 eligible contracts 選最近月份；新 protocol 要在 origin 先選合約再等待 outcome，避免依未來資料可得性換合約。
3. cross-market helper 現在能正確對齊時間，但**尚不是 point-in-time join，也未接入 JNU 價格模型**。必須另做 availability、staleness、representation gates，不能直接拿寬表宣稱完成跨市場 AI。
4. 近期 direct historical validation cache 的 identity／來源修訂失效策略應於資料契約工作包檢查；日期與樣本數相同不必然代表來源相同。不可用 cache 升級證據。
5. 安裝可搬移仍要重建 venv、重設 OS task／MCP launcher／SDK 依賴；WinCred 密鑰不隨資料夾複製。程式已有 canonical path resolver，但尚未做新磁碟乾淨機完整驗收。
