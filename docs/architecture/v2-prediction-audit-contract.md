# V2 Prediction Audit Contract

- **Schema**: `V2_PREDICTION_AUDIT_SCHEMA_VERSION = "2H.4"`
  (module `src/market_ai_hub/research/v2/prediction_audit.py`)
- **Store**: `data/audit/prediction_audit.duckdb` — **LOCAL_ONLY** (no remote, no sync).
- Independent of `2A.2` / `2B.1` / `2C.2` / `2D.4` / `2E.3` / `2F.3` / `2G.2` / `3A.2.3`.

## 2H.2 addition — forecast artifact audit

2H.1 stored prediction metadata + factor lineage + outcomes but **not the forecast output itself**, so
Brier/log-loss/calibration could not be computed from the audit DB alone. 2H.2 adds an immutable
`ForecastArtifactRecord` + `forecast_artifacts` table:

```
artifact_type ∈ POINT / QUANTILE / INTERVAL / CLASS_SCORE / EVENT_PROBABILITY / STATE / NOT_AVAILABLE
fields: forecast_artifact_id, prediction_id, calibration_domain, probability_type, event_definition_id,
        event_threshold_value, label_type, value, raw_score, class_label, quantile_level, lower_value, upper_value,
        nominal_coverage, units, status, calibration_status_at_origin, calibration_evidence_id,
        distribution_id, distribution_version, generated_at, source_snapshot_ids
non-applicable fields stay None/"" — never fabricated
```

Type-specific requirements: `QUANTILE` needs `quantile_level`; `INTERVAL` needs
`lower/upper/nominal_coverage` with `lower <= upper`; `EVENT_PROBABILITY` needs
`event_definition_id`; `NOT_AVAILABLE` must carry no value/raw_score.

`raw score != calibrated probability` and `EVENT_PROBABILITY != automatically CALIBRATED`.
`is_public_probability(artifact)` is fail-closed (False) in 2I.1. Audit tags and an
arbitrary evidence ID never authorize publication; CLASS_SCORE is not a probability.
The separate PPM typed evidence gate remains authoritative for its own public view.
A future fitted-evidence resolver must validate event family, target, horizon, model
version, period and provenance before this audit API can publish probabilities.

### Prediction binding
`PredictionRecord.forecast_artifact_digest` is part of the prediction payload, so identity binds
`factor_lineage_digest + forecast_artifact_digest`. A prediction cannot secretly gain a forecast
output later (same id + changed digest = `BLOCKED_ID_COLLISION`).

### Atomic bundle
`append_prediction_bundle(prediction, lineage, forecast_artifacts)` validates everything first, then
writes prediction + lineage + artifacts in ONE transaction; any failure rolls back with no partial
prediction. `append_prediction()` (2H.1 path) delegates to the bundle with no artifacts.

### Outcome binding
`OutcomeRecord.forecast_artifact_id` (optional) must exist, belong to the same `prediction_id`, and
be type/scope compatible: `TOUCH` probability cannot pair with a `TERMINAL` outcome, and a
`DIRECTION` score cannot pair with a price-touch outcome. V2-I can therefore build exact
`forecast_artifact <-> outcome` evaluation pairs.

### Temporal gates (added to all 2H.1 gates)
`generated_at <= forecast_origin` (`BLOCKED_ARTIFACT_TEMPORAL`) and the legacy floor
`outcome available_at >= forecast_origin` (`BLOCKED_OUTCOME_TEMPORAL`). For sealed 2H.3+ label windows,
`outcome available_at >= label_window_end` (`BLOCKED_OUTCOME_IMMATURE`) and
`target_period == label_window_id` (`BLOCKED_OUTCOME_SCOPE`) are additionally mandatory.


## 2H.3 / W3.1 addition — sealed outcome maturity

2H.3 keeps the 2H.2 artifact contract and adds immutable prediction-time governance fields:
`sample_origin ∈ {FORWARD_PRECOMMITTED, RETROSPECTIVE_REPLAY, UNKNOWN}`,
`label_window_id`, `label_window_start`, and `label_window_end`. These fields are part of the
prediction payload and therefore change `prediction_id`; they cannot be attached after results are known.

When a prediction seals a label window, `append_outcome()` requires
`outcome.available_at >= label_window_end` and `outcome.target_period == label_window_id`.
A result that merely appears after `forecast_origin` is not enough. Existing 2H.2-style records remain
readable with the default `sample_origin=UNKNOWN` / no sealed window, but W3.1 governed evaluation
excludes them from governed forward/calibration evidence.

The default audit DB path follows the canonical `MARKET_AI_DATA_ROOT` resolver. Identical forecast
artifact identities cannot silently bind to two different predictions; the second binding is a typed
`BLOCKED_ARTIFACT_PREDICTION_MISMATCH`, not a raw database constraint failure.

## 2H.4 addition — frozen event threshold without breaking legacy identities

2H.4 adds optional `ForecastArtifactRecord.event_threshold_value` for event definitions whose
threshold is known at forecast origin and must be frozen for later settlement. W3.2-EP1 uses it for
`TERMINAL_CLOSE_GT_SOURCE_CLOSE_1D`.

The field enters canonical artifact payload/identity only when it is non-null. For legacy artifacts
where the field is absent, the payload omits it entirely, preserving all pre-2H.4 artifact hashes.
The audit layer still allows malformed probability values to be recorded so the evaluation layer can
fail-closed on bad inputs; raw audit storage does not imply publication eligibility.

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
`sample_origin`, `label_window_id/start/end`, `forecast_origin`, `feature_cutoff_timestamp`, `build_id`, `model`, `model_version`,
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
