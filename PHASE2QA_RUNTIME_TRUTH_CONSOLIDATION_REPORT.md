# PHASE 2Q-A — Runtime Truth Consolidation + Deterministic Direction Fix + MCP Fast Path

- gate：**PHASE2QA_PASS**
- build_id：`cd33ef1c14839b7d`（source runtime 修正，fingerprinted files 變更）
- 版本：`v2.0.0-rc1`（維持）

## 修正的 primary problems

| # | 問題 | 修正 |
|---|------|------|
| A | eligible_direction_vote_count=0 仍輸出 Up/Flat | direction ensemble 只收 `DIRECTION_CLASSIFICATION` + `eligible_for_direction_vote`；0 票 → `NO_VALIDATED_MODEL_CONSENSUS` / `NO_ELIGIBLE_VOTES` |
| B | restart 前後 final_direction 可變 | 移除 `max(set(dirs), key=dirs.count)`；deterministic plurality，平手 → `NO_CONSENSUS` / `TIE` |
| C | uncalibrated 被當 probability | raw_class_scores 與正式 vote 分離；未校準不稱 probability |
| D | proxy/direct calendar 混用 | target_semantics 分 `direct_market_calendar`(OSE/JPX_DERIVATIVES) vs `proxy_model_calendar`(XTKS) |
| E | Phase2 OOS truth 與舊 gate 不一致 | 單一來源 `services/research_truth.py`（讀 PHASE2_RESEARCH_FREEZE） |
| F | forward registry 語意不一致 | `PredictionRegistry.forward_summary()` 統一分層計數 |
| G | Cherry Studio 太慢 | compact packet = 1 primary call；tool budget；forecast result cache |

## 核心變更

- `ensemble/ensemble.py`：direction eligibility + deterministic tie + raw research view（§2–4）
- `services/research_truth.py`（新）：ValidationTruth 單一來源（§8/§9/§11）
- `services/forecast_cache.py`（新）：forecast result cache（§20）
- `services/perf_trace.py`（新）：MCP_PERF_TRACE（§22，預設 false，無 secrets）
- `packet/schema.py` + `packet/builder.py`：target semantics / calendar / support-resistance / environment / driver panel（§6/§7/§12/§13/§16）
- `services/model_catalog.py`：gate wording（§9）
- `services/build_info.py`：release_version / runtime_build_id（§15）
- `research/registry.py`：forward_summary（§14）
- `mcp/server.py`：forward count / leaderboard scoping / forecast cache / gate note（§10/§14）
- docs：system prompt tool budget + cherry skill fast path + MCP_DISCONNECT_FORENSICS.md（§18/§24/§26）

## Validation

- 新增 `tests/test_phase2qa.py`：22 tests（§27，含 cross-process determinism subprocess 測試）
- 全 suite：**691 passed**，5 deselected，無 regression
- benchmark `scripts/benchmark_mcp_fastpath.py`：**fastpath_acceptance = warm QUICK 1 primary call + 0 duplicate model inference**；warm backend latency ~3ms（millisecond-level）

## 未變更（禁區）

runtime 小修正之外：不新增模型 / 不重訓 / 不 fine-tune / 不 strategy optimization / 不 broker / 不 live trading。
RESEARCH_FREEZE / 歷史報告 / 各 phase manifest 的 build_id 快照保持原值（歷史紀錄）。
