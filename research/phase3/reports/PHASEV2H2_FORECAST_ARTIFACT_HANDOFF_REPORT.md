# PHASE V2-H 2H.2 — Forecast Artifact Audit + Agent Handoff Closure — REPORT

- **Schema**: `V2_PREDICTION_AUDIT_SCHEMA_VERSION = "2H.2"` (`src/market_ai_hub/research/v2/prediction_audit.py`)
- **Store**: `data/audit/prediction_audit.duckdb` (LOCAL_ONLY; tests use temporary DuckDB)
- **Baseline**: main = `94dfa51aed48cb094eac0cc3296705294f49c65e`, build_id `f5f167785aa5893d`
- **Final build_id**: `9c036eae6c83a934`
- **Final tests**: `1636 passed, 20 deselected, 144 warnings`

## A. Baseline
```
starting HEAD: 94dfa51aed48cb094eac0cc3296705294f49c65e
ending HEAD:   (see merge commit)
working tree:  clean at start
Python:        3.12.13
starting build_id: f5f167785aa5893d
ending build_id:   9c036eae6c83a934
```

## B. 2H.2 forecast artifact contract
2H.1 gap closed: the forecast output itself (value / raw score / probability / quantile / interval /
state) was not persisted, so Brier/log-loss/calibration could not be computed from the audit DB.

`ForecastArtifactRecord` + `forecast_artifacts` table:
```
artifact_type ∈ POINT / QUANTILE / INTERVAL / CLASS_SCORE / EVENT_PROBABILITY / STATE / NOT_AVAILABLE
forecast_artifact_id · prediction_id · calibration_domain · probability_type · event_definition_id ·
label_type · value · raw_score · class_label · quantile_level · lower_value · upper_value ·
nominal_coverage · units · status · calibration_status_at_origin · calibration_evidence_id ·
distribution_id · distribution_version · generated_at · source_snapshot_ids · schema_version
```
Non-applicable fields stay `None/""`. Type requirements enforced (QUANTILE level; INTERVAL bounds with
`lower <= upper`; EVENT_PROBABILITY event_definition_id; NOT_AVAILABLE carries no value/raw_score).
`raw score != calibrated probability`; `EVENT_PROBABILITY != automatically CALIBRATED`.
`is_public_probability()` is True only for EVENT_PROBABILITY/CLASS_SCORE with
`calibration_status_at_origin == CALIBRATED` + `calibration_evidence_id` + value — otherwise the
artifact stays internal (verified: an uncalibrated 0.72 event probability persists but is not public).

## C. Prediction binding + atomic bundle
- `PredictionRecord.forecast_artifact_digest` is part of the prediction payload → identity binds
  `factor_lineage_digest + forecast_artifact_digest`; a prediction cannot secretly gain a forecast
  output later (same id + changed digest → `BLOCKED_ID_COLLISION`).
- `append_prediction_bundle(prediction, lineage, forecast_artifacts)`: validate everything first, then
  write prediction + lineage + artifacts in ONE transaction; verified rollback leaves **no** partial
  prediction/lineage/artifact rows. `append_prediction()` (2H.1 path) delegates to the bundle and
  refuses a record carrying a non-empty artifact digest.
- Artifact identity excludes `prediction_id` (FK) so the id is not circular with the prediction id.

## D. Outcome binding + temporal gates
`OutcomeRecord.forecast_artifact_id` (optional) must exist, belong to the same prediction, and be
type/scope compatible: TOUCH probability + TERMINAL outcome → blocked; DIRECTION score + price-touch
outcome → blocked; DIRECTION score + DIRECTION outcome → allowed. V2-I can build exact
`forecast_artifact <-> outcome` evaluation pairs.
Added gates: `generated_at <= forecast_origin` (`BLOCKED_ARTIFACT_TEMPORAL`) and
`outcome available_at >= forecast_origin` (`BLOCKED_OUTCOME_TEMPORAL`). All 2H.1 gates retained.

