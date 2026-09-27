# 本次交付與驗收證據

日期：2026-09-27。基底 main `ff109f22c86895ee2c8b719bd8fcf986b859adf0`。
分支 `codex/vnext-audit-handoff`；runtime source build `dff534ae24a053c7`。

## 已驗證

- 最終程式重點測試：**91 passed, 2 deselected，exit 0**，16.14 秒。
- 第一輪完整離線測試：1994 passed、1 skipped、35 deselected、110 warnings，exit 0；之後新增 cross-market 回歸檢查且修正特徵處理，以上91項已涵蓋最終修改。最終完整輪另行記錄於下方。
- 實際 guarded replay CLI：直接回傳 `BLOCKED_HORIZON_MISMATCH`，沒有重跑模型。CLI exit 0 表示讀取成功，不代表統計證據通過。
- SEALED.json 修改前後 SHA256 都為 `56bddc0d409f89eab8885bdd7bc91ed8df169c0b21ed658100c2c6f708a3341e`。
- actual_evaluation_readiness：db_present=false、prediction_count=0、settled_event_probability_samples=0、INSUFFICIENT_EVIDENCE／NONE_YET。沒有建立預設DB；未推論其他資料根。
- WebCodex status/work_on_project 成功，runner online且repo身分一致；remote write/test、Remote Desktop Commander fallback、網頁Sources上傳未執行。
- git diff --check 通過。Windows Git 的 CRLF→LF 提示是文字正規化提醒，非測試錯誤。

## 可重跑的命令

於實際repo根目錄用既有 `.venv/Scripts/python.exe` 執行；新磁碟先重建venv。設定 PYTHONIOENCODING=utf-8、PYTHONDONTWRITEBYTECODE=1、HF_HUB_OFFLINE=1、TRANSFORMERS_OFFLINE=1。完整離線輪另設定 MARKET_AI_DATA_ROOT 到獨立的測試暫存資料根，避免碰正式行情資料。

```text
.venv/Scripts/python.exe -B -m pytest tests/test_vnext_evidence_guards.py tests/test_historical_prequential.py tests/test_jnu_direct_human.py tests/test_feature_sanitation.py tests/test_w2_feature_packet_wiring.py tests/test_tournament.py tests/test_research.py tests/test_challengers_2d1.py -q -p no:cacheprovider

.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider -m "not live and not optional_model and not private_data and not broker_diagnostic and not integration and not optional_integration" -k "not test_single_instance_lock_releases_after_error"
```

全量排除 live/model/private/broker/integration；另排除會競爭實際 recorder 全域 owner mutex 的單項測試。不為跑測試停止收行情。這不是實際GPU模型推論、券商連線、乾淨機安裝、live runtime採用或市場績效驗收。

## 最終完整輪與發佈

- 最終完整離線輪：**1995 passed、1 skipped、35 deselected、110 warnings，exit 0，221.70 秒**。此輪開始前所有 runtime source 已完成修改；之後僅修改交接文件。
- warnings 為既有 datetime.utcnow 棄用提示，未把它們當作零警告。
- staged 19 files 的基本 token/private-key pattern 掃描未命中；這只是輔助掃描，不是完整安全認證。
- 程式／文件主提交：`97c9ef383fd5c67afe47d3fcf7cc63e7a76c004d`，已推送 `origin/codex/vnext-audit-handoff`。
- PR：[修復與 vNext 交接 #74](https://github.com/fishke22/market-ai-hub/pull/74)，保持開啟，未合併。
- GitHub CI 已觸發；本文件寫入時為 pending，不能當作 CI 通過。[即時 CI 狀態](https://github.com/fishke22/market-ai-hub/pull/74/checks)。文件包的 PUBLICATION_STATUS.json 記錄匯出時的最新觀測，不自動等同之後狀態。
- 主提交後只有發佈資訊文件更新；runtime build 不變。兩個原有 untracked 排程檔仍保留，本次 tracked changes 已提交。
