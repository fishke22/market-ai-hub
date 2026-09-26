# MCP Tool Reference

由 runtime introspection 產生（21 tools）。

## health_check

- 用途：整體健康檢查：models / providers / 環境 / build fingerprint。
- 參數：無

## get_system_info

- 用途：Python / GPU / CUDA / models（role + task + dual status）/ ensemble / MCP tools / gates / build fingerprint。
- 參數：無

## get_research_gates

- 用途：Research validation gates：ENGINEERING_GATE / DATA_GATE / MODEL_PREDICTIVE_GATE / TRADING_EDGE_GATE。
- 參數：無

## get_data_source_status

- 用途：各資料來源狀態（TWSE/FinMind/FRED/yfinance/JQuants/TradingView/Broker）。
- 參數：無

## get_market_data

- 用途：取市場資料（yfinance symbols，或數字代碼走台股流程）。僅回傳結構化資料。
- 參數：無

## predict_chronos

- 用途：Chronos-2 多步預測。horizon "Nd" = N trading bars（1d/2d/5d/10d）。含 build fingerprint。
- 參數：無

## predict_timesfm

- 用途：TimesFM-3.0 多步預測（weights 非商業授權）。含 build fingerprint。
- 參數：無

## predict_ensemble

- 用途：Chronos + TimesFM + XGBoost + LightGBM ensemble。
- 參數：無

## get_model_performance

- 用途：讀取歷史 backtest 績效（model 空白 = 全部）。
- 參數：無

## backtest

- 用途：walk-forward backtest（yfinance 資料 + baseline 分類器）。
- 參數：無

## run_ts_validation

- 用途：時間序列模型 rolling-origin OOS 驗證（V1.1 pipeline）。
- 參數：無

## analyze_osaka_nikkei

- 用途：大阪日經 PROXY 分析（^N225 index + 跨市場；非 OSE micro 即時）。
- 參數：無

## analyze_taiwan_stock

- 用途：台股分析（如 2330 / 3706.TW / 華邦電）。只回傳 structured evidence。
- 參數：無

## get_analysis_packet

- 用途：正式分析封包（backend 先完成大部分工作）。
- 參數：無

## get_data_coverage

- 用途：大阪微型日經各 factor 資料覆蓋摘要（LIVE_VERIFIED/CONTRACT_ONLY/NEEDS_CONFIG/...）。不得隱藏缺口。
- 參數：無

## get_event_calendar

- 用途：近期重要官方事件日曆（BOJ/Fed/CPI/NFP/PCE/GDP/MOF），只回 Top-N。
- 參數：無

## get_official_release_snapshot

- 用途：官方 macro 來源狀態快照（LIVE_VERIFIED / NEEDS_CONFIG / CONTRACT_ONLY）。
- 參數：無

## get_target_instrument_state

- 用途：真正交易標的狀態（OSE_NIKKEI225_MICRO_FUTURES）+ Micro settlement + 角色標記。
- 參數：無

## get_model_leaderboard

- 用途：模型 leaderboard（tournament PerformanceStore，含 BEST_BASELINE）。
- 參數：無

## get_forward_test_status

- 用途：Forward test 註冊狀態；同時回報 W3.2 audit-side raw EVENT_PROBABILITY 累積狀態。
- 主要欄位：`forward_evidence_n`（舊 Prediction Registry settled model forecasts）、`w32_event_probability_registered`、`w32_event_probability_settled`、`w32_event_probability_pending`、`w32_event_probability_public_calibrated=false`、W4 最低 50/50/50 sequential sample 門檻。
- 注意：raw EVENT_PROBABILITY 計數不是 CALIBRATED；150 筆只是進入 W4 protocol 的最低樣本門檻，不保證 acceptance。
- 參數：無

## get_analysis_archive_status

- 用途：Analysis Archive 狀態（不可變分析 / append-only outcome / reanalysis）。
- 參數：無
