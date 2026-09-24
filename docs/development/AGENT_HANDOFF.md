# MARKET_AI_HUB — AGENT HANDOFF (durable)

Facts below are verified against the repo, not chat memory. If they disagree with the repo, the repo
wins. Refresh with `scripts/agent_bootstrap.ps1`. Last updated: V2-H 2H.2 closure.

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
| Price/Probability Map | 3A.2.3 | `research/price_probability_map.py` |

Closed phases (do not redo): V2-A.2, V2-B.1, V2-C.2, V2-D.4, V2-E.3, V2-F.3, V2-G.2, V2-H 2H.2.
V2-I (calibration / evaluation) is **NOT STARTED**.

## Yuanta — three separate API families (do not mix)

```
SECURITIES API
= Yuanta SPARK / 元大證券API
= securities auth previously SERVER_VERIFIED (PHASE2YC)
= usable for Taiwan stock data, but only upgraded to LIVE after an actual quote-capability check

FUTURES QUOTE API
= YuantaQuote ActiveX/COM (ProgID YUANTAQUOTE.YuantaQuoteCtrl.1, x86 sidecar)
= independent quote API
= T / T+1 login already SERVER_VERIFIED LogonOK (Status=2, code=0)
= live quote callback still UNRESOLVED (registration OnRegError ErrCode=3, meaning UNKNOWN)

FUTURES TRADING API
= YuantaOrd (Yuanta.YuantaOrdCtrl.1)
= separate product, NOT connected to runtime
= NO ORDER (quote-only policy)
```

Never re-promote SPARK as the official futures quote provider without official evidence.

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
legacy_futures_auth    : VERIFIED                      (ReqType=1/2 measured Status=2 LogonOK code=0)
legacy_domestic_quote  : AUTH_VERIFIED_REGISTRATION_UNRESOLVED
spark_futures          : EXTERNAL_ENTITLEMENT_RETEST_REQUIRED   (historical server result 0112)
ose_micro_live         : NOT_AVAILABLE                 (nearest StkCode JNU2612, MarketNo 207)
taifex_live            : NOT_AVAILABLE_UNTIL_CALLBACK
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
- Quote-only: no order, no account query, no position/balance, no recorder, no auto-retry.

## Current gates

```
V2-A.2  PREV2H_V2A2_SESSION_FACTOR_ROUTING_FOUNDATION_PASS
V2-G.2  PHASEV2G_SEQUENTIAL_UPDATING_SCAFFOLD_PASS
V2-H.2  PHASEV2H_PREDICTION_AUDIT_DB_FORECAST_ARTIFACT_PASS
        V2I_UPSTREAM_EVALUATION_DATA_READY
        AGENT_HANDOFF_CONTRACT_READY
V2-I    NOT STARTED — calibration evidence currently NONE_YET; CALIBRATED is FORBIDDEN until real
        settled probabilistic samples exist in the audit DB.
```
