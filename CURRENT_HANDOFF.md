# MARKET_AI_HUB — CURRENT HANDOFF

- Current phase: V1.1 FINAL VALIDATION & RUNTIME CONSISTENCY REMEDIATION — 完成
- Gate: READY_FOR_V1_PROMPT_FREEZE
- Current build_id: e77d9c9a2f0a015b（code 變更後會變，見 services/build_info.py）
- Last updated: 2026-09-19

## 本輪完成重點（V1.1）
1. Runtime consistency root cause：Cherry Studio long-running MCP process 持有啟動時程式碼
   （log 證據：舊 server.py line 225 crash traceback）。修法：build fingerprint +
   process singleton + 使用者重啟流程（見 V1_1_FINAL_VALIDATION_REPORT.md §1）
2. Build fingerprint：health_check/get_system_info/gates/predict_*/analyze_* 全帶
   build_id / source_root / python_executable / server_started_at
3. Quantile contract：p10<=p50<=p90 或 NOT_AVAILABLE；分類器不假裝有 quantile
   （lower/upper_reference 取代）；invalid quantile 不進 ensemble
4. Model task：PRICE_FORECAST（chronos/timesfm/fincast）vs DIRECTION_CLASSIFICATION（xgb/lgbm/lr/rf）
5. Ensemble：price_ensemble / direction_ensemble 分層；component_table（role/eligible/weights/excluded_reason）；
   legacy 欄位 legacy_research_only=true；validation_level=RESEARCH
6. Count semantics：independent_base_model_count=4 / eligible_direction_vote_count=0 /
   eligible_price_reference_count=2（不再混成一個數字）
7. Target calendar：XTKS 日曆（2026-09-21~23 日本連假正確跳過）；
   requested_dates → CALENDAR_TARGET_MISMATCH（OSE Holiday Trading 不映射）。
   **修掉 1970 epoch 日期 bug**（之前用整數 row index 當日期）
8. OOS validation：rolling origins + 3 baselines + interval coverage/calibration_error；
   deterministic PROMOTION_RULES（code 內）；結果存 ts_validation.duckdb。
   實測 chronos 12-fold MASE 1.94 → UNVALIDATED（誠實）
9. Gates：evaluated_at + build_id + evidence，每 call 基於 current runtime

## Tests
- pytest：125 passed（111 unit + 14 integration）
- smoke_mcp：PASS（13 tools）
- acceptance_v1_1：8/8 PASS（Cherry Studio 完全相同啟動命令）
- 報告：reports/v1_1_acceptance.json、V1_1_FINAL_VALIDATION_REPORT.md

## 使用者下一步（重要）
- 在 Cherry Studio 把 market-ai MCP 開關關掉再打開（或重啟 Cherry Studio）
- 驗證：health_check → build.build_id == e77d9c9a2f0a015b

## Known limitations
- TS 模型 UNVALIDATED（12-fold 未打敗 naive）；TW 日期 WEEKEND_ONLY_APPROX；
- classifier proba 未 calibrated（已標記）；OSE micro 資料仍需付費來源（本專案不購買）
