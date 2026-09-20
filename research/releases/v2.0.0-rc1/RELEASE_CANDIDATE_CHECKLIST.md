# Release Candidate Checklist（Phase 2 正式發布前）

> 狀態：PASS / PASS_WITH_LIMITATION / DEFERRED / BLOCKED（不用模糊的 DONE）。

## CORE
- [PASS] 全 regression（`pytest tests/`）。
- [PASS] clean core（無 optional integration 仍可 import / MCP / packet）。
- [PASS] build_id `ccabe1e1552d9ae7`。

## DATA
- [PASS_WITH_LIMITATION] JPX Micro settlement / volume / OI = LIVE_VERIFIED。
- [PASS_WITH_LIMITATION] per-contract OHLC = CONTRACT_ONLY（不假造完整 history）。
- [DEFERRED] 完整 OSE Micro OHLC history（官方無文字來源）。

## MODELS
- [PASS] Chronos-2 / TimesFM / XGBoost / LightGBM / NHITS / NBEATSx runtime 一致。
- [PASS_WITH_LIMITATION] Kronos-TW / Sundial / Moirai / TTM / FinCast = disabled /
  license_restricted / dependency_blocked / registered_only。

## FORECAST
- [PASS_WITH_LIMITATION] Dynamic Ensemble = RESEARCH / UNVALIDATED_FORWARD（未宣稱提升）。

## STRATEGY
- [PASS] Historical Strategy Research Engine（Edge Store / walk-forward / cost）。

## AUTOMATION
- [PASS] 自主循環 dry-run（status/tick/catchup）。
- [PASS_WITH_LIMITATION] realtime Tick/L2 關機無法事後補回（documented）。

## MCP
- [PASS] 21 tools（runtime introspection，非手寫 count）。
- [PASS] 無 order / login / credential / broker tool。

## SKILLS
- [PASS] 3 skills（osaka-micro-analysis / taiwan-stock-v28 / model-validation-audit）。
- [PASS] MCP tool 名稱存在、無 credential 引用。

## TRADINGVIEW
- [PASS_WITH_LIMITATION] OPTIONAL、enabled=false；免費方案 15 分鐘延遲。
- [PASS] upstream pin `c05b8f5755...`；MIT source（data/software 非 MIT）。

## YUANTA
- [PASS_WITH_LIMITATION] 證券 Spark AUTH_VERIFIED；期貨 Spark 0112（contradiction，未解）。
- [PASS_WITH_LIMITATION] Legacy Quote T+1 SERVER_CONFIRMED；T = REQUIRES_SESSION_AWARE_RETEST。
- [PASS] Trading API DOCUMENTED_ONLY / NOT_IMPLEMENTED / NOT_IMPORTED。
- [PASS_WITH_LIMITATION] JNU public code VERIFIED；SPARK StkCode / COM symbol / order code UNVERIFIED。
- [DEFERRED] Legacy Quote T session retest（正常 T 時段）。

## SECURITY
- [PASS] OrderApiExposureGuard PASS；secret scan 無真實 PII（僅 false positive）。
- [PASS] 無 order API 暴露；credential 只在 WinCred + process memory。

## LICENSE
- [PASS] LICENSE Apache-2.0；THIRD_PARTY_NOTICES（code/weights 分開）。

## RECONSTRUCTION
- [PASS] `reconstruct_verify.ps1` → PASS。
- [PASS] clean-clone simulation（source copy + 新 venv + import/MCP smoke）。

## DOCUMENTATION
- [PASS] 11 份 Yuanta docs + AI_RECONSTRUCTION_GUIDE + SYSTEM_MANIFEST + capabilities。
- [PASS] 無 stale current claim（13 tools / ^N225 primary target / 0112=wrong family 已清）。

## CI
- [PASS_WITH_LIMITATION] `.github/workflows/ci.yml`（CPU / no broker / no credentials / no live）。

## PUBLICATION
- [PASS] PUBLICATION_FILE_MANIFEST.txt / PUBLICATION_EXCLUDE_MANIFEST.txt。
- [BLOCKED-DEFERRED] GitHub push / release / tag（本棒禁止；下一棒才發布）。
