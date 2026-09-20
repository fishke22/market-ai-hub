# Local Runtime Artifact Audit

**Phase 2Q-C.1 §14** — 本棒只 AUDIT，不做大規模 relocation（真正 workspace cleanup 留後續 professionalization phase）。

## 分類

| artifact | 分類 | 說明 |
|----------|------|------|
| `lightning_logs/`（~2.7MB） | SHOULD_RELOCATE | 應在 DATA_ROOT/logs 下；現於 project root。gitignored。 |
| `mlruns/` | absent（EXPECTED） | 未用 mlflow local。 |
| `.pytest_cache/` | EXPECTED | pytest 快取，gitignored。 |
| `__pycache__/`（含 src/tests） | EXPECTED | Python bytecode，gitignored。 |
| `data/registry/`（~1.5MB） | EXPECTED | 不可變 prediction registry DB。gitignored。 |
| `data/tournament/`（~0.8MB） | EXPECTED | performance store。gitignored。 |
| `data/feature_store/`（~1MB） | EXPECTED | feature store。gitignored。 |
| `data/*.duckdb`（market/performance/ts_validation） | SHOULD_RELOCATE | 直接放在 data/ 根，未進各自 subdir。gitignored。 |
| `data/exploitdb.sqlite` | SHOULD_IGNORE（已忽略） | 非專案 runtime DB。 |
| `data/phase2v*_results.json` | EXPECTED | 研究結果快照。gitignored。 |
| `data/cache/` `data/normalized/` `data/raw/` `data/processed/` | EXPECTED | 資料管線產物。gitignored（PUBLICATION_EXCLUDE_MANIFEST）。 |
| `logs/mcp.log` | EXPECTED | MCP log。gitignored。 |
| `.opencode/` | EXPECTED | opencode agent 工作目錄。gitignored。 |

## 結論

全部 runtime artifact 皆已 gitignored（不污染 git）。僅兩項「SHOULD_RELOCATE」是位置 hygiene（非 correctness）：
1. `lightning_logs/` 應在 DATA_ROOT/logs。
2. `data/*.duckdb` 應進各自 subdir。

本棒不搬動（避免破壞既有 runtime 參照）。留後續 professionalization phase。
