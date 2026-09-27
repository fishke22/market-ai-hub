# Accuracy v2 全系統驗證報告 — 2026-09-27

本報告驗證目前 MARKET_AI_HUB 可執行的主要功能面、資料邊界、模型 runtime、研究治理、前向證據、Agent/MCP 介面、獨立離線引擎與搬移能力。它不是預測績效宣稱；工程可執行、資料可用、預測增益、機率校準與含成本交易優勢分開判定。

## 最終狀態

- branch: `codex/vnext-audit-handoff`
- source/config build: `794f5d800aeb9924`
- readiness: `READY_FOR_ANALYSIS_AND_GOVERNED_PREDICTION`
- P2: `NO_IMPROVEMENT / BASELINE_RETAINED`
- P5: `COLLECTING_FORWARD_EVIDENCE`, canonical predictions=0, settled origins=0
- P7: `P7_ENGINEERING_PASS`
- `PREDICTIVE_GAIN=false` / `CALIBRATED=false` / `TRADING_EDGE=false`
- live execution=false
- P6: conditional/nonblocking；未有資料、runtime與獨立增益前不強做。

## 全套驗證

`.venv\Scripts\python.exe -m pytest -q -k "not test_single_instance_lock_releases_after_error"`

- 2112 passed
- 1 skipped
- 24 deselected
- 143 warnings
- exit 0
- final continuity/capability suite elapsed 215.63s

唯一固定排除的是既有 recorder owner-mutex 單例；本次沒有停止、重啟、重登或接管 recorder。warnings 主要是測試碼中的 `datetime.utcnow()` deprecation，屬技術債，不是目前功能失敗。

## 實機功能矩陣

| 功能面 | 實際驗證 | 結果 |
|---|---|---|
| repo/build | HEAD/origin/dirty/build bootstrap | PASS |
| MCP stdio | 外部 stdio initialize + list_tools | PASS；24 tools、expected missing=set() |
| MCP health | health_check | PASS；DuckDB/providers healthy |
| public collector | JPX + TAIFEX 實際 refresh | PASS；broker/credentials/recorder/order 均 false |
| JPX | 2026-09-25 JNU official settlement/archive | PASS |
| TAIFEX | official TMF snapshot/materialization | PASS；invalid/non-exact/non-regular fail closed |
| Chronos-2 | CPU load、CUDA load、7-step quantile inference | PASS |
| Chronos revision | `29ec3766d36d6f73f0696f85560a422f50e8498c` | verified |
| TimesFM-3.0 | RESEARCH load、univariate、multivariate、past-only covariates、CUDA | PASS |
| TimesFM serving | SERVING purpose | 正確 fail closed；research-only license gate |
| JNU direct | exact-contract current analysis | PASS；direct_model_available=true |
| JNU task target | next published settlement observation | PASS；current target date=2026-09-28 |
| holiday horizon | 2026-09-18 next observation | PASS；2026-09-24，不誤用 9/21–9/23 holiday sessions |
| P4 fallback | baseline/volatility/interval/quantile | PASS |
| P5 | preview / immutable ledger / maturity / revision / downgrade | PASS；未提前寫 sample |
| audit DB | read-only integrity | PASS；目前 0 P5 predictions、0 invalid |
| research gates | engineering/data/calendar/temporal | PASS |
| predictive gate | production predictive evidence | UNPROVEN（正確阻擋） |
| trading edge gate | cost/slippage evidence | UNPROVEN / NO_ECONOMIC_EDGE |
| auto train/promote | training_review | 正確 false；manual approval required |
| AnalysisPacket | current truth/direct path/gates | PASS |
| P7 Nautilus | isolated 1.231.0 deterministic parity | PASS |
| P7 cost | ZERO/BASE/STRESS 0/26/120 bps proxy | PASS；不當實際成交成本 |
| P7 paper | simulated venue only | PASS |
| P7 migration | rebuild recipe/path/isolation | PASS |
| secret/live boundary | no Git secret migration / no live order | PASS / fail closed |

## MCP 24 個工具

