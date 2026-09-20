# PHASE 2Q-F.2 — Acceptance Harness Hardening + Manual Cherry UAT Preparation + Client Response Truth Audit

- gate：**PHASE2QF2_PREP_PASS**（automated precheck；非 FINAL_UAT_PASS）
- build_id：`2253d3829253ef59`（未變，本棒未改 runtime source）
- 版本：`v2.0.0-rc1`（不 tag / release / retag）

## 1. Clean-room script fail-closed（§1/§2）

`scripts/verify_clean_room.ps1` 改為 fail-closed：
- 每 step 檢查 `$LASTEXITCODE`，非 0 → 印 `FAIL` 並標記 failed。
- 最後：`CLEAN_ROOM_ACCEPTANCE = PASS`（全 PASS 才 exit 0）或 `FAIL`（exit 1）。
- 六個 step：ENVIRONMENT / DEFAULT_PYTEST / MCP_TOOLS / SKILLS / DOC_LINKS / SECRET_SCAN。

## 2. Manual Cherry UAT template（§4-§16）

`research/phase2/status/MANUAL_CHERRY_UAT_TEMPLATE.md`：
- 5 cases（health / Osaka / 2330.TW / TAIEX / validation+retraining）。
- 每 case 記錄 timestamp / client / system prompt / MCP build / tool calls / latency / answer / PASS/FAIL / failure owner。
- failure owner 分類：ANSWER_LAYER / SKILL_ROUTING / MCP_PAYLOAD / RUNTIME / CLIENT_BEHAVIOR / DOCUMENTATION。
- 每 case 明確 expected semantics（§7-§14）。

## 3. UAT payload capture（§17）

`scripts/capture_uat_payloads.py`：只抓 safe MCP structured payload（health / gates / 3 packet），
不抓 Cherry conversation / credential。實測：
- health chronos = `AVAILABLE_NOT_LOADED`
- Osaka = `OSE_NIKKEI225_MICRO_FUTURES`
- 2330.TW = `2330.TW`（source=twse，無 OSE contamination）
- TAIEX = `TAIEX`（source=proxy_index）
- TRADING_EDGE_GATE = `UNPROVEN`（result=NO_ECONOMIC_EDGE）

## 4. Automated precheck（§18-§20）

- local default pytest：**772 passed, 20 deselected**（無 regression）。
- docs links：OK（9 primary docs）。
- secret scan：0 真實 secret（4 getpass 誤報）。
- 21 tools / 3 skills：契約固定，verify script exact assert。

## 5. Status

```
AUTOMATED_PRECHECK_PASS
MANUAL_CHERRY_UAT = PENDING_USER_CONFIRMATION
```

Agent 不得宣稱 manual PASS。只有使用者在 Cherry Studio 實際跑 5 cases 並確認後才能改 `PASS`。

## 禁區未動

不 new model / training / fine-tuning / strategy optimization / new market feature / broker / live trading / tag / release。
