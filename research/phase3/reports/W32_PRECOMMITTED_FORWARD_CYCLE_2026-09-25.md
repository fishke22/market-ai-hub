# W3.2 Precommitted Forward Cycle — 2026-09-25

## Result

W3.2 engineering cycle is **PASS**. Actual forward predictive evidence is **NONE_YET**.

Implementation commit: `2f374ad533a74e3647fdfdeb73d9ebb2f379631a`  
Runtime build_id: `81f02a25847b9e65`

## What was added

`src/market_ai_hub/research/v2/forward_cycle.py` connects one minimal direct-market research cycle to
the existing contracts:

1. OSAKA_MICRO / JNU / 1 OSE session;
2. exact contract-specific DAILY close input with PIT/source/roll provenance;
3. existing `last_price_naive` baseline;
4. W3.2 precommit only after 15:45 JST source close and before 17:00 JST target night open;
5. immutable 2H.3 `FORWARD_PRECOMMITTED` prediction, lineage and POINT artifact;
6. target close settlement only after the sealed horizon and only for the same contract;
7. W3.1 `evaluation_as_of` governance;
8. unchanged 2I.1 POINT evaluation.

Feature Store integration is read-only and requires dedicated
`terminal_close / w3.2-contract-daily-close-1` DAILY features. TICK is never silently resampled.

## Fail-closed cases tested

- input not PIT-safe;
- missing source snapshot IDs or contract identity;
- source session not closed;
- forecast attempted after target night session begins;
- input becoming available after forecast origin;
- duplicate same-window precommit;
- settlement before maturity;
- wrong contract/month;
- wrong target session;
- missing outcome source IDs;
- evaluation cutoff before outcome availability;
- current-style TICK input impersonating DAILY;
- missing Feature Store;
- legacy continuous parquet missing forward provenance.

## Validation

- core W3.2 + W3.1 / V2-H / V2-I: 101 passed;
- Feature Store / operator focused regression after final wiring: 127 passed;
- broader W2/W3/legacy-forward/PPM regression: 303 passed, 2 deselected;
- final default profile: **1773 passed, 23 deselected, 132 warnings in 156.48s**, exit 0;
- changed implementation/test secret scan: 0 findings;
- `git diff --check`: PASS.

## Actual runtime readiness

Read-only probe at 2026-09-25 03:08 Asia/Taipei (2026-09-24 19:08 UTC):

- legacy continuous Osaka parquet exists: 960 rows, latest trading date 2026-09-01;
- blocked fields: `available_at`, source snapshot IDs, contract code, contract month and roll provenance;
- canonical Feature Store exists;
- OSE observation count at the probe cutoff: 0;
- eligible W3.2 daily contract-close candidate: none;
- real W3.2 prediction inserted: none.

No raw private quote values were printed or committed.

## What this does not prove

No real forward outcome has matured under W3.2. No probability was fitted or published. No calibration
status changed. No broker login/logout/subscription/restart/account/order action occurred. No scheduler
was enabled.

The next data-engineering package must produce the dedicated PIT-safe contract DAILY close feature
without weakening W2 provenance rules. Until that exists, W3.2 intentionally abstains.