`health_check`, `get_system_info`, `get_data_source_status`, `get_data_coverage`, `get_data_continuity_status`, `get_capability_registry`, `get_target_instrument_state`, `get_event_calendar`, `get_official_release_snapshot`, `get_research_gates`, `get_forward_test_status`, `get_model_leaderboard`, `get_model_performance`, `get_analysis_packet`, `get_analysis_archive_status`, `get_market_data`, `analyze_jnu`, `analyze_osaka_nikkei`, `analyze_taiwan_stock`, `predict_chronos`, `predict_timesfm`, `predict_ensemble`, `run_ts_validation`, `backtest`。

工具存在不等於其結果可以升級為 production evidence；Agent 必須一起讀 research gates、資料級別與 validation truth。

## 本次發現並修正的三個一致性缺口

### 1. 舊 Phase2 freeze 被放在 current truth

Accuracy v2 現在是 current authority：current direct historical=`BLOCKED_HORIZON_MISMATCH`、development=`NO_IMPROVEMENT_BASELINE_RETAINED`、causal=`NOT_ESTABLISHED_CURRENT_ACCURACY_V2`。舊 VAR/causal 內容保留在 `legacy_phase2`，歷史不刪除但不能覆蓋現行結論。

### 2. AnalysisPacket 誤稱沒有 Direct Micro model path

exact-contract JNU direct research path 已可實際載入 Chronos，因此現行狀態改為 `RESEARCH_AVAILABLE_FORWARD_UNVALIDATED`。有 direct research output 不等於有 predictive gain；point champion 仍為 zero-return baseline。

### 3. Direct JNU 使用 next-session 語義

direct path 已統一成 `NEXT_PUBLISHED_SETTLEMENT_OBSERVATION`。2026-09-18 的下一筆 expected published observation 固定測試為 2026-09-24；使用者文字改為「下一筆官方發布的清算價觀測」，不再說「下一交易日」。

## Data Continuity 與 Capability Registry

目前 actual continuity snapshot 是 `NORMAL_TARGET_DATA`：JNU2610 latest official reference=2026-09-25 / 66,140，next expected published observation=2026-09-28，expected publication=2026-09-29T00:00:00Z，stale-after=00:30Z。最新 source redundancy=`SINGLE_CHANNEL_ONLY`：receipt channel 有 hash-verified 66,140；最新 local Daily Report channel 沒有同日 row。兩者本來也都屬 JPX/OSE，所以 independent publisher count 明確維持1。context-confidence=`MEDIUM` 且不是 probability。

continuity mode 的負測試固定：overdue、no exact reference、source conflict 都必須 context-only；direct target prediction / new P5 precommit / predictive-gain update / calibrated probability / trading edge 全部阻擋，proxy 不能變 target。P5 可繼續 settle 已存在的 frozen pending outcome。正常資料則完全不改原本 JNU/P5 路徑。

Capability Registry 共15項，Agent 可直接讀 `available/data_ready/evidence_level/user_visible/blocked_reason`；actual summary available=11、data_ready=11、blocked=8。Golden Answer tests 固定 published-observation、interval-not-probability、legacy evidence 不覆蓋 current truth、direct path 存在但 forward-unvalidated、proxy≠target、edge unproven。

## 可以相信與不能宣稱

可以相信：資料 provenance、PIT/future-fill 防護、exact contract、holiday/roll/revision/stale fail-closed；public collector；實機 model inference；P4 fallback；MCP/packet/human summary；P5 prediction-before-outcome ledger；P7 isolated engine/rebuild。

不能宣稱：模型已穩定優於 zero-return baseline、固定勝率、interval 等於上漲機率、TimesFM research 權重可當 production serving、成本 proxy 等於真實成交成本、系統已有含成本 trading edge。

## 殘餘風險／等待項

1. P5 尚無 settled canonical origin；forward evidence 必須等時間自然產生。
2. P6 仍為 conditional；OFI/news/fine-tune/shared training 沒 prerequisites 不施工。
3. 部分 coverage 仍為 PROXY/MISSING/NEEDS_CONFIG；不得說成 direct target data。
4. FeatureStore 某些 current origin 可回 `NO_ELIGIBLE_ROWS`；direct JNU/P4 可用，但不能假裝 factor 可用。
5. `datetime.utcnow()` deprecation warnings 列入後續低風險 cleanup。
6. P5 Windows task 尚未 apply；排程設計 ready，不是假裝已無人值守。
7. 若未來官方 JNU outcome 長期中斷，替代資料只能提高 context / robustness / abstention credibility，不能代替 exact target outcome 做 OOS accuracy validation。
