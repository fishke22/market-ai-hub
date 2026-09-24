# Yuanta W2 Field-Aware Quote Reader / Offline Replay — 2026-09-25

## Scope

This is one bounded W2 sub-package. It does **not** restart the broker recorder, fit/calibrate models, add a model, place orders, query accounts, or claim DATA READY / CALIBRATED / EDGE.

Implementation commit: `825c19e7c67922eb7779d768ccd8b4207aae98cf`  
Runtime build_id after the reader source: `52837b5fc6444e3f`  
Branch: `codex/quote-hub-correctness`; PR #55 was still OPEN during local validation; `origin/main` remained `eb9202a157ce8831fdf6442a0f9faa5b84387d92`.

## Runtime adoption evidence

The existing persistent SPARK recorder was inspected read-only through `recorder_root()` / status/latest / existing Parquet. No login, logout, subscription, restart, order, position, balance or account action occurred.

Observed running status used the old schema: `status`, `pid`, `provider`, `login_msg_code`, `subscriptions`, `last_quote_at`, `heartbeat_at`. The 22 records in current `latest.json` had **0/22** `field_provenance` and no `freshness_semantics`. Therefore the live process is **RUNTIME_ADOPTION_PENDING**. A newly imported source build_id is not evidence for the already-running process.

## Reader contract

`src/market_ai_hub/integrations/yuanta/quote_reader.py` is offline-only and routes through existing sources of truth:

- subscription identity comes from `config/yuanta_live_recorder.yaml`;
- factor/representation/session semantics come from V2-A.2 `factor_representation` + `session_truth`;
- V2-H lineage uses existing `lineage_from_observation()`;
- no parallel factor/session/provider registry was added.

Trade, bid and ask are separate field kinds. For the hardened recorder schema, each field uses its own `field_provenance.received_at`; when aliases such as `DealPrice` and `deal` both exist, the newest valid per-field receipt wins. `source_type` keeps `TRADE` / `BID` / `ASK` distinct and snapshot IDs are deterministic.

Top-level `received_at` remains callback receipt only. `source_time_of_day` has no date, so the reader never combines it with local receipt date to fabricate an exchange timestamp. Without a real dated event timestamp, `event_timestamp=None` and `timestamp_precision=UNKNOWN`, which prevents V2-A.2 LIVE eligibility.

Old recorder schema without `field_provenance` is accepted only as `LEGACY_TOP_LEVEL_RECEIPT_ONLY`; it cannot be promoted to DIRECT_LIVE. If the new schema contains a field provenance object but omits that field's `received_at`, the reader typed-rejects instead of falling back silently.

For SPARK market 3 / 207, day/PM contract code must agree with the resolved V2 session when the session is knowable. Market, prefix/contract, subscription key, unsupported V2 representation, future receipt (`received_at > asof`), out-of-order replay, partial file, persistence error and buffer overflow all fail closed.

## Existing Parquet read-only replay evidence

A recent existing local Parquet file was inspected without modifying or copying it into the repository:

- total rows: 934;
- OSE `ose_micro` rows: 76;
- valid positive trade rows adapted to V2-A.2: 5;
- all 5 were explicitly `LEGACY_TOP_LEVEL_RECEIPT_ONLY` and `DELAYED_REFERENCE`;
- 71 rows had no valid positive trade value for the requested trade field and were rejected.

This is expected field-aware behavior: a callback row is not automatically a trade event. Only aggregate counts are recorded here; private quote values are not committed.

## Regression evidence

Focused contract regression after final reader semantics:

`153 passed, 1 deselected` — reader, quote hardening, Yuanta live contract, V2-A.2 factor/session, V2-H and 2H.2.

Final default profile after build snapshot update:

`1717 passed, 23 deselected, 132 warnings in 135.55s`, exit 0.

`git diff --check` passed. Existing Yuanta secret scanner reported 17 historical repository findings and **0 findings in this work package's five implementation/test files** before the implementation commit.

## What remains true

- Runtime adoption: **PENDING** until an explicitly authorized maintenance window performs tail/rollback/single-owner checks and controlled recorder restart.
- Automatic reconnect, continuous contract/session roll reevaluation, durable WAL/spool and long-duration stress remain unimplemented/unverified.
- Some recorder subscription representations (for example futures context that does not yet exist in the V2-A.2 static representation registry) are typed `UNSUPPORTED_V2_REPRESENTATION`; this work package does not expand the frozen registry just to make every subscription ingestible.
- This sub-package proves persisted quote → V2-A.2 observation → V2-H lineage offline wiring. It does **not** yet prove V2-A.2 → feature store → models → public packet end-to-end ingestion.
- W3 outcome maturity / evaluation_as_of / homogeneous scope still precede any calibration fitting. 2I.1 remains evaluation-only and CLASS_SCORE remains non-probability.
