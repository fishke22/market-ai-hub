# MARKET_AI_HUB — CURRENT HANDOFF

- Current phase: **Phase 2Q-C.2（Target-Family Runtime Isolation + Taiwan Packet Correctness + Historical OOS Metric Correctness）**
- Gate: **PHASE2QC2_PASS**（最近；前置 PHASE2QC1_PASS）
- build_id：**1afb6888eec3fbdc**（未變；2Q-C.1 起）

## Phase 2 全歷程 Gate

| Phase | 內容 | Gate |
|---|---|---|
| 2A~2G.2 | Registry/Providers/FeatureStore/Regime/Tournament/自動化/Strategy/Joint/官方資料 | PASS |
| 2H | Analysis Packet + MCP 8 tool + Cherry Skills + Archive | PASS |
| 2I-A / 2I-B | 效能/準確度硬化 + Reconstruction Pack | PASS |
| 2T | TradingView Optional Bridge 實機驗證 | PASS |
| 2Y-A~2Y-G.1 | Yuanta 盤點/憑證/Spark/COM/sidecar/ground-truth/語義修正 | PASS |
| 2Z / 2Z.1 | Final Acceptance + Yuanta API family disambiguation | **PASS** |
| 2V-A | Real-World E2E Validation + Yuanta OneAPI version audit | PHASE2VA_PASS |
| 2Y-H | Yuanta Local SDK Forensics + Quote symbol/login/version closure | PHASE2YH_PASS |
| **2V-B** | Historical OOS Walk-Forward + Statistical Evidence Audit | **PHASE2VB_PASS** |
| **2V-B.1** | Local Historical Data Discovery + Direct Target Recovery Audit | **PHASE2VB1_PASS** |
| **2V-B.2** | Local OSE Micro Data Provenance Validation + Safe Import + Direct OOS Decision | **PHASE2VB2_PASS** |
| **2V-B.3** | Direct OSE Micro Continuous Bar Historical OOS Exam | **PHASE2VB3_PASS** |
| **2V-C** | Execution-Aware Strategy Validation + Cost Stress Test | **PHASE2VC_PASS** |
| **2V-C.1** | Gap Edge Causality + Pre-Close Executability Validation | **PHASE2VC1_PASS** |
| **2V-D** | Forward Shadow Validation + Drift Monitoring + Registry Hardening | **PHASE2VD_PASS** |
| **2V-E** | Forward Data Feed Readiness + Daily Operations + Phase 2 Research Freeze | **PHASE2VE_PASS** |
| **2V-F** | Compute Resource Governor + Safe Training Scheduler + Desktop Protection | **PHASE2VF_PASS** |
| **2P-A** | Final Publication Acceptance + Release Freeze + Clean Reconstruction Audit | **PHASE2PA_PASS** |
| **2P-B** | Beginner Ops Docs + Cherry Studio Guide + Final Publication | **PHASE2PB_BLOCKED**（remote mismatch） |
| **2P-C** | Remote Reconciliation + Client-Neutral Merge + GitHub Publication | **PHASE2PC_PUBLISHED** |
| **2P-D** | Agent Response Truthfulness Hotfix + Target Semantics Audit | **PHASE2PD_PUBLISHED** |
| **2P-E** | System Prompt Compaction + Skill Responsibility Cleanup | **PHASE2PE_PUBLISHED** |
| **2Q-A** | Runtime Truth Consolidation + Deterministic Direction + MCP Fast Path | **PHASE2QA_PASS** |
| **2Q-B** | Whole System Validation + Clean-Room Audit + Failure Injection + E2E MCP | **PHASE2QB_PASS** |
| **2Q-C** | Primary Market Parity + Historical Learning + OOS Validation Framework | **PHASE2QC_PASS** |
| **2Q-C.1** | Product Spec Truth + Local Data Root Hygiene + Filesystem Side-Effect Remediation | **PHASE2QC1_PASS** |
| **2Q-C.2** | Target-Family Runtime Isolation + Taiwan Packet Correctness + Historical OOS Metric Correctness | **PHASE2QC2_PASS** |

