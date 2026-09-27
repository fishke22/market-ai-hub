# 免費來源與工具施工流程

核對日期：2026-09-27。以下為免費可閱讀的官方文件／開源碼；免費閱讀、開源授權、模型權重授權、行情使用／再散布權、broker entitlement、運算成本是不同事情。未宣稱所有服務、資料歷史或範例 API 都免費。施工時固定版本後重核 license 與對應 docs，不直接跟 main 自動升級。

## 來源與選型依據

| 來源 | 使用方式與免費界線 |
|---|---|
| [Qlib 官方 repository](https://github.com/microsoft/qlib)／[依賴宣告](https://raw.githubusercontent.com/microsoft/qlib/main/pyproject.toml) | 上游 mlflow<3.13 與 Hub research extra 3.16.1 衝突；隔離 adapter env，不把核心降級 |
| [FinRL-X 官方](https://github.com/AI4Finance-Foundation/FinRL-Trading) | 開源 weight-centric framework；FMP／WRDS／Alpaca 等範例整合不是免費必要條件，也不代表支援元大 JNU |
| [FinGPT 官方](https://github.com/AI4Finance-Foundation/FinGPT) | 金融 NLP／事件抽取參考；逐一檢查模型卡、base model 與資料集條款，不默認商用與再散布都允許 |
| [FinRobot 官方](https://github.com/AI4Finance-Foundation/FinRobot) | 多 agent 金融分析架構參考；若依賴付費 LLM/API，改用已存在的合規免費本地路徑或不啟用 |
| [LEAN 開源 engine](https://github.com/QuantConnect/Lean)／[LEAN CLI 官方前提](https://www.quantconnect.com/docs/v2/lean-cli/key-concepts/getting-started) | CLI 要付費 organization；免費路徑只評估 engine 原始碼，不能承諾 CLI／cloud 免費 |
| [NautilusTrader 官方](https://github.com/nautechsystems/nautilus_trader) | 目前 main/docs 指向 v2 release candidate；官方不建議 RC 控制真實資金。研究可固定版本，別把 --pre 當生產安裝 |
| [vn.py 官方](https://github.com/vnpy/vnpy) | 備選 adapter 參考；broker gateway／資料商／商業模組另行核對，不整套搬入 |
| [FreqAI 官方說明](https://www.freqtrade.io/en/stable/freqai/)／[Freqtrade LICENSE](https://github.com/freqtrade/freqtrade/blob/develop/LICENSE) | 參考重訓與 backtest patterns；crypto 範例不可直接套 JNU；授權相容性審查後才可能引用碼 |
| [scikit-learn calibration](https://scikit-learn.org/stable/modules/calibration.html) | 可靠度曲線與校準；fit/calibration/test 分離；低 Brier 不單獨證明校準良好 |
| [TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html) | 可使用 gap，但不會自動知道本專案 label 區間、publication lag 或 purge 規則；需按 horizon 實作檢查 |
| [LightGBM parameters](https://lightgbm.readthedocs.io/en/stable/Parameters.html) | 既有依賴可先做 quantile challenger，安裝版 API 要另核對；不必先添新模型套件 |
| [JPX Daily Report](https://www.jpx.co.jp/english/markets/statistics-derivatives/daily/index.html) | 免費公開統計入口，約次營業日09:00 JST；假日統計合併發布，不能推論完整盤中資料或假日獨立清算價 |
| [JPX 假日交易](https://www.jpx.co.jp/english/derivatives/rules/holidaytrading/index.html) | OSE 與 TSE 現貨不同日曆；9/21–23/2026 開市，資料發布日期與交易日期不同 |
| [JNU 官方合約規格](https://www.jpx.co.jp/english/derivatives/products/domestic/225micro-futures/01.html) | multiplier JPY10，tick5點；任何成本／paper adapter 要依版本化合約規格運作 |
| [ChatGPT Projects 官方說明](https://help.openai.com/en/articles/10169521-projects-in-chatgpt) | 專案 Instructions 與 Sources 可放持續上下文；不能假設每次都讀到所有舊聊天，仍以短索引與 repo 交接建立可恢復性 |

上面之外的 GARCH、change-point、conformal 或新聞來源，只有工作包確實需要才補官方來源、授權與成本紀錄；本次不下載新權重、購買行情或新增付費服務。

## WebCodex 主施工

本次已實測 `runtime_status` 與 `work_on_project` 的查詢：online runner、service v0.4.1、正確 MARKET_AI_HUB repo。實際 exposed tool 名稱由應用程式提供；不得猜 shell API 或參數。

1. 新對話先發現 WebCodex 工具，呼叫 runtime_status，再 work_on_project；透過列出的 project identity 選 MARKET_AI_HUB，不沿用過期 session id。
2. 要求 project instructions/workflow；讀 AGENTS.md、AGENT_HANDOFF、project-status、本包 01/02/05，再讀當次需要的 module。先實測 branch、HEAD、origin、dirty files、build、資料根，不用 PDF 的舊 HEAD。
3. 使用 read_files/search_project_texts 小批量查詢；差分用 apply_text_edits/apply_patch；run_process/run_shell 按實際 schema 執行。長工作以 job id/observe_jobs 追蹤，讀 tail，不每次回傳整份 log。
4. 同一 repo 只有一個 writer。避免平行 heavy pytest／模型載入；使用 bounded output，將完整 log 留本機並回報路徑／exit code。
5. finish_coding_task 的 summary_only 可作最後輔助 snapshot，但它不替代實際 diff、測試、commit/push、CI 或 live runtime 採用證據。

未確認可用的 WebCodex 功能不在 prompt 中假定存在。本機 Codex可直接做檔案／Git／測試，不必繞遠端桌面。

## Remote Desktop Commander 備援

只有 WebCodex 不可連、必要操作工具缺失或確定 job 無法執行時，才使用當前實際暴露的 Remote Desktop Commander 工具。先確認上一個 job 是否仍在執行／是否已寫檔，避免兩邊重複施工。確認同 repo／branch／HEAD／dirty files 後接續同一工作包。備援連線本次未測，不宣稱已驗證。

兩者都不能執行時，保留 checkpoint，輸出「一個工作包」的可回貼施工 prompt，列允許檔案／禁止事項／精確驗收命令／預期報告格式。若使用者仍要 OpenCode Desktop，先查 [官方文件](https://opencode.ai/docs/) 與本機版本、模型列表；使用者過去稱呼的 DeepSeek-v4-flash 4.1 high/max 不當作已驗證 model ID／推理 enum。不要杜撰設定鍵、修改全域 provider 或默默改模型。

## 跨對話持續記錄

repo 交接是動態單一來源；上傳文件是有日期的快照。每次完成工作包更新：HEAD/build、完成／未完成、test command/count/exit、資料證據來源、未讀／不可達路徑、下一包目標、PR/CI。更新後輸出一份精簡的可替換來源文件；使用者在 Project Sources 移除或清楚標示舊版本。不得宣称工具已自動替使用者更新 ChatGPT 專案來源，除非真的做了該操作。
