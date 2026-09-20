# Manual Cherry Studio UAT Template

> **State: `MANUAL_CHERRY_UAT = PENDING_USER_CONFIRMATION`**
>
> Only a human actually running these cases in Cherry Studio may change this to `PASS`.
> Automated checks may only set `AUTOMATED_PRECHECK_PASS`.

## Setup

- Client: Cherry Studio (or any stdio MCP client).
- System prompt: `docs/prompts/SYSTEM_PROMPT_V4_1_COMPACT.md`.
- MCP server: `market-ai-mcp.exe` (stdio).

## How to fill

For each case, record: timestamp, client version, system-prompt version, MCP build id
(`health_check` → `build.build_id`), tool calls observed, latency (MCP vs LLM separately),
final answer, PASS/FAIL, and failure owner if FAIL.

Failure owner must be one of:

- `ANSWER_LAYER` — LLM interpretation error (payload was correct).
- `SKILL_ROUTING` — wrong tool selection / duplicate model calls.
- `MCP_PAYLOAD` — structured payload itself wrong.
- `RUNTIME` — backend defect / crash.
- `CLIENT_BEHAVIOR` — client-side issue.
- `DOCUMENTATION` — wrong/missing doc guidance.

---

## CASE 1 — System health

Prompt: `系統健康檢查`

Expected:
- Fast, shallow; must NOT show `Loading weights` / take tens of seconds.
- Model state = `AVAILABLE_NOT_LOADED` or `LOADED_READY` (not "FAIL" for not-loaded).
- Tool budget: ≤ 2 calls (health, optionally system info).

Record:

```
timestamp:
client:
system_prompt:
mcp_build:
tool_calls:
mcp_latency_ms:
llm_latency_ms:
answer:
result: PASS/FAIL
failure_owner: (if FAIL)
```

## CASE 2 — Osaka Micro compact

Prompt: `分析大阪微型日經（compact）`

Expected:
- Primary target = `OSE_NIKKEI225_MICRO_FUTURES`; `^N225` = PROXY only.
- Official settlement = `SETTLEMENT` (not live execution price).
- Continuous ≠ Contract; Settlement ≠ Bar Close.
- `eligible direction votes = 0` → `NO_VALIDATED_MODEL_CONSENSUS` (not Up/Down/Flat).
- uncalibrated scores never called "上漲機率/下跌機率".
- P10/P90 never called 支撐/壓力/停損/失效點.
- Tool budget: 1 primary `get_analysis_packet` call (≤2).

Record: (same fields)

## CASE 3 — Taiwan Stock compact

Prompt: `分析 2330.TW（compact）`

Expected:
- Reference price = 2330 itself (FinMind/TWSE), exchange TWSE.
- Must NOT contain OSE settlement / `202703` / Micro contract / `^N225` / jpx-micro metadata.
- contract month = null / N/A.

Record: (same fields)

## CASE 4 — TAIEX compact

Prompt: `分析台股指數 TAIEX（compact）`

Expected:
- TAIEX = cash index, forecast/reference.
- If `^TWII` used, labeled proxy.
- TAIEX index points not executable.
- Strategy execution must name TX / MTX / TMF (not TAIEX itself).

Record: (same fields)

## CASE 5 — Validation / retraining review

Prompt: `系統目前的驗證狀態與是否該重新訓練？`

Expected:
- Proxy Historical `NO_EVIDENCE`; Direct Micro `STATISTICAL_FORECAST_EVIDENCE`;
  Causal `NON_EXECUTABLE_FORECAST_EDGE`; Economic `NO_ECONOMIC_EDGE`; Forward = runtime truth;
  Strategy/production candidate `NONE`.
- Never say "OOS 沒做" / "成本滑價沒做".
- Retraining only under sufficient new samples / drift / degradation / new hypothesis + manual
  approval; `AUTO_TRAIN=AUTO_FINE_TUNE=AUTO_PROMOTE=false`.

Record: (same fields)

---

## Overall

```
MANUAL_CHERRY_UAT = PENDING_USER_CONFIRMATION  (until all 5 cases run and recorded by the user)
```
