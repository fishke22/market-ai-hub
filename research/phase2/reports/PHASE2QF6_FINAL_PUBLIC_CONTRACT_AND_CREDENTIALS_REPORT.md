# PHASE 2Q-F.6 — Final Public Response Contract Closure + MCP Routing Lockdown + Secure FRED/FinMind Credential Setup

- gate：**PHASE2QF6_FINAL_UAT_PREP_PASS**（0 Critical / 0 High）
- build_id：`1fa0f15a0764eb4f`
- 版本：`v2.0.0-rc1`（不 tag / release / retag）

## 0. Preflight — interrupted work

`git status` = clean；HEAD == origin/main == `455b6a0`。**無未提交 / dirty / untracked 狀態可保留**
（所有 local branches 皆在 main 或之後，`safety/phase2pb-local-20260920` 為舊備份）。故無需 backup patch。

## 13 問答（§43）

1. **Interrupted remote work 留下哪些 modifications？** 無。working tree clean，無 uncommitted/untracked。
2. **哪些已保留？** 全部既有 commit（F5 = `455b6a0`）保留，未 reset/checkout/clean。
3. **F5 後 Cherry 為何仍拿得到 probability/confidence？** 因為 F5 只 sanitize `get_analysis_packet` 與 `predict_*`；但 Cherry 直接呼叫 `analyze_osaka_nikkei` / `analyze_taiwan_stock`（legacy），它們回 raw model tree（`confidence`、`class_probabilities`、`final_direction`）。
4. **analyze_osaka_nikkei 是否曾繞過 sanitizer？** 是。修：改為 PUBLIC SAFE WRAPPER（`sanitize_analysis_output`，預設 view=public，`semantic_scope=PROXY_ONLY`）。
5. **analyze_taiwan_stock 是否曾繞過 sanitizer？** 是。同樣加 public wrapper（view 參數）。
6. **PUBLIC view 現在是否 whitelist？** 是。`public_view.py` 改 explicit whitelist（只允許核准欄位）。
7. **Micro / Proxy 現在如何 machine-separated？** Osaka packet `target_semantics`：`direct_target`/`direct_market_calendar=OSE_DERIVATIVES`/`direct_micro_forecast_status=NOT_AVAILABLE` vs `proxy_model_target=^N225`/`proxy_model_calendar=XTKS`/`proxy_model_target_dates`；`analyze_osaka_nikkei` 加 `semantic_scope=PROXY_ONLY`。
8. **3706 zero-vote 是否仍可能 HIGH consensus？** 否。public view 移除 `model_agreement`/`legacy_raw_unvalidated_agreement`，只留 `validated_direction_agreement=N/A` + `direction_status=NO_VALIDATED_MODEL_CONSENSUS`。
9. **P10/P90 是否仍可能變 support/resistance？** 否。public 名稱固定 `predictive_quantile_range`，無 support/resistance alias。
10. **Position-aware request PUBLIC contract？** `position_guidance_policy`（mode=RISK_ANALYSIS_ONLY，personalized_trade_action=PROHIBITED；allowed=EXPOSURE/PNL_SENSITIVITY/SCENARIO_ANALYSIS；forbidden=ADD/REDUCE/STOP/TAKE_PROFIT/ORDER_SIZE）。
11. **FRED/FinMind credential 存哪裡？** Windows Credential Manager（target `MARKET_AI_HUB/FRED_API_KEY`、`MARKET_AI_HUB/FINMIND_API_TOKEN`）；env fallback。
12. **repo/logs 是否 0 secrets？** 是（secret scan 0 真實 secret）。
13. **provider shallow status 設定後如何顯示？** 設定後 `get_secret` 找到 → status OK（不再 NEEDS_CONFIG）；shallow 不打 network。

## 21 MCP Tool Public Contract Audit（§3）

| tool | class | 可能風險 | 處置 |
|------|-------|---------|------|
| health_check | PUBLIC_SAFE | — | shallow |
| get_system_info | PUBLIC_SAFE | — | shallow |
| get_research_gates | PUBLIC_SAFE | gate 可能被誤讀 | label + training_review |
| get_data_source_status | PUBLIC_SAFE | — | provider status |
| get_market_data | PUBLIC_SAFE | 可能回 raw rows | 結構化 tail only |
| predict_chronos | **PUBLIC_SAFE_SANITIZED** | confidence/direction | `sanitize_forecast_dump` |
| predict_timesfm | **PUBLIC_SAFE_SANITIZED** | confidence/direction | `sanitize_forecast_dump` |
| predict_ensemble | **PUBLIC_SAFE_SANITIZED** | class_probabilities/agreement | `sanitize_ensemble_dump` |
| get_model_performance | AUDIT_ONLY | 歷史 metric | 明確 metric label |
| backtest | AUDIT_ONLY | 研究指標 | research-only |
| run_ts_validation | AUDIT_ONLY | OOS metric | research-only |
| analyze_osaka_nikkei | **PUBLIC_SAFE_SANITIZED** | raw model tree | `sanitize_analysis_output`（view=public 預設） |
| analyze_taiwan_stock | **PUBLIC_SAFE_SANITIZED** | raw model tree | `sanitize_analysis_output` |
| get_analysis_packet | PUBLIC_SAFE | — | F4/F5 已 safe |
| get_data_coverage | PUBLIC_SAFE | — | — |
| get_event_calendar | PUBLIC_SAFE | — | — |
| get_official_release_snapshot | PUBLIC_SAFE | — | — |
| get_target_instrument_state | PUBLIC_SAFE | — | role 標記 |
| get_model_leaderboard | AUDIT_ONLY | sample_n 誤讀 | evidence_layer 標記 |
| get_forward_test_status | PUBLIC_SAFE | registered≠validated | 明確 wording |
| get_analysis_archive_status | PUBLIC_SAFE | — | — |

一般 Cherry 可自動呼叫者皆 safe by default；raw diagnostics 需 explicit `view=audit`。

## 交付

- `services/public_view.py`：whitelist sanitizer + `sanitize_analysis_output` + canonical names + position policy。
- `services/secret_store.py`（新）：WinCred → env resolver（不 log value）。
- `scripts/setup_api_credentials.py`（新）：getpass 互動寫 WinCred。
- `config/settings.py`：`get_secret` 走中央 resolver。
- `mcp/server.py`：analyze_* 加 view wrapper；predict_* sanitized。
- `packet/builder.py`：driver_panel `evidence_role/causal_validation/trading_edge`。
- `tests/test_phase2qf6.py`（13 tests）。

## Validation

- **full default pytest：817 passed, 20 deselected**（804 + 13 new）。
- audit_runtime_evidence / assert_uat_semantics / docs links：PASS。secret scan：0 真實 secret。

## Credential setup command

```
D:\MARKET_AI_HUB\.venv\Scripts\python.exe scripts\setup_api_credentials.py
```

（使用者在本機 terminal 以 getpass 安全輸入 rotated FRED/FinMind credentials；Agent 未抽取、未寫入任何 chat 中的舊值。）

## Manual UAT

```
MANUAL_CHERRY_UAT = RETEST_REQUIRED
```

使用者跑 6 cases（health / Osaka / 2330 / TAIEX / validation+retrain / position-aware）。

## 禁區未動

不 new model / training / fine-tuning / strategy optimization / broker / live trading / auto order / tag / release / retag / force push。
