# PUBLICATION DIFF SUMMARY

> 相對目前 public V1（build `bbf3cb2f9a80d20e`，13 tools，^N225 target），Phase 2 新增/更正。

## 新增（Phase 2）

| 面向 | 內容 |
|------|------|
| Architecture | 官方資料源 → Data Lake → Feature Store → Regime → Direct Models → Tournament → Joint/Scenario → Analysis Packet |
| Data providers | TWSE / TAIFEX / FinMind / BOJ / FRED / CFTC / J-Quants / USTreasury / Cboe / BLS / JPX settlement + proxy |
| Models | Chronos-2 / TimesFM-3.0 / XGBoost / LightGBM / fincast（NHITS/NBEATSx training-only blocked） |
| Validation | 完整 walk-forward OOS + cost stress + causality audit + forward shadow |
| MCP | 21 tools（含 get_analysis_packet / predict_* / get_forward_test_status） |
| Skills | osaka-micro-analysis / taiwan-stock-v28 / model-validation-audit |
| Yuanta docs | 四條 API family + SPARK StkCode (JNU<YYMM>) + Legacy Quote/Trading 分離 |
| Forward Shadow | 每日 forecast + registry + drift monitoring infrastructure |
| Resource Governor | DESKTOP_SAFE 預設（不獨占 GPU/CPU/RAM） |

## 更正（相對 V1）

| 舊 | 新 |
|----|----|
| ^N225 為 primary target | `OSE_NIKKEI225_MICRO_FUTURES` 為 primary（^N225=PROXY） |
| 13 MCP tools | 21 MCP tools |
| 未揭露 research 結論 | 明確：VAR 有統計訊號但 NON_EXECUTABLE / NO_ECONOMIC_EDGE |
| NHITS/NBEATSx "available" | runtime blocked（training-only） |
| 無 resource governor | DESKTOP_SAFE 預設，AUTO_TRAIN=false |

## 不變

- V1 history 保留（HISTORICAL V1 SNAPSHOT）。
- NO LIVE TRADING / NO ORDER / NO BROKER CREDENTIAL。
- 無 production trading candidate。