## 2Q-C.2 本棒成果（Target-Family Isolation + Taiwan Packet + MASE metric，correctness hotfix）
- 修 HIGH cross-market contamination：taiwan packet 不再引用 OSE Micro settlement（root cause = reference routing 二分法）。
- 新 `resolve_market_family()`（OSAKA_MICRO / TAIWAN_STOCK / TAIWAN_INDEX，未知 market fail clearly）。
- reference/regime/coverage/archive 全按 family 隔離；`_taiwan_stock_reference()`（FinMind→TWSE→yfinance）；TAIEX = ^TWII proxy + DIRECT_NOT_IMPLEMENTED。
- 修 MASE：每 fold scale 只用 TRAINING naive in-sample（不跨 fold、不含 future）；新增 baseline_scores + fold-level metrics。
- 修 yfinance tz-naive timestamp 雙重解讀（先 localize 到 local tz 再 convert UTC）。
- 新增 `test_phase2qc2.py`（22 tests）；全 suite **765 passed**（743→765）。MCP E2E 驗證三 market 無污染。
- build_id 未變（`1afb6888eec3fbdc`）。禁區未動：不 performance / 不新模型 / 不 training / 不 broker。PR #10 merged；版本仍 v2.0.0-rc1。

## 2Q-C.1 本棒成果（Product Spec Truth + Data Root Hygiene + Filesystem Side-Effect，correctness/hygiene hotfix）
- 修 OSE Micro multiplier 100→10（JPX official：Contract Unit = Nikkei 225 × JPY 10，tick 5）。TX/MTX/TMF = 200/50/10 authoritative verified。
- 新 `config/runtime_paths.py`：MARKET_AI_DATA_ROOT env override，預設 `<ProjectRoot>\data`；private inbox = `<DATA_ROOT>\private\inbox\225labo`。
- 移除 hardcode `D:\MARKET_AI_HUB_PRIVATE_INBOX`（empty legacy folder 已安全刪除）；import/health/status 不再產生 filesystem side effect（lazy path + FileHandler delay）。
- `scripts/import_latest_225labo_micro.ps1` 改從 Python resolver 取 path。`.env.example` 加 MARKET_AI_DATA_ROOT。
- 新增 PRODUCT_SPEC_AUDIT.md / LOCAL_RUNTIME_ARTIFACT_AUDIT.md / 報告。225LABO license boundary 不變（LOCAL_ONLY，manual only）。
- 新增 `test_phase2qc1.py`（16 tests）；全 suite **740 passed**（724→740）。build_id → `1afb6888eec3fbdc`。
- 禁區未動：不 training / 不 broker / 不 mega-restructure。PR #9 merged；版本仍 v2.0.0-rc1。

## 2Q-C 本棒成果（Primary Market Parity + Historical Learning + OOS Validation，architecture/framework）
- 三大 first-class families 正式定義：OSAKA_MICRO / TAIWAN_STOCK / TAIWAN_INDEX（防止 Osaka-only）。
- TAIWAN_INDEX 語義：TAIEX=cash index forecast/reference（非可成交）；TX/MTX/TMF=execution。
- 新模組 `research/historical_learning.py`：HistoricalWalkForwardProtocol（expanding/rolling、three_zone_split、protocol hash、leakage invariant）。
- 新 `services/primary_targets.py`（registry loader）+ `config/primary_targets.yaml`（不 hardcode 私人路徑）。
- `research_truth` 新增 `evidence_by_target()`（§21 按市場隔離）；`get_analysis_packet` 支援 `market=taiwan_index`。
- 新增 YAML/docs：PRIMARY_MARKET_MISSION / UNIFIED_RESEARCH_EVIDENCE_SCHEMA / TAIWAN_INDEX_CAPABILITY_AUDIT / HISTORICAL_LEARNING_PROTOCOL / OUT_OF_SAMPLE_VALIDATION_STANDARD / 報告。
- 新增 `test_phase2qc.py`（15 tests）；全 suite **724 passed**（712→724）。build_id → `026a18a9d46832f8`。
- TAIWAN_STOCK / TAIWAN_INDEX 目前 NO_EVIDENCE / NOT_YET_VALIDATED（誠實）。禁區未動：不 broker / 不 auto promotion。PR #8 merged；版本仍 v2.0.0-rc1。

