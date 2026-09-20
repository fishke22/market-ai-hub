# PHASE 2V-F — COMPUTE RESOURCE GOVERNOR REPORT

- Gate: **PHASE2VF_PASS**（未來任何 training/fine-tuning 不會預設獨占整台電腦）
- 前置: PHASE2VE_PASS

---

## 0. 目的

確保未來任何 model retraining / fine-tuning / feature rebuild / Optuna / GPU batch / historical replay
都**不得吃滿整台電腦、造成 Windows 卡死、Cherry Studio 無法使用、GPU OOM、RAM swap 爆滿**。

**預設 INTERACTIVE_DESKTOP_PRIORITY**：training 永遠是 background workload。

## 1. 交付物

| 元件 | 說明 |
|------|------|
| `config/resource_profiles.yaml` | 3 profiles（DESKTOP_SAFE 預設 / BALANCED / TRAINING_MAX） |
| `config/model_resource_requirements.yaml` | 模型資源分級（VAR=CPU_LIGHT, Chronos/TimesFM/NHITS/NBEATSx=GPU_HEAVY）+ 優先順序 |
| `src/market_ai_hub/services/resource_governor.py` | 核心 governor（preflight / request_slot / release / status / log） |
| `scripts/resource_status.ps1` | 只讀狀態 |
| `scripts/run_training_safe.ps1` | safe launcher（preflight → acquire slot → launch → release） |
| `RESOURCE_GOVERNOR_STATUS.json` | 自動生成狀態 |
| `data/resource_usage_log.jsonl` | resource usage 記錄（不記 credential/PII） |
| `tests/test_phase2vf.py` | 15 tests |

## 2. 預設資源限制（DESKTOP_SAFE）

| 資源 | soft | hard | 保留 |
|------|------|------|------|
| GPU VRAM | ≤ 65%（~10.4GB @16GB） | ≤ 75%（~12GB） | ≥ 4GB |
| CPU | — | — | 25% logical cores（16→12 training max） |
| RAM | ≤ 65% | ≤ 75% | — |
| Process priority | BelowNormal | — | — |
| Optuna | n_jobs=1 | — | — |
| Auto train / fine-tune | **false** | — | — |

## 3. 設計保證

- **Single heavy GPU job**：GPU_HEAVY job 同時間最多一個（`RESOURCE_JOB_LOCKED`）。
- **Fail closed**：GPU/RAM metrics 讀取失敗 → `RESOURCE_MONITOR_UNAVAILABLE`，heavy training 不啟動。
- **GPU busy defer**：headroom < reserve → `RESOURCE_GPU_BUSY`，不硬搶。
- **Forward Shadow priority**：training 不得阻塞 forward registry / ingest / settlement。
- **Emergency stop**：checkpoint_then_exit（不是 kill -9）。
- **Status 無 secrets**：不記 credential/account/password/token/PII。
- **Training windows**：default MANUAL_ONLY（安裝後不自動 nightly training）。

## 4. 實測

- profile = DESKTOP_SAFE；cpu_max_threads = 12（16 cores 保留 25%）
- ram limits = 85GB soft / 98GB hard（~128GB 系統）
- gpu vram limits = 10647MB soft / 12285MB hard（~16GB 保留 4GB）
- preflight / acquire / release 全 PASS；single-heavy-job lock 驗證（第二 job → RESOURCE_JOB_LOCKED）
- tests 634 passed

## 5. Gate

**PHASE2VF_PASS**（resource governance 建立；不代表允許 auto-learning）。

AUTO_TRAIN=false / AUTO_FINE_TUNE=false / AUTO_PROMOTE=false 全程守住。
