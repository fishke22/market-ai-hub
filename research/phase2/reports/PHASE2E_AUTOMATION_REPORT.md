# Phase 2E — 自主研究循環 / Data Lake / Analysis Archive / 受控自動學習

- Gate: **PHASE2E_PASS**
- build_id: `bbf3cb2f9a80d20e`（未變，V1 相容）
- 測試：**240 passed**（154 V1 + 12 2A + 12 2B + 17 2C + 16 2D + 15 2D.1 + 14 2E）

## 交付內容（對照 A–W）

| 項 | 交付 | 檔案 |
|---|---|---|
| A | Smart Data Lake（目錄 + Manifest） | `automation/data_lake.py` |
| B | 增量下載（missing-range / dedup / hash / atomic write） | `automation/incremental.py` |
| C | Analysis Archive（不可變分析） | `automation/archive.py` |
| D | Outcome（append-only 結算） | `automation/archive.py` |
| E | 學習規則文件 | `docs/automated_learning_policy.md` |
| F | 自主 orchestrator + CLI | `automation/cli.py`、`__main__.py` |
| G | 輕量 10 步每日循環 | `automation/loop.py` |
| H | 開機 catch-up | `automation/loop.py::run_catchup` |
| I | TrainingEligibilityPolicy | `automation/training_policy.py` |
| J | 訓練 pipeline（政策層） | `training_policy.py`（snapshot→train→validate→test→walk-forward→tournament→shadow→forward 政策定義） |
| K | Champion 安全（AUTO_PROMOTE=false） | `training_policy.py` |
| L | MLflow 自動訓練日誌 | 沿用 `research/mlflow_tracker.py`（automation 政策層接線） |
| M | Bounded Optuna | `automation/optuna_wrap.py` |
| N | River shadow | `automation/training_policy.py::DriftMonitor` |
| O | Windows 排程腳本 | `scripts/register_research_tasks.ps1`、`unregister_research_tasks.ps1` |
| P | 電力 / 離線行為 | `loop.py`（OFFLINE_DEFERRED / GPU_BUSY） |
| Q | Data retention config | `config/data_retention.yaml` |
| R | Analysis save hook（不改 response） | `automation/analysis_hook.py` |
| S | status CLI | `cli.py::cmd_status` |
| T | 測試 | `tests/test_phase2e.py`（14 項） |
| U | 文件（5 份） | `docs/*.md` |
| V | 本報告 | `PHASE2E_AUTOMATION_REPORT.md` |
| W | 交接 | `CURRENT_HANDOFF.md` |

## 硬性安全規則（已實作 + 測試鎖定）

1. **無交易**：automation 套件與 MCP / Cherry 完全獨立，不含任何交易能力。
2. **AUTO_PROMOTE_TO_CHAMPION = False**（永不自動換 champion）；`test_auto_promote_always_false` 鎖定。
3. **River shadow-only**：`DriftMonitor` 只回 `DRIFT_WARNING` + retrain 建議；`test_drift_monitor_psi` 驗證 shadow_only=True。
4. **Optuna bounded**：max_trials=20 / max_runtime=300s / gpu_budget=4000MB；Final Test 不得調參。
5. **offline → OFFLINE_DEFERRED**：不刪資料、不偽造（`test_run_tick_offline_no_fabrication`）。
6. **GPU busy → TRAINING_DEFERRED_GPU_BUSY**（`test_run_tick_gpu_busy`）。
7. **不可變 + append-only**：Analysis 重複 save / 重複 settle 皆拒絕（測試鎖定）。
8. **不得自動刪除**：raw official data / prediction history / analysis history（KEEP_FOREVER）。
9. **LLM 文字不得訓練價格模型**（防 self-reinforcement）。

## 已知限制（誠實揭露）

- **訓練 pipeline 為「政策層」實作**：eligibility 判斷 / drift 監測 / Optuna wrapper / 排程 / 結算 / archive 皆為真實可跑程式碼；但「實際執行 heavy 重訓」尚未在本 phase 自動觸發（需手動、且避免無人時鎖 GPU）。後續 phase 可將 policy 接到 tournament engine 的實際 train。
- **MLflow 接線為政策層**：沿用現有 `mlflow_tracker.py`，未在 automation 內重建一套 logger。
- **Analysis save hook 未改動 fingerprinted `services/analysis.py` / `mcp/server.py`**：為避免 build_id 變動與 V1 破壞，hook 以獨立函式 `archive_analysis(result_dict)` 提供，loop 可呼叫；把 hook 織入 MCP 分析工具保留到後續（會動到 fingerprinted 檔案）。

## 驗證

- `pytest tests/test_phase2e.py -q` → 14 passed
- `pytest tests/ -q` → 240 passed
- `python -m market_ai_hub.automation status` → CLI 正常
- `build_id` 維持 `bbf3cb2f9a80d20e`