## 2Q-B 本棒成果（Whole System Validation + Clean-Room + Failure Injection + E2E MCP，correctness-only）
- 0 Critical / 0 High defect；修 1 個 MEDIUM：`mcp/server.py` 硬編碼 `project_path` → `str(project_root())`（clean-room 違反）。
- 新增 tests：`test_phase2qb.py`（16）+ `test_phase2qb_failure.py`（5）；全 suite **712 passed**（691→712）。
- 新增 scripts：`mcp_e2e_stability.py`（實際啟動 MCP stdio，24 calls no crash，RSS 67.3MB）+ `secret_scan.py`（0 真實 secret）。
- 新增 `SYSTEM_VALIDATION_BASELINE.json` + `PHASE2QB_WHOLE_SYSTEM_VALIDATION_REPORT.md` + `docs/reference/KNOWN_LIMITATIONS.md`。
- Clean clone PASS（project_root 正確解析、21 tools、3 skills、data/ 僅 .gitkeep）；restart deterministic（multi-seed subprocess）；research truth 一致；仍 RESEARCH_ONLY。
- build_id → `440d9273c9bb39f5`。禁區未動：不 performance optimization / 不重組目錄 / 不新模型 / 不 broker / 不 auto promotion。PR #7 merged；版本仍 v2.0.0-rc1（不 tag）。

## 2Q-A 本棒成果（Runtime Truth Consolidation + Deterministic Direction + MCP Fast Path）
- 修正 Cherry Studio 驗收問題 A–G：direction 只收 eligible vote（0 票 → NO_VALIDATED_MODEL_CONSENSUS）；deterministic tie（平手 → NO_CONSENSUS，cross-process 一致）；uncalibrated 不稱 probability；direct/proxy calendar 分離；research truth 單一來源；forward count 統一；fast path + forecast cache。
- 新模組：`services/research_truth.py`（讀 PHASE2_RESEARCH_FREEZE）、`services/forecast_cache.py`、`services/perf_trace.py`（MCP_PERF_TRACE）。
- packet 加 target_semantics / calendar 分離 / support_resistance_status / validation_truth / market_environment / driver_panel。
- gate wording 修正（MODEL_PREDICTIVE_GATE=GENERAL_PRODUCTION_MODEL_GATE_UNPROVEN；TRADING_EDGE_GATE.result=NO_ECONOMIC_EDGE）。
- build_info 加 release_version / runtime_build_id。benchmark `scripts/benchmark_mcp_fastpath.py`（fastpath_acceptance=true，warm QUICK 1 call + 0 dup inference ~3ms）。
- 新增 `tests/test_phase2qa.py`（22 tests，含 subprocess cross-process determinism）；全 suite **691 passed**。
- build_id → `cd33ef1c14839b7d`（source runtime 修正，fingerprinted files 變更）。禁區未動：不新增模型 / 不重訓 / 不 strategy optimization / 不 broker / 不 live trading。PR #6 merged；版本仍 v2.0.0-rc1。

## 2P-E 本棒成果（System Prompt Compaction + Skill Responsibility Cleanup，doc-only）
- 新增 `docs/prompts/SYSTEM_PROMPT_V4_1_COMPACT.md`（~260 行，RECOMMENDED FOR CHERRY STUDIO AND NORMAL MCP CLIENT USE）。
- 保留 critical safeguards；移除 hardcode dynamic facts（Forward N / build_id 作 authoritative / leaderboard）；詳細規則 delegate 到 3 Skills。
- V4.0 標 FULL REFERENCE / EXTENDED POLICY（不刪）。
- README / CHERRY_STUDIO_BEGINNER_GUIDE / CHERRY_STUDIO_SETUP / MCP_CLIENT_SETUP 推薦改指 compact。
- 新增 `tests/test_phase2pe.py`（12 tests）；全 suite 669 passed。
- 不改 runtime / models / research evidence / MCP tools / training defaults。PR #5 merged；版本仍 v2.0.0-rc1。

