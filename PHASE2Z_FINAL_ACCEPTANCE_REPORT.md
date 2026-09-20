# Phase 2Z — Final Integration Acceptance + Release Candidate Validation

- Gate: **PHASE2Z_PASS**
- build_id：`ccabe1e1552d9ae7`（未變，本棒只改 docs/tests/non-fingerprinted）
- 測試：**503 passed**（494 + 9 2Z；5 live deselected）

## 1. Final architecture
三條主 path：Data Lake → FeatureStore/Regime → Model Tournament → Joint/Scenario →
Dynamic Ensemble → Strategy Research → Analysis Packet → MCP → Skills。
背景 path：Prediction Registry → Outcome Settlement → Automated Research Loop。

## 2. Primary target
- `OSE_NIKKEI225_MICRO_FUTURES`（^N225 只 PROXY/REFERENCE）。

## 3. Test count
- **503 passed**（154 V1 + Phase 2 各階段 + 9 2Z release acceptance）。

## 4. build_id
- `ccabe1e1552d9ae7`（未變）。

## 5. MCP 21 tools
- runtime introspection 確認 **21 tools**；無 order/login/credential/broker tool。

## 6. Skills 3
- osaka-micro-analysis / taiwan-stock-v28 / model-validation-audit；MCP tool 名稱存在、無 credential 引用。

## 7. Clean-core smoke
- 無 TradingView / Yuanta vendor / credential / optional key 仍可 import + MCP 21 tools +
  get_analysis_packet（clean clone venv 驗證）。

## 8. Clean-clone reconstruction
- `reconstruct_verify.ps1` → PASS。
- clean source copy（無 venv/data/models/vendor）→ 新 venv（minimal deps）→
  settings/mcp import OK → MCP 21 tools（get_analysis_packet 存在）。

## 9. Model registry
- Chronos/TimesFM/XGBoost/LightGBM/NHITS/NBEATSx 與 runtime 一致；
  Kronos/Sundial/Moirai/TTM/FinCast = disabled/license_restricted/dependency_blocked/registered_only。

## 10. Provider status
- JPX settlement/volume/OI + BLS/Cboe/EDGAR/BOJ LIVE_VERIFIED；BEA/e-Stat/EIA/EDINET NEEDS_CONFIG。
- **Provider request instrumentation**（新增 `provider_metrics.py`）：logical request /
  cache_hit / cache_miss / duration；關閉 2I-A observability gap。
- Dedup validation：cold=cache_miss、warm=cache_hit。

## 11. Prediction Registry
- forecast → settle → score → leaderboard；append-only outcome。

## 12. Archive
- get_analysis_packet 預設 archive hook；重分析新 record + supersedes，不 overwrite。

## 13. Automation
- status/tick/catchup dry-run；PC 關機可 catch-up（realtime Tick/L2 例外 documented）。

## 14. TradingView
- OPTIONAL、enabled=false、15 分鐘延遲；pin `c05b8f5755...`；MIT source（data/software 非 MIT）。

## 15. Yuanta
- 證券 Spark AUTH_VERIFIED；期貨 Spark 0112（CONTRADICTION，未解）；
  Legacy Quote T+1 SERVER_CONFIRMED、T REQUIRES_SESSION_AWARE_RETEST；
  Trading API DOCUMENTED_ONLY；JNU public code VERIFIED、其餘 code UNVERIFIED。

## 16. Yuanta deferred T retest
- `docs/YUANTA_PENDING_VALIDATIONS.md`（DEFERRED_EXTERNAL_VALIDATION，非 core blocker）。

## 17. Security
- OrderApiExposureGuard PASS；secret scan 無真實 PII（僅 false positive）；無 order API。

## 18. Licenses
- LICENSE Apache-2.0；THIRD_PARTY_NOTICES（code vs weights 分開）。

## 19. Secret scan
- 全 masked（false positive：BLS series ID / 假測試帳號 / .pfx 關鍵字 / doc 提及）。

## 20. Publication manifests
- PUBLICATION_FILE_MANIFEST.txt / PUBLICATION_EXCLUDE_MANIFEST.txt 齊全。

## 21. CI
- `.github/workflows/ci.yml`：CPU / no broker / no credentials / no live。

## 22. Remaining limitations（不阻塞）
- per-contract OSE Micro OHLC 無官方文字來源（settlement=close proxy）。
- Dynamic Ensemble UNVALIDATED_FORWARD；BEA/e-Stat/EIA/EDINET needs config。
- TradingView 15 分鐘延遲；SPARK Futures 0112 未解；OSE Micro StkCode UNVERIFIED。

## 23. Blockers
- 無 core blocker。

## 24. Final gate
- **PHASE2Z_PASS**（全 regression PASS + clean core PASS + MCP/Skills PASS +
  clean reconstruction PASS + secret/license/publication PASS；optional integrations 不阻塞）。

## 驗證
- `pytest tests/ -q` → 503 passed
- `reconstruct_verify.ps1` → PASS
- clean-clone（新 venv）→ settings/mcp import OK + MCP 21 tools
- build_id 維持 `ccabe1e1552d9ae7`
