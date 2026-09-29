# JNU Three-Engine Adapter

Authority: `fishke22/jerry-backtest-lab:config/jnu_three_engine_analysis_contract_v1.json`.

MARKET_AI_HUB remains the local compute/data/model engine. This adapter does not copy JNU Research rules and does not turn agreement into a majority vote. It emits a contract-shaped record and a lossless fusion envelope.

## Local validation boundary

This branch was authored while the user's MARKET_AI_HUB PC was offline. Anything requiring `D:\MARKET_AI_HUB`, Yuanta callbacks, local model weights, local-only/licensed data, scheduler state or MCP runtime is **LOCAL_VALIDATION_PENDING**.

Before merging locally, compare the local working tree and commits against the GitHub branch. Never reset/overwrite unpushed local work. Rebase/cherry-pick deliberately, run the full existing test suite, then run `tests/test_jnu_three_engine.py`. Only after local runtime checks pass may the pending marker be removed.

## Forward validation

Forecast snapshots are immutable records. Outcomes append by forecast hash. Reanalysis must be a new analysis/snapshot and must never replace the original forecast.
