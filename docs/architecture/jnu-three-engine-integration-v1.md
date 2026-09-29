# JNU Three-Engine Adapter

Authority: `fishke22/jerry-backtest-lab:config/jnu_three_engine_analysis_contract_v1.json`.

MARKET_AI_HUB remains the local compute/data/model engine. This adapter does not copy JNU Research rules and does not turn agreement into a majority vote. It emits a contract-shaped record and a lossless fusion envelope.

## Contract hardening

- Directional bias, confidence class and market regime fail closed on the authority enums.
- Evidence Fusion always emits `ABSTAIN`; two agreeing engines never outvote a dissenting engine.
- The original engine records remain lossless in `model_evidence.engine_records`. A supplemental `model_evidence.evidence_dimensions` index keeps `STRUCTURE`, `QUANT`, `MACRO`, `EVENT_RISK` and `DATA_QUALITY` separate without adding weights.
- An Acceptance claim requires an explicit finite `level`. Touch, Break and Acceptance remain distinct semantics; the adapter does not synthesize support/resistance.
- Ledger outcomes accept only `1h`, `4h`, `session_close`, `next_session`, `1d`, or `5d`.
- `validation_claims` are always fail-closed in this adapter and cannot be promoted by nested model evidence.

## Local validation boundary

Local validation is componentwise: Yuanta runtime, JNU exact/live contract identity, session semantics, Chronos runtime, TimesFM research runtime and MCP runtime each have an independent `PENDING|VERIFIED|FAILED|NOT_APPLICABLE` state. The summary is `LOCAL_VALIDATION_PENDING`, `LOCAL_VALIDATION_PARTIAL`, `LOCAL_VALIDATION_VERIFIED`, or `LOCAL_VALIDATION_FAILED`; a caller cannot turn one verified component into a blanket pass.

The 2026-09-29 host validation is external evidence for review, not a hard-coded default. Runtime records must explicitly supply their component status; otherwise every component remains pending. This preserves portability to other machines and prevents stale host evidence from silently upgrading a new run.

## Forward validation

Forecast snapshots are immutable records. Outcomes append by forecast hash. Reanalysis must be a new analysis/snapshot and must never replace the original forecast. Runtime/engineering verification does not establish predictive gain, calibrated probability, or trading edge.
