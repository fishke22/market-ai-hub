# PHASE V2-H 2H.1 — Prediction Audit DB Foundation — REPORT

- **Schema**: `V2_PREDICTION_AUDIT_SCHEMA_VERSION = "2H.1"` (`src/market_ai_hub/research/v2/prediction_audit.py`)
- **Store**: `data/audit/prediction_audit.duckdb` (LOCAL_ONLY; tests use temporary DuckDB)
- **Baseline**: main = `c56144116ce72ec6f93300a7a0c9f7a268de8c5f`, build_id `381c25184ef31938`
- **Final build_id**: `f5f167785aa5893d`
- **Final tests**: `1600 passed, 20 deselected, 144 warnings`

## A. Baseline
```
starting HEAD: c56144116ce72ec6f93300a7a0c9f7a268de8c5f
ending HEAD:   (see merge commit)
working tree:  clean
Python:        3.12.13
starting build_id: 381c25184ef31938
ending build_id:   f5f167785aa5893d
```

## B. Purpose / invariants
Persist forever "what was known at prediction time" (prediction + factor lineage) and separately
"what actually happened" (outcome) — the two are never merged.

```
feature_cutoff_timestamp <= forecast_origin            else BLOCKED_TEMPORAL_ORDER
prediction payload has no outcome/realized/future keys else BLOCKED_OUTCOME_IN_PREDICTION
lineage available_at <= feature_cutoff_timestamp       else BLOCKED_FUTURE_FACTOR
same id + same payload -> IDEMPOTENT ; same id + different payload -> BLOCKED_ID_COLLISION
public API exposes NO UPDATE / DELETE (append-only)
record identity recomputed from stored payload == stored id
prediction / outcome / lineage payloads hash in separate namespaces
```

## C. Prediction record
`prediction_id` (`v2h_pred_…`, content-addressed) · target identity/role/calendar/frequency/horizon ·
`forecast_origin` · `feature_cutoff_timestamp` · `build_id` · `model` / `model_version` ·
`v2_schema_versions` (assembled from the live modules) · `state_snapshot_id` · `sequence_id` ·
`source_snapshot_ids` · `factor_lineage_digest` · `status` · `supersedes_id` · DB `created_at`.
`prediction_id` / `created_at` excluded from the payload; typed query columns + exact `payload_json`
are both stored so identity re-verifies after a DB round trip.

## D. Factor lineage (one immutable row per representation)
V2-A.2 fields carried verbatim: `economic_factor_id`, `representation_id`, `instrument_type`,
`representation_relation`, `temporal_role`, `resolved_role`, venue/calendar, `session_status`,
`trading_date`, `event_timestamp` / `available_at` / `provider_timestamp` / `received_at`,
`timestamp_precision`, staleness/availability/quality, provider/source/frequency/data_grade,
`point_in_time_safe`, contract/roll/series, `source_snapshot_ids`, content `lineage_id`.
`availability_status ∈ {AVAILABLE, NOT_AVAILABLE, EXTERNAL_ENTITLEMENT_BLOCKED, UNKNOWN}` —
unavailable / entitlement-blocked is persisted as valid audit truth, never omitted.
`lineage_from_observation()` maps a live `FactorRepresentationObservation` into audit lineage.

## E. Outcome record (separate table)
`outcome_id` (`v2h_out_…`) · `prediction_id` · `label_type` · `outcome_kind` · `target_period` ·
`actual_value` / `actual_state` · `event_timestamp` / `available_at` · `label_schema_version` ·
`source_snapshot_ids` · DB `created_at`. A prediction insert writes no outcome / realized label /
future price; outcomes append later and never rewrite the prediction row.

## F. Tests (31, temporary DuckDB only)
temporal order enforced/equal-allowed · outcome-in-prediction blocked (case-insensitive) with legit
schema keys allowed · future factor after cutoff blocked, available-before-cutoff allowed ·
NOT_AVAILABLE and EXTERNAL_ENTITLEMENT_BLOCKED persisted · unknown availability rejected ·
duplicate representation blocked · lineage digest mismatch fail-closed · exact-duplicate idempotent ·
same-id different-payload blocked · forged id rejected · supersede creates new record and preserves
original · outcome id collision blocked · outcome requires known prediction ·
outcome append does not mutate prediction or lineage · hash namespaces separate ·
later provider refresh cannot mutate old lineage · identity recomputes from DB · deterministic reads ·
no UPDATE/DELETE SQL or methods · records frozen · naive datetime rejected ·
V2-A.2 observation → lineage integration (unavailable + live contract cases).

## G. Regression (actual)
```
focused tests/test_v2h_prediction_audit.py: 31 passed
V2-A..H: 604 passed
Phase3A: 121 passed
full suite: 1600 passed, 20 deselected, 144 warnings
```

## H. Changed files
```
ADD src/market_ai_hub/research/v2/prediction_audit.py
ADD tests/test_v2h_prediction_audit.py
ADD docs/architecture/v2-prediction-audit-contract.md
ADD research/phase3/reports/PHASEV2H_PREDICTION_AUDIT_DB_FOUNDATION_REPORT.md
MOD docs/development/project-status.md (phase V2-H / schema 2H.1 / build_id)
MOD tests/test_challengers_2d1.py / test_research.py / test_tournament.py (build_id)
```

## I. Actual readiness / integration
```
actual market V2-H predictions persisted: 0 (no managed production prediction stream yet)
factor lineage: live -> persist live lineage; unavailable -> persist unavailable lineage (both verified)
V2-F / V2-G / V2-I integration: NOT_STARTED (no runtime wiring in this round)
Yuanta live capability: not a gate
```

## J. Safety
```
calibration: NO · Brier/log-loss: NO · model training: NO · trading: NO · broker: NO
scheduled recorder: NO · V2-I: NOT_STARTED · production DB written by tests: NO
```

## K. Gate
**PHASEV2H_PREDICTION_AUDIT_DB_FOUNDATION_PASS**
ENGINE PASS != PREDICTIVE EVIDENCE != CALIBRATED PROBABILITY != TRADING EDGE.

STOPPED AFTER V2-H PREDICTION AUDIT DB FOUNDATION.
V2-I NOT STARTED.
