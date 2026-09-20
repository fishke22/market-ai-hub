# User Acceptance Checklist

Manual acceptance prompts for Cherry Studio (or any stdio MCP client). This is a manual check —
automated tests do not substitute for actually running these in the client.

Status: `MANUAL_CHERRY_UAT = PENDING_USER_CONFIRMATION` until these are run by a human.

## Prerequisites

- MCP server launched (`market-ai-mcp.exe`), configured in the client.
- System prompt set to `docs/prompts/SYSTEM_PROMPT_V4_1_COMPACT.md` (recommended).

## 1. System health

Prompt: `系統健康檢查`

Expected: a fast response (well under a second after warm-up) with model states
(`AVAILABLE_NOT_LOADED` / `LOADED_READY`), provider states, and a build fingerprint.
Must NOT show `Loading weights` or take tens of seconds.

## 2. Osaka Micro compact

Prompt: `分析大阪微型日經（compact）`

Expected: `OSE_NIKKEI225_MICRO_FUTURES` as the target; `^N225` only as proxy; reference price
labeled `SETTLEMENT` (not `LIVE_PRICE`); no claim of a validated direction.

## 3. Taiwan Stock compact

Prompt: `分析 2330.TW（compact）`

Expected: reference price is the stock itself (FinMind/TWSE), exchange `TWSE`, no OSE settlement,
no contract month.

## 4. TAIEX compact

Prompt: `分析台股指數 TAIEX（compact）`

Expected: TAIEX labeled as a forecast/reference cash index, `^TWII` proxy, and a note that
execution would require TX/MTX/TMF (not TAIEX points).

## 5. Validation / retraining review

Prompt: `系統目前的驗證狀態與是否該重新訓練？`

Expected: honest layered evidence (proxy OOS `NO_EVIDENCE`, direct Micro
`STATISTICAL_FORECAST_EVIDENCE` non-executable, economic `NO_ECONOMIC_EDGE`), forward
`NONE_YET`, and `AUTO_TRAIN=false` (no auto retraining).

## Response semantics to check across all prompts

- `eligible votes = 0` → `NO_VALIDATED_MODEL_CONSENSUS`, not an invented Up/Down/Flat.
- uncalibrated scores are never called "probability".
- P10/P90 are never called support/resistance.
- OOS / cost-slippage validation are never described as "not done".
- Taiwan stock never shows OSE settlement; TAIEX never shown as executable futures price.