## E. Durable agent handoff
```
ADD AGENTS.md                              (short, 7 fixed rules: verify repo, run bootstrap, read handoff,
                                            read contract/project-status, no redo of CLOSED/PASS phases,
                                            provider-unavailable != blocked, no PASS/READY/CALIBRATED/EDGE conflation)
ADD docs/development/AGENT_HANDOFF.md      (contract map, three Yuanta API families, provider status truth,
                                            legacy EASYWIN canonical facts, truthfulness rules, current gates)
ADD scripts/agent_bootstrap.ps1            (read-only: branch/HEAD/origin/status/build_id/V2 schemas/
                                            phase/providers/read-next; never writes; sets only PYTHONPATH)
```
Verified by tests: AGENTS.md exists and stays short; handoff contains the three families
(`SECURITIES API` / `FUTURES QUOTE API` / `FUTURES TRADING API`, `YuantaQuote` vs `YuantaOrd`), states
`Yuanta futures unavailable != system blocked` and cash/futures identity separation, forbids
re-promoting SPARK as the futures quote provider; bootstrap has no mutating git/fs verbs and no
secret access (`win32cred`/`CredRead`/`getpass`/`credential_store` absent).

## F. Legacy EASYWIN canonical symbol fix
Official local sample fact: T/T+1 are distinguished by `ReqType=1/2`; historical T+1 `reg_Ses2.log`
used base symbol `TXFL7` (not `TXFL7PM`); official Python sample default `UpdateMode=4-SnapshotUpd`,
`SetMap=0`.
```
resolve_api_symbol(order, session) -> (BASE symbol, ReqType 1|2)   # TMFJ6 + 1 / TMFJ6 + 2
pm_alias_for(symbol) -> symbol + "PM"                              # EasyWin UI/alias metadata only
futures_quote_probe: AddMktReg(symbol, UpdateMode=4, ReqType from session, SetMap=0)
```
`resolve_quote_symbol(..., "T+1")` no longer returns the PM symbol. No Yuanta login/bruteforce was
performed in this round.

## G. Tests
```
test_v2h (2H.1 + 2H.2): 57 passed
V2-A..H: 630 passed
Phase3A: 121 passed
Yuanta focused: 174 passed
full suite: 1636 passed, 20 deselected, 144 warnings
```
New 2H.2 coverage: deterministic artifact identity; prediction digest binds artifacts; bundle atomic
rollback; no secret artifact append after prediction; `generated_at` after origin blocked; raw score
non-probability; uncalibrated event probability non-public; wrong-type pairing blocked;
cross-prediction blocked; unknown artifact blocked; outcome before origin blocked; DB round-trip
identity verifies; append-only API preserved. Handoff/EASYWIN coverage as in section E/F.

## H. Changed files
```
ADD tests/test_v2h2_forecast_artifact.py
ADD tests/test_agent_handoff_contract.py
ADD AGENTS.md
ADD docs/development/AGENT_HANDOFF.md
ADD scripts/agent_bootstrap.ps1
ADD research/phase3/reports/PHASEV2H2_FORECAST_ARTIFACT_HANDOFF_REPORT.md
MOD src/market_ai_hub/research/v2/prediction_audit.py       (2H.1 -> 2H.2)
MOD src/market_ai_hub/integrations/yuanta/easwin_resolver.py (canonical base symbol + ReqType)
MOD src/market_ai_hub/integrations/yuanta/futures_quote_probe.py (UpdateMode 4 / SetMap 0)
MOD docs/architecture/v2-prediction-audit-contract.md
MOD docs/development/project-status.md
MOD tests/test_v2h_prediction_audit.py / test_phase2yg3_yuanta_secret_and_easwin.py
MOD tests/test_challengers_2d1.py / test_research.py / test_tournament.py (build_id)
```

## I. Gate / readiness interpretation
```
PHASEV2H_PREDICTION_AUDIT_DB_FORECAST_ARTIFACT_PASS
V2I_UPSTREAM_EVALUATION_DATA_READY
AGENT_HANDOFF_CONTRACT_READY
```
Even with the gate PASS: the audit DB currently holds **no real settled probabilistic samples**, so
```
V2-I calibration evidence = NONE_YET
CALIBRATED = FORBIDDEN
```
Synthetic tests must never be used to claim market probabilities are calibrated.

## J. Safety
```
model training: NO · calibration fitting: NO · Brier/log-loss: NO · broker order: NO · trading: NO
recorder: NO · V2-I implementation: NO · production audit DB written by tests: NO
```

STOPPED AFTER V2-H 2H.2 FORECAST-ARTIFACT / AGENT-HANDOFF CLOSURE.
V2-I NOT STARTED.
