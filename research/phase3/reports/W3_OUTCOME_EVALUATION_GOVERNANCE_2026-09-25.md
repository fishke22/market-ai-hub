# W3 Outcome / Evaluation Governance — 2026-09-25

## Scope

This bounded package closes the engineering governance gap identified after W2. It does not fit a calibrator, retrain a model, restart the recorder, log in to a broker, query accounts, or create trading instructions.

Implementation commit: `95289de6722c1477c5183e172384a3fd196050fd`  
Runtime build_id: `98fe354dcc4fb275`

## 2H.3 prediction-time sealing

Prediction Audit advances from 2H.2 to 2H.3 while preserving the existing append-only forecast-artifact contract. New prediction identities can bind:

- `sample_origin`: `FORWARD_PRECOMMITTED` or `RETROSPECTIVE_REPLAY` (legacy/default `UNKNOWN` is retained for compatibility but is not governed evidence);
- `label_window_id`;
- timezone-aware `label_window_start` / `label_window_end`.

When the window is sealed, `append_outcome()` rejects an outcome whose `available_at` precedes `label_window_end`, and rejects a `target_period` that differs from `label_window_id`. Therefore `outcome.available_at >= forecast_origin` alone is no longer accepted as maturity evidence for sealed W3 predictions.

The default audit DB now resolves from canonical `MARKET_AI_DATA_ROOT`. A forecast artifact identity already bound to a different prediction returns a typed binding rejection instead of leaking a raw DuckDB primary-key exception.

## W3.1 governed evaluation

`evaluation_governance.py` is an eligibility layer in front of the unchanged V2-I 2I.1 metric engine. It requires explicit timezone-aware `evaluation_as_of` and one exact homogeneous scope across target family, instrument, horizon, model, model version, artifact type, label type, sample origin and, for event probabilities, calibration domain / probability family / event definition.

The gate rejects or excludes:

- horizon not mature at `evaluation_as_of`;
- outcome available only after the requested evaluation cutoff;
- outcome recorded before horizon end;
- target-period / sealed-window mismatch;
- forward-precommitted mixed with retrospective replay;
- wrong model/version/target/horizon/event/label scope;
- duplicate logical samples;
- selected superseded samples;
- unknown sample origin or missing sealed maturity as insufficient evidence.

The manifest reports valid sample count, missing outcomes, event count, observed/expected label windows where the calendar is supported, missing days, horizon overlap and rejection counts.

## Validation

- W3 + V2-H/V2-I focused: `85 passed`.
- W3 + PPM / packet broader regression after schema updates: `236 passed, 1 deselected`.
- Audit-path/build focused after canonical data-root correction: `74 passed`.
- Final default code/test profile: `1749 passed, 23 deselected, 132 warnings in 172.00s`, exit 0.
- Changed implementation/test secret scan: 0 findings; repository historical scanner findings remain separate.
- `git diff --check`: PASS.

## Evidence boundary / remaining work

These tests use temporary synthetic audit records. They prove the engine and leakage gates, not market predictive evidence. There are still no newly established real forward calibration samples in this package, and `CALIBRATION_FITTING` remains `NOT_STARTED` / `CALIBRATED=false`.

Real W3 evidence work still requires precommitted predictions to exist before outcomes and then mature naturally. W4 fitting may start only after enough real, homogeneous, valid samples exist under a frozen evaluation protocol.

Separate unresolved runtime items remain: controlled recorder adoption (maintenance-window authorization required), automatic reconnect, session/contract roll, durable WAL/spool, long-duration stress, and validated TICK→daily aggregation before broker TICK can feed current daily models.
