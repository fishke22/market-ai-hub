# Known Limitations

記錄**真正現存**的限制。已修問題不列入。

分四類：EXTERNAL / OPTIONAL CONFIG / RESEARCH LIMITATION / RUNTIME LIMITATION。

## EXTERNAL（外部資料／授權，非本倉庫可控制）

- Direct OSE Micro settlement 歷史不足：JPX 官方僅提供當日 current-day CSV，歷史 settlement 404。
- Chronos / TimesFM weights 需首次下載（HF Hub）；無 HF_TOKEN 時為 unauthenticated（rate limit 較低，非功能受限）。
- TimesFM-3.0 為非商業授權（TIMESFM3_NON_COMMERCIAL_ONLY）。

## OPTIONAL CONFIG（選用能力，未設定時顯示 unavailable，不影響 core startup）

- 225LABO minute 資料 ingest：`data/ylab225_ingest.py` 的 `INBOX` 為本機絕對路徑（`D:\MARKET_AI_HUB_PRIVATE_INBOX\225labo`）；需本機手動提供 zip。未提供時 ingest 為 unavailable（core MCP startup 不依賴它）。
- Yuanta 盤後行情：需本機 Yuanta SDK / COM / 憑證；未安裝時顯示 DISABLED。
- TradingView bridge：OPTIONAL_NOT_INSTALLED。

## RESEARCH LIMITATION（研究結論，非 bug）

- Historical statistical signal（VAR MASE=0.958）非可執行 edge：edge 85.2% 在 gap，需當日 full close（pre-close 崩潰 41.3%）。
- Forward evidence NONE_YET（225LABO 資料 19 天 stale）；registered/pending ≠ validated Forward samples。
- Trading Readiness = RESEARCH_ONLY；無 strategy / production candidate。

## RUNTIME LIMITATION

- build_id 為 fingerprinted source 檔內容 hash：任何 source 修正都會改變 build_id（這是 feature，非 bug）。
- forecast result cache 為 process-level TTL（300s）：跨 process 重啟不保留；新資料（data hash 變）自動 invalidates。
- MCP_PERF_TRACE 預設關閉；需 env 開啟。
