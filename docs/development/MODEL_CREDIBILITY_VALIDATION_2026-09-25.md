# 本輪模型可信度修正：驗證紀錄

- 日期：2026-09-25。
- 起始 HEAD：b56723357e7538309aba096013804781eb0a520c。
- 程式／測試修正 commit：ea29c12af8bdffb36bbaa1dd8275d445fc7135a0。
- 修正 runtime build：eca898aa6fc222c2。
- 分支：codex/quote-hub-correctness；既有 PR：https://github.com/fishke22/market-ai-hub/pull/55 。PR open，不等於已 merge；遠端 CI 需以最新 head 查詢。

## 實際測試

1. 四個初始 regression 在修正前全部失敗：季節 horizon、interval alignment、invalid quantile flag、同族不同 label 綁定。
2. 固定假 confidence interval regression 在修正前失敗。
3. XGBoost/LightGBM origin regression 在修正前各失敗：訓練 rows 原為 [0,1]、預測 row=1；正確為已成熟 rows [0,1,2,3]、預測 row=5。
4. 最終相關測試：**172 passed, 3 deselected in 34.45s，exit 0**。
5. 最終完整離線 profile：**1785 passed, 34 deselected, 110 warnings in 120.14s，exit 0**。
6. changed-file secret pattern scan：0 findings；git diff --check：PASS。這是既有 scanner 的變更檔案範圍，非宣稱全庫沒有任何秘密。

相關測試命令（repo 根目錄、專案 Python）：

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_tournament.py tests/test_v2i_calibration_evaluation.py tests/test_v2h2_forecast_artifact.py tests/test_w3_evaluation_governance.py tests/test_w32_forward_cycle.py tests/test_phase2c.py tests/test_challengers_2d1.py tests/test_research.py -q -p no:cacheprovider -m 'not live and not optional_model and not private_data and not broker_diagnostic and not integration'
```

完整離線測試另設定 PYTHONIOENCODING=utf-8、PYTHONDONTWRITEBYTECODE=1、HF_HUB_OFFLINE=1、TRANSFORMERS_OFFLINE=1，MARKET_AI_DATA_ROOT 指向工作區隔離測試資料目錄，不使用實際行情 data root：

```powershell
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider -m 'not live and not optional_model and not private_data and not broker_diagnostic and not integration and not optional_integration'
```

較早的 default-profile 執行未完成並已停止，只停止本輪精確識別的 pytest processes；不能列為 full default suite PASS。上列是完成的 offline profile，排除項目明列，不等於 live、私有行情、大模型權重、broker 或 UI E2E 通過。測試總數不可直接和 W3.3 的 default-profile 1789 相減解讀。

## 已修正與未證實的界線

- 本輪修正五類問題，詳見 MODEL_CREDIBILITY_PLAN_2026-09-25.md；新增回歸是合成資料，不能當成市場績效。
- 未新增或下載模型，未 fitting calibration，未建立真實 forward 預測，未重新計算歷史市場排行榜。
- 未執行 broker login/logout/restart/訂閱／tick query，也未讀取或輸出憑證。
- 起始已有 staged W3.3 contract/report 兩檔；刻意保持它們原狀，未併入本輪 commit。工作樹因此不是 clean，不能誤報。
- 下一步 C1 尚需處理其他比較／拒答／基準語義邊界，C2 需來源與受控維護窗口，C3/C4 需真實資料與事前驗證協議。不要因本輪測試通過便自動開啟概率發佈。
- 現有五觀測季節基準、八成 nominal interval 評估仍是既有 adapter 契約；不是任意頻率或任意分位數通用引擎。

## 使用文件

將本文件與 MODEL_CREDIBILITY_PLAN_2026-09-25.md 上傳 ChatGPT 專案資料來源，再把 CHATGPT_MODEL_CREDIBILITY_PROMPT.txt 全文貼到新對話。它們補充舊 context pack；本輪 snapshot 和當前 repo 優先於旧 pack 的進度描述。後續每次都重新核對 HEAD。
