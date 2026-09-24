# V2 Prediction Audit Contract

- **Schema**: `V2_PREDICTION_AUDIT_SCHEMA_VERSION = "2H.1"`
  (module `src/market_ai_hub/research/v2/prediction_audit.py`)
- **Store**: `data/audit/prediction_audit.duckdb` — **LOCAL_ONLY** (no remote, no sync).
- Independent of `2A.2` / `2B.1` / `2C.2` / `2D.4` / `2E.3` / `2F.3` / `2G.2` / `3A.2.3`.

## Purpose

Persist forever **what was known at prediction time** (prediction + factor lineage) and, separately,
**what actually happened** (outcome). The two are never merged, so a later outcome can never be read
back into the prediction payload.

## Invariants (machine-enforced)

```
feature_cutoff_timestamp <= forecast_origin            else BLOCKED_TEMPORAL_ORDER
prediction payload has no outcome/realized/future keys else BLOCKED_OUTCOME_IN_PREDICTION
lineage available_at <= feature_cutoff_timestamp       else BLOCKED_FUTURE_FACTOR
same id + same payload  -> IDEMPOTENT
same id + different payload -> BLOCKED_ID_COLLISION
public API exposes NO UPDATE / DELETE (append-only)
record_identity recomputed from the stored payload == stored id
prediction / outcome / lineage payloads hash in separate namespaces
```

## Prediction record

`prediction_id` (content-addressed `v2h_pred_…`), target identity/role/calendar/frequency/horizon,
`forecast_origin`, `feature_cutoff_timestamp`, `build_id`, `model`, `model_version`,
`v2_schema_versions` (assembled from the live modules via `v2_schema_versions()`), `state_snapshot_id`,
`sequence_id`, `source_snapshot_ids`, `factor_lineage_digest`, `status ∈ {PENDING, SUPERSEDED, VOID}`,
`supersedes_id`, plus DB-side `created_at`. `prediction_id`/`created_at` are excluded from the payload.

The payload is canonical-JSON + SHA256; the store keeps both typed query columns and the exact
`payload_json` so `prediction_identity(json.loads(payload_json)) == prediction_id`.

## Factor lineage (one immutable row per representation)

Carries the V2-A.2 representation record verbatim: `economic_factor_id`, `representation_id`,
`instrument_type`, `representation_relation`, `temporal_role`, `resolved_role`, venue/calendar,
`session_status`, `trading_date`, `event_timestamp`/`available_at`/`provider_timestamp`/`received_at`,
`timestamp_precision`, staleness/availability/quality, provider/source/frequency/data_grade,
`point_in_time_safe`, contract fields, `source_snapshot_ids`, plus a content `lineage_id`.

`availability_status ∈ {AVAILABLE, NOT_AVAILABLE, EXTERNAL_ENTITLEMENT_BLOCKED, UNKNOWN}` —
**unavailable / entitlement-blocked is valid audit truth and is persisted, never omitted**.
`factor_lineage_digest` is the sorted digest of the lineage ids and is part of the prediction payload.
`lineage_from_observation()` maps a live `FactorRepresentationObservation` into audit lineage.

## Outcome record (separate table)

`outcome_id` (`v2h_out_…`), `prediction_id`, `label_type`, `outcome_kind`, `target_period`,
`actual_value` / `actual_state`, `event_timestamp`, `available_at`, `label_schema_version`,
`source_snapshot_ids`, `notes`, DB-side `created_at`. Inserting a prediction writes **no** outcome,
realized label, or future price; outcomes arrive later via `append_outcome()` and never rewrite the
prediction row.

## Append-only + correction

No update/delete exists in the public API. Correction = a **new record** with `supersedes_id`
pointing at the superseded `prediction_id`; the original row is untouched and still verifies.

## Scope / limits

No calibration, Brier/log-loss, model training, trading, broker, scheduled recorder, or V2-I.
Live availability is not a gate: live → persist live lineage; unavailable → persist unavailable
lineage. `ENGINE PASS != PREDICTIVE EVIDENCE != TRADING EDGE`.
