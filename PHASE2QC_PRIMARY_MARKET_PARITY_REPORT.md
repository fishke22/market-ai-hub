# PHASE 2Q-C — Primary Market Parity + Historical Learning Architecture + OOS Validation Framework

- gate：**PHASE2QC_PASS**
- build_id：`026a18a9d46832f8`（source 修正：packet builder taiwan_index 支援 + research_truth per-target evidence）
- 版本：`v2.0.0-rc1`（不 tag）

## 最高目的

正式防止 MARKET_AI_HUB 過度變成 Osaka-only system。三大 first-class families 定義完成。

## 三大 Primary Target Families

| family | primary target | execution | status |
|--------|---------------|-----------|--------|
| OSAKA_MICRO | OSE_NIKKEI225_MICRO_FUTURES | futures micro | IMPLEMENTED（保留 frozen evidence） |
| TAIWAN_STOCK | 台股個股 | equity itself | PARTIAL（分析 tool 存在，historical OOS 缺失） |
| TAIWAN_INDEX | TAIEX（forecast/reference） | TX/MTX/TMF | MISSING（語義+registry 已建，pipeline 待後棒） |

## Taiwan Index 語義（§2）

TAIEX = cash index forecast/reference（非可成交）；TX/MTX/TMF = TAIFEX futures（執行）。
Forecast target != execution instrument。TAIEX 指數點位不得冒充可成交 futures price。

## 交付物（§33）

- `PRIMARY_MARKET_MISSION.yaml` — 三大 family mission。
- `config/primary_targets.yaml` — target registry（不 hardcode 私人路徑）。
- `TAIWAN_INDEX_CAPABILITY_AUDIT.md` — data/model/packet/validation/forward/strategy 各 IMPLEMENTED/PARTIAL/MISSING。
- `HISTORICAL_LEARNING_PROTOCOL.md` — 三資料區 + walk-forward + pre-register + baselines + metrics。
- `OUT_OF_SAMPLE_VALIDATION_STANDARD.md` — split/leakage/evidence-per-target/dataset license。
- `UNIFIED_RESEARCH_EVIDENCE_SCHEMA.yaml` — evidence 綁 target_family/target/horizon/reproducibility。
- `PHASE2QC_PRIMARY_MARKET_PARITY_REPORT.md`（本檔）。

## Code

- `research/historical_learning.py`（新）：`HistoricalWalkForwardProtocol`（expanding/rolling，
  chronological_origins、three_zone_split、assert_origins_no_leakage、ProtocolSpec + protocol_hash、immutable WalkForwardFold）。
- `services/primary_targets.py`（新）：registry loader。
- `services/research_truth.py`：新增 `evidence_by_target()` / `evidence_for()`（§21 按市場隔離）。
- `packet/builder.py`：`get_analysis_packet` 支援 `market=taiwan_index`（TAIEX forecast vs TX/MTX/TMF execution 分離）。
- `mcp/server.py`：get_analysis_packet docstring 更新。

## 關鍵不變式

- 禁止 random shuffle；chronological split + walk-forward。
- 三資料區時間隔離；nested tuning 只在 train + inner validation。
- Evidence per target 隔離（Osaka evidence 不替 Taiwan 背書）。
- Historical OOS PASS 最多 CHAMPION_CANDIDATE，不得 auto production。
- AUTO_TRAIN / AUTO_FINE_TUNE / AUTO_PROMOTE = false。
- No live trading。

## Tests（§34）

新增 `test_phase2qc.py`（15 tests）：primary parity / three_zone_split / rolling / protocol hash /
leakage（future_row_not_in_train、validation_not_final_test、walkforward_origin_strict、
proxy_not_direct、target_family_isolated、hyperparameter_tuning_no_test_access）/ packet parity / auto-train。

**Full regression：724 passed（712→724，+12 新 tests，無 regression）。**

## 結論

本棒**不追求**「找會賺錢的模型」；目的是三大市場都有公平、可重現、不洩漏未來的歷史學習與 OOS 驗證能力。
TAIWAN_STOCK / TAIWAN_INDEX 目前 NO_EVIDENCE / NOT_YET_VALIDATED 是**誠實正確的結果**。
下一棒 Phase 2Q-D 才做 full performance engineering（全鏈路加速）。