## 2P-D 本棒成果（Agent Response Truthfulness Hotfix，documentation/prompt only）
- 新增 `docs/prompts/SYSTEM_PROMPT_V4_PHASE2_RC1.md`（Phase 2 / v2.0.0-rc1 對齊，含 0A 語意保護 10 條）。
- 10 條語意保護：continuous vs contract / settlement vs model target / direction eligibility（NO_VALIDATED_MODEL_CONSENSUS）/ uncalibrated probability / economic validation truth / support-resistance evidence / P10-P90 / holiday trading（2026-09-21~23 祝日交易）/ model-specific validation / forward registry（registered≠validated）。
- V3.3 標 DEPRECATED AS PRIMARY / HISTORICAL COMPATIBILITY REFERENCE。
- README / MCP_CLIENT_SETUP / CHERRY_STUDIO_SETUP / START_HERE_BEGINNER 推薦 System Prompt 改指 V4。
- 新增 `tests/test_phase2pd.py`（8 tests）；全 suite 657 passed。
- 不改 runtime / MCP tools / models / research conclusions / training defaults。
- PR #4 merged；版本仍 v2.0.0-rc1。

## 2P-C 本棒成果（Remote Reconciliation + GitHub Publication）
- Remote client-neutral 改寫（3922365）與 local Phase 2 工作**兩者全保留**（不二選一）。
- release/v2.0.0-rc1 建於 origin/main，cherry-pick Phase 2 work，reconcile README/HANDOFF/ARCHITECTURE。
- remote stale V1 docs 更新（13→21 tools，build_id→ccabe1e1552d9ae7）。
- **已發布 GitHub**：PR #3 merged（6b6d58e）→ tag v2.0.0-rc1 → release（truthful notes）。
- 全 suite 649 passed；MCP 21 tools；Skills 3；research state 誠實。
- URL：https://github.com/fishke22/market-ai-hub/releases/tag/v2.0.0-rc1
- 產物：`REMOTE_RECONCILIATION_REPORT.md`、`PHASE2PC_REMOTE_RECONCILIATION_PUBLICATION_REPORT.md`。

