# LABEL LEAKAGE AUDIT (V2)

## Current labels (verified)

- `future_return_k = close.shift(-k)/close - 1` (`features/features.py:93`).
- 3-class `make_classification_labels(threshold=0.005)` (`features/features.py:128`).
- Training split: `baseline_ml.py:146` uses `X_train = feat_df[valid].iloc[:-horizon_steps]` and
  `y_train = y[valid][:-horizon_steps]` — a **chronological left-side train** with the last k rows
  reserved for label alignment. This is a single chronological split, **not** a rolling walk-forward.

## Leakage findings

| Item | Verdict | Evidence |
|---|---|---|
| `future_return_*` fed as features? | **NO** (correctly excluded) | `FEATURE_INPUT` (`baseline_ml.py:54`) excludes `future_return_1/3`; `FEATURE_COLUMNS` (`features.py:20`) lists them as labels |
| Rolling features left-closed? | YES | `rolling`/`ewm` are backward-looking by construction |
| `distance_from_ma20` denominator | guarded (0→NaN) | `features.py` `.replace(0, np.nan)` |
| Cross-market future leakage | guarded | `forecast/leakage.py` rejects `ACTUAL_FUTURE` for `NQ_tomorrow/USDJPY_tomorrow/VIX_tomorrow/US10Y_tomorrow/SOX_tomorrow` |
| VWAP / session-high / volume-profile look-ahead | **N/A today** (features absent) — but flagged `HIGH_LEAKAGE_RISK` for future | must be built as-of bar timestamp |
| Point-in-time join | **GAP** — no revision-aware join | feature store only stores `close` |

## Future label look-ahead rules (design)

1. Any barrier/event label (`touch/break/acceptance`) must be computed from a **forward window
   that starts strictly after** the feature cutoff (`feature_cutoff_timestamp`).
2. `Volume Profile` at 10:00 may only use volume **up to 10:00** (as-of), never after.
3. Session high/low must use the session **so far**, not the full session.
4. Contract roll / continuous series must carry roll state and never splice across a roll
   boundary into a label.
5. Macro releases must be revision-aware (first-release vs revised).

## Calibration window separation (already enforced)

`CalibrationEvidence` requires disjoint `fit_window_*` vs `evaluation_window_*`
(`CALIBRATION_TEMPORAL_LEAKAGE`) and forbids `FINAL_OOS` fit (`CALIBRATION_PARTITION_VIOLATION`).
See `price_probability_map.py`.
