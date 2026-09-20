# Changelog

Release history organized by product capability. Detailed engineering phase history is preserved
under [`research/`](research/README.md).

## v2.0.0-rc1 (2026-09-20)

### Added

- Three first-class target families: `OSAKA_MICRO`, `TAIWAN_STOCK`, `TAIWAN_INDEX`
  (`config/primary_market_mission.yaml`, `config/primary_targets.yaml`).
- 21 MCP tools over a stdio server, including `get_analysis_packet`, `analyze_osaka_nikkei`,
  `analyze_taiwan_stock`, `get_research_gates`, `get_forward_test_status`.
- 3 packaged agent skills (`osaka-micro-analysis`, `taiwan-stock-v28`, `model-validation-audit`).
- Chronological walk-forward / out-of-sample validation framework
  (`research/historical_learning.py`) with train/validation/final-holdout isolation and
  training-only MASE scaling.
- Compute resource governor (`DESKTOP_SAFE` default; `AUTO_TRAIN/AUTO_FINE_TUNE/AUTO_PROMOTE = false`).
- Target-family runtime isolation — no cross-market data contamination between Osaka and Taiwan.

### Validation

- Osaka proxy OOS: `NO_EVIDENCE`.
- Direct Micro historical OOS: `STATISTICAL_FORECAST_EVIDENCE` (VAR(1), non-executable).
- Causal: `NON_EXECUTABLE_FORECAST_EDGE`. Economic: `NO_ECONOMIC_EDGE`.
- Trading readiness: `RESEARCH_ONLY`. Strategy/production candidate: `NONE`.

### Known limitations

- No executable trading edge (statistical signal is non-causal).
- Forward evidence `NONE_YET` at activation.
- 225LABO data is `LOCAL_ONLY` (manual download, never redistributed).

---

See the [release snapshot](research/releases/v2.0.0-rc1/) for the immutable `v2.0.0-rc1` manifest
and checklist.
