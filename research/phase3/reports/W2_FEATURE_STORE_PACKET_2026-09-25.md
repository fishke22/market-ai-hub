# W2 Feature Store / Public Packet Provenance Wiring — 2026-09-25

## Scope

This bounded work package continues W2 after the field-aware Yuanta quote reader. It does not restart the live recorder, fit models, add a model, calibrate probabilities, or perform broker/account/order operations.

Implementation commit: `5fe8906bd1237f7f89cd96dbbfa9383b8763281f`  
Runtime build_id: `f09ff80765f94687`

## What is now connected

Offline data path:

`persisted quote -> V2-A.2 observation -> V2-H lineage -> Feature Store provenance snapshot -> gated quote feature -> Analysis Packet provenance summary`

The Feature Store remains the existing Phase-2C store. Schema v2 is a non-destructive extension; existing rows remain readable. V2-A.2 observation snapshots preserve lineage, venue/session/trading date, timestamp precision, availability/quality, contract month/code, roll/series semantics and source snapshot IDs.

A quote is materialized as `v2a2-quote-1` only when it is available at the cutoff, has a real dated event timestamp, is FRESH, point-in-time safe, carries an eligible V2-A.2 live role, and — for futures — has contract series semantics with `roll_status=NONE` and a contract code. Legacy receipt-only, unknown-event-time and stale rows may be retained for provenance but are not live model features.

Replay is idempotent for both factor-observation snapshots and materialized features. Conflicting reuse of a lineage ID fails closed.

## Data-root correction

The canonical runtime override is `MARKET_AI_DATA_ROOT`. Runtime paths, Data Lake and default Feature Store now resolve to the same root. `MARKET_AI_HUB_DATA_ROOT` is retained only as a Data Lake migration fallback when the canonical variable is absent. Current tests use the canonical name.

## Public packet boundary

Analysis Packet now exposes a bounded `factor_observation_summary` for relevant representations. It includes source/lineage/quality/contract/freshness context. It is not a probability or trading signal, and it does not silently replace the packet's existing target/reference price selection.

Read-only packet access does not create or migrate a missing Feature Store database.

## Validation

- W2 integration: `155 passed, 1 deselected`.
- Broader quote/V2/Feature Store/packet contracts: `265 passed, 2 deselected`.
- Final default suite: `1726 passed, 23 deselected, 132 warnings in 150.34s`, exit 0.
- Changed-file Yuanta secret scan: 0 hits.
- `git diff --check`: PASS.

## Not yet proven

This package does **not** prove that Chronos/TimesFM/classifiers or other prediction input construction actually consumes the new gated Feature Store rows. That is the next W2 package. Until that path is proven, do not call the recorded feed MODEL READY or DATA READY.

The live recorder is still `RUNTIME_ADOPTION_PENDING` and requires a separately authorized maintenance window for controlled restart/adoption. Reconnect/roll/WAL remain separate open items. W3 maturity/evaluation scope work still precedes calibration fitting.
