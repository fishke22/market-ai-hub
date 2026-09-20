# PHASE 2Q-E — Repository Professionalization + Documentation IA + Workspace Hygiene + Release/System Truth Normalization

- gate：**PHASE2QE_PASS**
- build_id：`72994dd18696dd04`
- 版本：`v2.0.0-rc1`（不 retag）

## 成果

### Root professionalization（§2）

Root tracked files：**115 → 14**（README / LICENSE / SECURITY / DISCLAIMER / THIRD_PARTY_NOTICES /
CHANGELOG / CONTRIBUTING / pyproject / 3× requirements / .env.example / .gitattributes / .gitignore）。

93 個 phase reports / protocols / manifests / results / publication artifacts 全數 `git mv` 至
`research/`（Git history 保留，未刪任何研究證據）。

### Research IA（§3-§9）

```
research/
  phase2/
    status/  freeze/  protocols/  manifests/  results/  reports/  performance/  publication/  integrations/
  history/v1/
  releases/v2.0.0-rc1/
```

- 權威 freeze：`research/phase2/freeze/PHASE2_RESEARCH_FREEZE.yaml`（`research_truth.py` 路徑已更新，content 不變）。
- RC1 release snapshot 獨立於 current main：`research/releases/v2.0.0-rc1/`。
- V1 歷史：`research/history/v1/`（標 HISTORICAL SNAPSHOT，非 current truth）。
- Yuanta 研究：`research/phase2/integrations/yuanta/`（23 docs）。

### Docs IA（§19-§23）

- `docs/README.md` index；`docs/getting-started/`、`docs/guides/`、`docs/concepts/`、
  `docs/reference/`、`docs/development/`、`docs/integrations/yuanta/`。
- beginner 命名 → professional（START_HERE_BEGINNER → quickstart、FAQ_BEGINNER → faq 等）。
- `docs/reference/current-status.md`（current main truth，獨立於 rc1 snapshot）。

### README rewrite（§16）

專業 homepage，三大 first-class families、current research status、validation philosophy、
documentation index、safety/limitations。移除 phase construction diary / 大量 emoji / 小白 / V1 大段。

### Config normalization（§13/§14）

- `SYSTEM_MANIFEST.yaml` → `config/system_manifest.yaml`（三 families；build_id 標 `runtime_introspected`，不 hardcode stale）。
- `PRIMARY_MARKET_MISSION.yaml` → `config/primary_market_mission.yaml`。

### New files

- `CHANGELOG.md`（產品能力變化，非 phase 編號）。
- `CONTRIBUTING.md`。
- `scripts/check_docs_links.py`（relative link 驗證）。
- `tests/test_phase2qe.py`（root allowlist + doc style + three-family）。

## Validation

- 全部 `git mv`（非 copy+delete），Git 可追蹤 rename。
- `research_truth` / `forward_shadow` / tests / scripts 路徑更新後，research truth 語義不變
  （causal=NON_EXECUTABLE_FORECAST_EDGE、economic=NO_ECONOMIC_EDGE）。
- 更新了 30+ test/script references 至新路徑。
- 三市場無 cross contamination（沿用 2Q-C.2 測試）。
- secret scan：0 真實 secret（4 誤報皆 getpass prompt）。
- check_docs_links：OK（9 primary docs 無 broken relative link）。
- root allowlist：14 root files（≤25）。

## Test count

- Full regression：**782 passed**（778 + 4 new test_phase2qe），無 regression。
- Clean clone：root 14 files、freeze/research_truth/21 tools/3 skills 全 PASS。

## 未完成 / 留後續（§30-§35，非 correctness 阻斷）

- lightning_logs 未來路徑改 `<DATA_ROOT>/logs/lightning/`：設定未改（留 2Q-F）。
- runtime DB layout 遷移至 `<DATA_ROOT>/db/`：未執行（需 safe migration，留 2Q-F）。
- `.remediation_backup_*` audit：未動（Git 已保留完整 history）。

## 禁區未動

不 new model / training / fine-tuning / strategy optimization / broker / live trading /
重新計算 frozen evidence。v2.0.0-rc1 tag 未動，未 force push。
