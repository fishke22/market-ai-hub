# MARKET_AI_HUB — AGENT HANDOFF (durable)

Facts below are verified against the repo, not chat memory. If they disagree with the repo, the repo
wins. Refresh with `scripts/agent_bootstrap.ps1`. Last updated: 2026-09-25 W2 offline model-input contract closure after V2-I 2I.1.

## Current repair checkpoint

Read `research/phase3/reports/W2_MODEL_INPUT_CONTRACT_2026-09-25.md` for the latest W2 closure, then `W2_FEATURE_STORE_PACKET_2026-09-25.md` / `YUANTA_FIELD_AWARE_REPLAY_W2_2026-09-25.md` for prior W2 steps. Latest implementation commit is `9a11ce309ef5159545cb64e4ed8fa81ca0bbacfd`; runtime build_id is `bed003b51f6d1f8b`.

Runtime adoption is still **RUNTIME_ADOPTION_PENDING**. Read-only inspection found the running recorder status still has the old field set and all 22 current `latest.json` quotes lack `field_provenance` / `freshness_semantics`; no broker login, logout, subscription, restart, order or account action was performed. Do not use a newly imported build_id as evidence for the already-running process.

Offline W2 reader/replay now maps trade/bid/ask independently from per-field provenance into the existing V2-A.2 `FactorRepresentationObservation`, preserves V2-H lineage/source IDs, rejects market/contract/session mismatches, out-of-order receipts, partial files and persistence/overflow truth, and never combines source time-of-day with a fabricated date. Old schema without per-field provenance is explicitly downgraded to `LEGACY_TOP_LEVEL_RECEIPT_ONLY` and cannot become DIRECT_LIVE.

W2 offline contract is now **PASS** through the model-input boundary: persisted quote → field-aware V2-A.2 observation → V2-H lineage → canonical Feature Store gate → public packet provenance → read-only model-input contract. Current broker rows are `TICK`, while Chronos/TimesFM/classifiers are `1d`; the model-input gate therefore returns `INCOMPATIBLE_FREQUENCY` instead of fabricating daily bars. This is **not DATA READY** and no model inference/training was enabled. Next bounded work is W3 outcome maturity / `evaluation_as_of` / homogeneous scope correctness. Recorder handover still requires explicit maintenance-window authorization.

## Read first (order)

1. `AGENTS.md` (repo root)
2. `scripts/agent_bootstrap.ps1` output (actual branch/HEAD/build_id/schemas/phase/providers)
3. this file
4. `docs/development/project-status.md`
5. the current phase contract under `docs/architecture/` (see map below)

## Architecture contracts (current)

| Track | Schema | Contract |
|---|---|---|
| V2-A As-Of / timestamp truth | 2A.2 | `docs/architecture/v2-asof-data-contract.md` |
| V2-A.2 Session + factor routing | 2A.2 | `docs/architecture/v2-session-factor-routing-contract.md` |
| V2-B Gap / session | 2B.1 | `research/v2/gap_session.py` |
| V2-C Daily labels | 2C.2 | `research/v2/labels.py` |
| V2-D State machine | 2D.4 | `docs/architecture/v2-state-machine-contract.md` |
| V2-E Extension / exhaustion | 2E.3 | `docs/architecture/v2-extension-exhaustion-contract.md` |
| V2-F Catalyst response | 2F.3 | `docs/architecture/v2-catalyst-response-contract.md` |
| V2-G Sequential updating | 2G.2 | `docs/architecture/v2-sequential-update-contract.md` |
| V2-H Prediction audit DB | 2H.2 | `docs/architecture/v2-prediction-audit-contract.md` |
| V2-I Calibration evaluation | 2I.1 | `docs/architecture/v2-calibration-evaluation-contract.md` |
| Price/Probability Map | 3A.2.3 | `research/price_probability_map.py` |

Closed phases (do not redo): V2-A.2, V2-B.1, V2-C.2, V2-D.4, V2-E.3, V2-F.3, V2-G.2, V2-H 2H.2,
V2-I 2I.1.
V2-I 2I.1 closed = **evaluation engine only**. CALIBRATION FITTING and probability publication are
**NOT STARTED**; `ACTUAL_CALIBRATION_EVIDENCE = NONE_YET`; `CALIBRATED` stays FORBIDDEN until real
settled probabilistic samples exist.

## Yuanta — three separate API families (do not mix)

```
SECURITIES API
= Yuanta SPARK / 元大證券API
= SPARK API supports securities + futures MARKETS by official contract
= securities profile login SERVER_VERIFIED MsgCode=0001
= measured quote identity must state account_profile=SECURITIES and market=TAIFEX / market=OSE / CME / CBOT / CBOE / NYBOT as applicable
= 2026-09-24 PROD matching callbacks VERIFIED on TAIFEX/OSE/CME/CBOT/CBOE/NYBOT
= night-session quote codes are API-specific (e.g. TMFPM*/JNUPM*); resolve dynamically from FunctionList
= primary cross-market live quote provider
= API_SUPPORT != FUTURES_ACCOUNT_ENTITLEMENT: separate futures-profile login still returns 0112

FUTURES QUOTE API
= YuantaQuote ActiveX/COM (ProgID YUANTAQUOTE.YuantaQuoteCtrl.1, x86 sidecar)
= independent quote API
= T / T+1 login SERVER_VERIFIED LogonOK (Status=2, code=0)
= 2026-09-24 T+1 TX/MX/TMF/UNF matching OnGetMktData VERIFIED
= domestic TAIFEX live backup; current overseas AddMktReg path is NOT verified

FUTURES TRADING API
= YuantaOrd (Yuanta.YuantaOrdCtrl.1)
= separate product, NOT connected to runtime
= NO ORDER (quote-only policy)
```