## 2P-B 本棒成果（Beginner docs + 嘗試 final publication）
- 建立 9 份繁體中文 beginner docs（START_HERE / HOW_WORKS / CHERRY_STUDIO_GUIDE / DATA_UPDATE / AUTO_LEARNING / SAFE_TRAINING / TRADING_READINESS / DAILY_WORKFLOW / FAQ）+ README「第一次使用」links。
- 全部誠實揭露：RESEARCH_ONLY / NON_EXECUTABLE / NO_ECONOMIC_EDGE / AUTO_*=FALSE / Forward NONE_YET。
- .gitignore 補 runtime/private artifacts（data/*.json、Yuanta auth/diagnostic、machine inventory、runtime status）。
- 全 suite 649 passed（新增 6 beginner doc tests + 9 publication tests）。
- **🔴 BLOCKED：remote mismatch**。git fetch 發現 origin/main 已前進至 3922365（使用者 Sep-19 的 client-neutral docs 改寫，重寫 README/HANDOFF/ARCHITECTURE），本地仍 f707fdf 落後 1 commit，且與 beginner docs 重疊將產生 merge conflict。
- **未 commit / push / tag / release**。需人工決定 merge 方向（見 PHASE2PB_BEGINNER_PUBLICATION_REPORT.md 選項 A/B/C）。
- 產物：`PHASE2PB_BEGINNER_PUBLICATION_REPORT.md`、`tests/test_phase2pb.py`（6 tests）、9 份 beginner docs。

## 2P-A 本棒成果（Final Publication Acceptance + Crash Recovery）
- Crash recovery：無 stale git lock / truncated 檔案 / partial writes（HEAD f707fdf intact）。
- 保留已完成的 README Research State + evidence docs + publication manifests；補建 RELEASE_MANIFEST / DIFF_SUMMARY / GIT_PLAN / acceptance report。
- Clean clone **PASS**（Python 3.12，core import + MCP 21 tools + reconstruct_verify PASS）。
- MCP runtime 21 tools；model registry chronos/timesfm/fincast/xgb/lgbm PASS、NHITS/NBEATSx blocked。
- Secret scan 無 hardcoded credential；private data（data/ 僅 .gitkeep）；Yuanta/225LABO 全排除。
- Release v2.0.0-rc1（Phase 2 Research Release Candidate）。**publication-ready，但本棒未 commit/push/tag**。
- 產物：`RELEASE_MANIFEST.yaml`、`PUBLICATION_DIFF_SUMMARY.md`、`PRE_PUBLICATION_GIT_PLAN.md`、
  `PHASE2PA_FINAL_PUBLICATION_ACCEPTANCE_REPORT.md`、`PHASE2PA_CRASH_RECOVERY_AUDIT.md`、
  `PHASE2PA_CRASH_RECOVERY_REPORT.md`、`PHASE2PA_RECOVERY_CHECKLIST.json`、`tests/test_phase2pa.py`（9 tests）；全 suite 643 passed。

## 2V-F 本棒成果（Compute Resource Governor，保護桌面多工）
- 建立 resource governor：`config/resource_profiles.yaml`（DESKTOP_SAFE 預設）+ `config/model_resource_requirements.yaml`。
- `src/market_ai_hub/services/resource_governor.py`：preflight / request_resource_slot / release / status / log。
- 預設限制：GPU VRAM ≤65%/75%（保留≥4GB）、CPU 保留 25%、RAM ≤65%/75%、priority BelowNormal、Optuna n_jobs=1。
- **AUTO_TRAIN=false / AUTO_FINE_TUNE=false / AUTO_PROMOTE=false**；single heavy GPU job；fail closed。
- `scripts/resource_status.ps1` + `scripts/run_training_safe.ps1`；RESOURCE_GOVERNOR_STATUS.json。
- 產物：`PHASE2VF_RESOURCE_GOVERNOR_REPORT.md`、`tests/test_phase2vf.py`（15 tests）；全 suite 634 passed。

## 2V-E 本棒成果（Forward Data Feed Readiness + Phase 2 Research Freeze）
- 建立 225LABO manual ingest workflow（無 auto-scrape，source immutable，incremental idempotent）。
- `src/market_ai_hub/data/ylab225_ingest.py`：build_daily_bars / validate / ingest_from_inbox / coverage_summary / run_daily_cycle。
- `scripts/import_latest_225labo_micro.ps1` + `scripts/run_daily_forward_cycle.ps1` + `scripts/register_forward_shadow_task.ps1`（opt-in only）。
- 資料 freshness gate：FRESH/STALE/MISSING_CURRENT_SESSION；stale → FORECAST_SKIPPED_DATA_QUALITY（實測）。
- **PHASE2_RESEARCH_FREEZE.yaml**：Phase 2 最終誠實結論凍結（VAR=STATISTICAL_FORECAST_EVIDENCE 但 NON_EXECUTABLE；NO_ECONOMIC_EDGE；無 candidate）。
- 產物：`FORWARD_DATA_SOURCE_POLICY.yaml`、`PHASE2_RESEARCH_FREEZE.yaml`、`FORWARD_DAILY_SUMMARY.md`、
  `tests/test_phase2ve.py`（14 tests）；全 suite 619 passed。

## 2V-D 本棒成果（Forward Shadow infrastructure，research-only，非 trading）
- 建立 forward shadow infrastructure：protocol frozen + activation timestamp（2026-09-20）+ core module + scripts。
- `src/market_ai_hub/research/forward_shadow.py`：create_daily_forecasts / settle_pending / build_status / init_activation。
- `scripts/run_forward_shadow.ps1` + `scripts/settle_forward_predictions.ps1`（research forecast + registry write，無 Yuanta login/order）。
- registry append-only + immutable 驗證；資料 freshness gate（stale → FORECAST_SKIPPED_DATA_QUALITY）。
- **Forward evidence = NONE_YET**（225LABO data 19 天 stale，最後 bar 2026-09-01；不能 backfill，需 fresh data + 每日執行）。
- **歷史結論維持**：VAR = STATISTICAL FORECAST EVIDENCE 但 NON_EXECUTABLE_FORECAST_EDGE；無 strategy/production candidate。
- Label 全程：RESEARCH_FORECAST_ONLY / NON_EXECUTABLE_FORECAST_EDGE；AUTO_PROMOTE=false；scheduler default DISABLED。
- 產物：`FORWARD_SHADOW_PROTOCOL.yaml`、`FORWARD_SHADOW_ACTIVATION.yaml`、`FORWARD_SHADOW_STATUS.json`、
  `FORWARD_SHADOW_REPORT.md`、`FORWARD_VALIDATION_MANIFEST.yaml`、`PHASE2VD_FORWARD_SHADOW_SETUP_REPORT.md`、
  `tests/test_phase2vd.py`（15 tests）；全 suite 605 passed。

## 2V-C.1 本棒成果（Gap Edge Causality + Pre-Close Executability，非 trading）
- **最終結論：NON_EXECUTABLE_FORECAST_EDGE**。VAR(1) 的 gap edge 無法轉成可執行策略。
- 因果發現：VAR 62.2% close-to-close edge 有 **85.2% 在 gap**（corr +0.726 sign / +0.896 return），intraday 反向 -0.378。
- **關鍵**：corr(r_t, gap) = **-0.919**（當日 return 與 gap 強烈反向 mean reversion）。gap edge 需「當日完整 return r_t」才能算，但 r_t 只在 close[T]（15:15）才完整 = gap 開始時刻 → **non-causal**。
- Pre-close causal signal（用 r_{t-1}）：gap 準確率崩潰到 **41.3%**（比隨機 50% 差），close-to-close 47.5%。
- Full-close signal = STATISTICAL_ONLY_EDGE（85.2% 真實但 non-causal）；pre-close = NO_EDGE。
- VAR 不升 strategy candidate，保留研究結果。2V-D 不得追 production strategy。
- 產物：`GAP_EXECUTION_PROTOCOL.yaml`（v1 frozen）、`GAP_RETURN_DECOMPOSITION.csv`、
  `PRECLOSE_SIGNAL_RESULTS.csv`、`PHASE2VC1_GAP_CAUSALITY_REPORT.md`、`tests/test_phase2vc1.py`（14 tests）；全 suite 590 passed。

## 2V-C 本棒成果（Execution-Aware Strategy Validation，非 live trading）
- 對 VAR(1) candidate 做簡單 strategy mapping（signal at T close → enter T+1 open → exit T+1 close, fixed 1 unit）。
- **Strategy 分類：NO_ECONOMIC_EDGE**。VAR strategy 零成本即虧損（gross -259.4 pts/trade, win 32.1%）。
- **關鍵發現**：VAR forecast 對 close-to-close 準 62.2%（真實 edge），但 tradable 的 open-to-close 方向**反向相關 -0.378**（只準 32.4%）。**edge 在 overnight gap，不在 intraday open-to-close**。
- Cost scenarios C0-C3 全負（-259 至 -301 pts/trade）；break-even = 0 ticks。
- LONG/SHORT 皆負（LONG -153, SHORT -408）；所有 regime/subperiod 皆負，隨時間惡化。
- **Forecast edge 保留 CHAMPION_CANDIDATE（close-to-close 62.2%）**，但 strategy 無可執行 edge。
- 產物：`STRATEGY_VALIDATION_PROTOCOL.yaml`（v1 frozen）、`STRATEGY_COST_ASSUMPTIONS.yaml`、
  `VAR_STRATEGY_RESULTS.csv`、`STRATEGY_REGIME_RESULTS.csv`、`STRATEGY_SUBPERIOD_RESULTS.csv`、
  `BREAK_EVEN_COST_TABLE.csv`、`STRATEGY_VALIDATION_MANIFEST.yaml`、
  `PHASE2VC_STRATEGY_VALIDATION_REPORT.md`、`tests/test_phase2vc.py`（17 tests）；全 suite 576 passed。

## 2V-B.3 本棒成果（Direct Micro Bar Historical OOS Exam，正式模型考試）
- 驗證 225LABO minute OHLCV → OSE 交易日 bar（960 days，832 origins），point-in-time expanding walk-forward。
- **BREAKTHROUGH: VAR(1) beats LAST_VALUE (h=1)**：MASE=0.958, 95% CI=[0.00018, 0.00080] (不跨 0), dir_acc=62.2%, MCC=0.241。
- **本專案首次有模型統計上顯著擊敗 baseline**。timesfm-3.0 也接近 (MASE=0.995)，但其他模型未 beat。
- 方向模型：XGBoost (56.4%), LightGBM (55.7%) — 皆優於簡單方向 baseline。
- Foundation models: chronos MASE=1.012, timesfm MASE=0.995 — timesfm 邊際 beat 需進一步驗證。
- Ensembles: equal-weight MASE=1.099, dynamic MASE=1.019 — ensemble 稀釋 VAR 訊號。
- **Proxy vs Direct 差異顯著**：^N225 proxy 全模型 NO_EVIDENCE，但 verified Micro 有 VAR 顯著 beat。
- **CHAMPION_CANDIDATE: VAR(1)**。AUTO_PROMOTE=false，需 2V-C strategy + 2V-D forward。
- 產物：`DIRECT_MICRO_BAR_OOS_PROTOCOL.yaml`（v1 frozen）、`DIRECT_MICRO_BAR_OOS_RESULTS.csv`、
  `DIRECT_MICRO_BAR_DATASET_MANIFEST.yaml`、`DIRECT_MICRO_BAR_EXAM_MANIFEST.yaml`、
  `PHASE2VB3_DIRECT_MICRO_BAR_OOS_REPORT.md`、`tests/test_phase2vb3.py`（14 tests）；全 suite 559 passed。

## 2V-B.2 本棒成果（資料鑑識與驗證，READ-ONLY，未修改原始檔）
- 驗證 `D:\data\N225microf_2023-2026` = **真實 OSE Micro 分鐘 trade OHLCV**（225LABO vendor，非官方交易所）。
- **796 個 verified 交易日**（2023-07-24 → 2026-08-31），**0 筆上市前資料**（上市日 2023-05-29）。
- tick size = 5 點（PASS）；時區 = JST（Asia/Tokyo，session 缺口吻合 OSE）；volume = per-minute contract。
- **Micro ≠ Mini**：重疊 137,839 筆，volume 吻合率僅 1.18%（差異 21,243 口）→ 獨立契約，非 duplicate。
- close = **BAR_CLOSE**（非 settlement）；settlement 歷史仍僅 1 日（QROS 的 53 個 JPX_SETTLEMENT manifest 全是 33 位元組失敗下載）。
- 決策：**DIRECT_MICRO_BAR_OOS_POSSIBLE** + **SUBSTANTIAL_DIRECT_BAR_SAMPLE_AVAILABLE**（796 天 ≥ 250）。
- **DIRECT_SETTLEMENT_INSUFFICIENT 維持不變**（未偽造 settlement）。
- 產物：`LOCAL_OSE_DATA_PROVENANCE_MANIFEST.yaml`、`PHASE2VB2_LOCAL_MICRO_PROVENANCE_REPORT.md`、
  `DIRECT_MICRO_BAR_OOS_PROTOCOL_DRAFT.yaml`（draft，未 pre-register）；tests 545 passed。

## 2V-B.1 本棒成果（READ-ONLY 鑑識，無登入/下單/訂閱/SDK 修改）
- Pre-registered `HISTORICAL_OOS_PROTOCOL.yaml`（v1，凍結）；`DIRECT_TARGET_COVERAGE.json`。
- **DIRECT OSE Micro settlement 歷史僅 1 交易日**（JPX 公開源當日-only，歷史 404）→ **INSUFFICIENT_EVIDENCE**（未用 proxy 補）。
- PROXY ^N225（1223 bars，~1090 origins）walk-forward（點-in-time、expanding、無 random split、test 未用於 tuning）。
- 模型：LAST_VALUE/SEASONAL_NAIVE/DRIFT/MA/RIDGE/VAR/KALMAN + XGB/LGBM + Chronos-2/TimesFM-3.0 + equal/dynamic ensemble。
- 統計：moving-block bootstrap 95% CI + Diebold-Mariano（Newey-West HAC）+ Benjamini-Hochberg FDR。
- **結論：所有模型 NO_EVIDENCE**（無一打敗 LAST_VALUE/DRIFT；direction ~50%；dynamic ensemble NO_EVIDENCE_OF_ENSEMBLE_EDGE）。
- 最大失效條件 = HIGH_VOL/TREND_DOWN。NHITS/NBEATSx = RUNTIME_BLOCKED（training-only）。
- 產物：`PHASE2VB_HISTORICAL_OOS_REPORT.md`、`MODEL_FAILURE_ANALYSIS.md`、
  `PROXY_REFERENCE_OOS_RESULTS.csv`、`DIRECT_OSE_MICRO_OOS_RESULTS.csv`、`REGIME_OOS_RESULTS.csv`、
  `OOS_EXAM_MANIFEST.yaml`；tests 533 passed。

## 發布前狀態（RELEASE CANDIDATE）
- build_id `ccabe1e1552d9ae7`；test **509 passed**；MCP **21 tools**；Skills **3**。
- Primary target `OSE_NIKKEI225_MICRO_FUTURES`（^N225=PROXY）。
- clean-clone reconstruction PASS（新 venv → import/MCP 21 tools）。
- `RELEASE_CANDIDATE_CHECKLIST.md` / `RELEASE_CANDIDATE_MANIFEST.yaml` 已建立。
- Provider request instrumentation（`services/provider_metrics.py`）關閉 observability gap。
- **Yuanta 四條 API family**：SPARK / Futures Legacy Quote / Futures Legacy Trading /
  Leveraged Trading（槓桿全球贏家 Web API，DOCUMENTED_ONLY）。

## 已知限制（不阻塞，誠實保留）
- **OSE Micro settlement 歷史資料缺口**：JPX 公開源僅當日（歷史 404）；完整歷史需 J-Quants API key（NEEDS_CONFIG）。
- **所有模型 historical OOS NO_EVIDENCE**（不 beat baseline；direction ~50%）；Dynamic Ensemble NO_EVIDENCE_OF_ENSEMBLE_EDGE。
- Dynamic Ensemble UNVALIDATED_FORWARD；BEA/e-Stat/EIA/EDINET NEEDS_CONFIG。
- TradingView 免費 15 分鐘延遲；SPARK Futures 0112 未解。
- **OSE Micro SPARK StkCode 已 VERIFIED**（`JNU<合約月>`；下單代碼 JNU；FunctionList SHA256 已存）。
- **Legacy Quote OSE/EASYWIN 實際 symbol：UNRESOLVED**（需 EasyWin 匯出對照表）。
- NHITS/NBEATSx RUNTIME_BLOCKED（training-only，無 runtime adapter）。
- Yuanta Legacy Quote T 盤 retest = DEFERRED。

## 下一步（下一棒）
- 本棒**未** git commit / push / release / tag；**未**選 Champion（無 candidate）。
- 下一棒候選：2V-C / 2V-D forward validation（若有 CHAMPION_CANDIDATE）或取 J-Quants key 補 settlement 歷史。

## SAFETY
NO LIVE TRADING / NO ORDER / NO BROKER CREDENTIAL / AUTO_PROMOTE_CHAMPION=false /
Yuanta quote-only、Trading API 未接 runtime、OrderApiExposureGuard PASS、secret scan 無真實 PII。

## NEXT（禁止）
- 不 git commit/push、不 release/tag、不 Live Trading、不 Yuanta order、不 recorder。
