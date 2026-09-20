# PHASE 2Q-C.1 — Product Spec Truth + Local Data Root Hygiene + Filesystem Side-Effect Remediation

- gate：**PHASE2QC1_PASS**
- build_id：`1afb6888eec3fbdc`
- 版本：`v2.0.0-rc1`（不 tag）

## 兩個 confirmed problems（§0）

| # | 問題 | 修正 |
|---|------|------|
| A | `ylab225_ingest.py` hardcode `D:\MARKET_AI_HUB_PRIVATE_INBOX\225labo`，`ingest_from_inbox()` 無條件 mkdir → 污染 D:\ root | 改用 `runtime_paths` resolver；路徑 lazy 解析；legacy folder 已安全移除（empty） |
| B | `primary_targets.yaml` OSE Micro multiplier=100（錯誤） | **→ 10**（JPX official：Contract Unit = Nikkei 225 × JPY 10） |

## Product Spec Audit（§1/§2）

authoritative 來源（official exchange doc，非 prompt/舊 report）：

| target | field | official | status |
|--------|-------|----------|--------|
| OSE Micro | multiplier | 10（JPX） | **FIXED**（100→10） |
| OSE Micro | tick | 5 | VERIFIED |
| TX | multiplier | 200（TAIFEX） | VERIFIED |
| MTX | multiplier | 50（TAIFEX） | VERIFIED |
| TMF | multiplier | 10（TAIFEX） | VERIFIED |

Notional sanity：OSE Micro @ 65,000 × 10 = **650,000 JPY**（不得 6,500,000）。

## Local Data Root（§3/§4/§8）

- 新 `config/runtime_paths.py`：`MARKET_AI_DATA_ROOT` env override，預設 `<ProjectRoot>\data`。
- private inbox = `<DATA_ROOT>\private\inbox\225labo`；raw = `<DATA_ROOT>\raw\ylab225\archive`；normalized = `<DATA_ROOT>\normalized\ose_micro`。
- 不再 hardcode D:\。
- `.env.example` 新增 `MARKET_AI_DATA_ROOT=`（optional）。

## No Filesystem Side Effect（§5/§15）

- `import market_ai_hub.data.ylab225_ingest` 不再建立目錄（路徑 lazy 由 function 內 resolver 產生）。
- `import market_ai_hub.mcp.server` 不再建立 logs 目錄（改用 FileHandler delay=True + main_sync 才 mkdir）。
- `coverage_summary()` / `health` / `status` 不建立目錄。
- 掃描全 src：唯一 import-time mkdir（server logs）已修；其餘 mkdir 皆在 explicit `__init__`/function 內。

## Legacy Migration（§9/§10）

- `legacy_inbox_status()`：NONE / LEGACY_EMPTY_INBOX / LEGACY_PRIVATE_DATA_FOUND。
- 本機 `D:\MARKET_AI_HUB_PRIVATE_INBOX\225labo` 確認 EMPTY → 已安全移除（含空 parent）。
- 有資料時不自動刪除/覆蓋/移動（提供 dry-run migration）。

## PowerShell（§7）

`scripts/import_latest_225labo_micro.ps1` 改從 Python `runtime_paths.private_inbox_dir()` 取 path，不再維護第二份 hardcode path。

## 225LABO License Boundary（§11）

維持 manual download only / no auto scrape / no redistribution / LOCAL_ONLY / raw GitHub NEVER。只修 path architecture。

## Doc Update（§12）

FORWARD_DATA_SOURCE_POLICY.yaml / FORWARD_SHADOW_OPERATIONS.md / DATA_UPDATE_FOR_BEGINNERS.md /
KNOWN_LIMITATIONS.md / PUBLICATION_EXCLUDE_MANIFEST.txt 全部改用 `<DATA_ROOT>\private\inbox\225labo`。
`git grep MARKET_AI_HUB_PRIVATE_INBOX` = 0（僅 runtime_paths 的 legacy detection 保留）。

## Tests（§13/§16/§17）

新增 `test_phase2qc1.py`（16 tests）：ose_micro_multiplier_is_10 / notional sanity / TX·MTX·TMF spec /
data_root env override / no hardcoded drive root / import no side effect / coverage no side effect /
missing inbox no drive-root pollution / legacy detection / legacy nonempty not deleted / legacy empty cleanup /
private data never git / ps1 resolver / env example。

**Full regression：740 passed（724→740，+16，無 regression）。**

## Local Runtime Artifact Audit（§14）

`LOCAL_RUNTIME_ARTIFACT_AUDIT.md`：分類 EXPECTED / SHOULD_RELOCATE / SHOULD_IGNORE / SAFE_TO_CLEAN。
本棒不搬動（真正 workspace cleanup 留後續）。