Official evidence now confirms SPARK supports futures markets, and securities-profile live callbacks
have been measured across multiple futures venues. Keep the claim precise: **SPARK securities profile
quote success != SPARK futures-account entitlement**. The futures profile still returns 0112.
The independent YuantaQuote COM API remains the separate FUTURES QUOTE API family and is a verified
domestic TAIFEX backup. Full method/evidence: `docs/integrations/yuanta/YUANTA_LIVE_MULTIFACTOR_GUIDE_ZH_TW.md`
and `config/yuanta_live_factor_matrix.yaml`. Rebuild/setup rules are in `docs/integrations/yuanta/YUANTA_FROM_SCRATCH_SETUP_ZH_TW.md`, product-code/session rules in `docs/integrations/yuanta/YUANTA_PRODUCT_CODE_AND_SESSION_RULES_ZH_TW.md`, and official download/source URLs in `config/yuanta_source_manifest.yaml`.

## System principles (Yuanta)

```
Yuanta futures unavailable != system blocked

Taiwan stock : use verified securities data where it is actually usable
TAIEX / TX / MTX / TMF : cash and futures identities stay separate forever
  no fresh futures feed -> persist NOT_AVAILABLE
  never let cash impersonate a future; never let a future overwrite cash
```

## Provider status truth (machine-readable: `integrations.yuanta.capabilities.PROVIDER_STATUS`)

```
legacy_futures_auth    : VERIFIED
legacy_domestic_quote  : LIVE_CALLBACK_VERIFIED
spark_securities_taifex_quote : LIVE_CALLBACK_VERIFIED
spark_securities_ose_quote    : LIVE_CALLBACK_VERIFIED
spark_securities_cme_quote    : LIVE_CALLBACK_VERIFIED
spark_securities_cbot_quote   : LIVE_CALLBACK_VERIFIED
spark_securities_cboe_quote   : LIVE_CALLBACK_VERIFIED
spark_securities_nybot_quote  : LIVE_CALLBACK_VERIFIED
spark_futures          : SPARK_FUTURES_ACCOUNT_ENTITLEMENT_BLOCKED (futures-profile login measured 0112)
ose_micro_live         : LIVE_CALLBACK_VERIFIED_SPARK_SECURITIES
taifex_live            : LIVE_CALLBACK_VERIFIED_SPARK_AND_LEGACY
```

## Legacy quote (EASYWIN) — canonical API facts

```
AddMktReg(symbol, UpdateMode, ReqType, SetMap)
  ReqType 1 = T 盤 ; ReqType 2 = T+1 盤        (official sample / reg_Ses2.log evidence: TXFL7, not TXFL7PM)
  UpdateMode default = 4 (SnapshotUpd)         (official Python sample)
  SetMap = 0
Legacy canonical API symbol = BASE symbol (e.g. TMFJ6) for BOTH T and T+1.
  `xxxPM` symbols stay as EasyWin UI/alias metadata only; never the AddMktReg canonical symbol.
```
Source of truth: `<yeswin>\AGENT\YSTrader\Data\List\M.TFX.TXT` (read-only, `easwin_resolver.py`).

## Truthfulness rules

- `ENGINE PASS != DATA READY != CALIBRATED != PREDICTIVE EVIDENCE != TRADING EDGE`.
- No fabricated timestamps, prices, probabilities, or provider status.
- Keep cutoff / leakage gates machine-enforced; report `NOT_AVAILABLE` instead of guessing.
- Never persist secrets; Windows Credential Manager only, masked output only.
- Quote-only: no order, no account query, no position/balance。即時行情由單一常駐 `live_quote_recorder` 負責；agent 必須讀 `data/live/yuanta/latest.json` 或透過 `scripts/request_yuanta_quote.ps1` 追加訂閱，不得自行重複登入/登出。

## Current gates

```
V2-A.2  PREV2H_V2A2_SESSION_FACTOR_ROUTING_FOUNDATION_PASS
V2-G.2  PHASEV2G_SEQUENTIAL_UPDATING_SCAFFOLD_PASS
V2-H.2  PHASEV2H_PREDICTION_AUDIT_DB_FORECAST_ARTIFACT_PASS
        V2I_UPSTREAM_EVALUATION_DATA_READY
        AGENT_HANDOFF_CONTRACT_READY
V2-I.1  PHASEV2I_CALIBRATION_EVALUATION_FOUNDATION_PASS
        YUANTA_SPARK_SECURITIES_FUTURES_QUOTE_PROBE_COMPLETE
V2-I    evaluation engine only — CALIBRATION FITTING NOT STARTED. ACTUAL_CALIBRATION_EVIDENCE =
        NONE_YET; CALIBRATED is FORBIDDEN until real settled probabilistic samples exist in the DB.
```
