"""Ensemble（spec §23 + V1 remediation + V1.1）。

V1.1 語義分層：
- price_ensemble：只聚合 PRICE_FORECAST 模型（Chronos/TimesFM [+FinCast bridge 不進]）
  的真 quantile（quantile_type=PREDICTIVE 且 quantile_valid=true）。
  分類器 heuristic spread 永不進入價格 quantile。
- direction_ensemble：只聚合 DIRECTION_CLASSIFICATION 模型的方向與 class probabilities。
- 舊欄位 point_forecast/quantiles/direction 保留為 legacy_research_only blend view。
- 任何模型皆 UNVALIDATED/EXPERIMENTAL → validation_level=RESEARCH，不得稱 validated ensemble。
- component table：role / status / eligible / raw_weight / effective_weight / excluded_reason。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import numpy as np

from market_ai_hub.schemas.market_data import (
    DataGrade,
    EngineeringStatus,
    ForecastOutput,
    ModelRole,
    ModelTask,
    PredictiveValidationStatus,
    QuantileType,
)
from market_ai_hub.services.build_info import build_fingerprint

log = logging.getLogger(__name__)

EXCLUDED_VALIDATION = {PredictiveValidationStatus.REJECTED.value}


def _component_table(forecasts: list[ForecastOutput], weights: np.ndarray, excluded: list[str]) -> list[dict]:
    out = []
    for f, w in zip(forecasts, weights):
        if f.model in excluded:
            status = "excluded"
            reason = "engineering FAIL or predictive REJECTED"
            eff = 0.0
        elif not f.eligible_for_ensemble_weighting and f.model_task != ModelTask.PRICE_FORECAST.value:
            status = "excluded"
            reason = "eligible_for_ensemble_weighting=false"
            eff = 0.0
        else:
            status = "included"
            reason = ""
            eff = float(w)
        out.append({
            "component": f.model,
            "role": f.model_role,
            "model_task": f.model_task,
            "engineering_status": f.engineering_status,
            "predictive_validation_status": f.predictive_validation_status,
            "eligible": status == "included",
            "raw_weight": float(w) if status == "included" else 0.0,
            "effective_weight": eff,
            "excluded_reason": reason,
        })
    return out


def _eligible_components(forecasts: list[ForecastOutput]) -> tuple[list[ForecastOutput], list[str]]:
    ok, excluded = [], []
    for f in forecasts:
        if f.engineering_status == EngineeringStatus.FAIL.value or f.predictive_validation_status in EXCLUDED_VALIDATION:
            excluded.append(f.model)
        else:
            ok.append(f)
    return ok, excluded


def ensemble_equal_weight(forecasts: list[ForecastOutput], symbol: str, horizon: str) -> ForecastOutput:
    if not forecasts:
        raise ValueError("no forecasts to ensemble")
    eligible, excluded = _eligible_components(forecasts)
    if not eligible:
        raise ValueError("no eligible components (all excluded)")
    weights = np.ones(len(eligible)) / len(eligible)
    return _combine(eligible, weights, symbol, horizon, excluded, "EQUAL_WEIGHT_RESEARCH")


def ensemble_performance_weighted(
    forecasts: list[ForecastOutput],
    symbol: str,
    horizon: str,
    performance: dict[str, float] | None = None,
) -> ForecastOutput:
    """performance-weighted ensemble（V1.1 仍為 EXPERIMENTAL；無足夠可靠 OOS 指標時 fallback equal）。"""
    if not performance or sum(1 for f in forecasts if f.model in performance) < 3:
        return ensemble_equal_weight(forecasts, symbol, horizon)
    eligible, excluded = _eligible_components(forecasts)
    if not eligible:
        raise ValueError("no eligible components (all excluded)")
    w = np.array([performance.get(f.model, 0.0) for f in eligible], dtype=float)
    if w.sum() <= 0:
        return ensemble_equal_weight(forecasts, symbol, horizon)
    return _combine(eligible, w / w.sum(), symbol, horizon, excluded, "PERFORMANCE_WEIGHTED")


def _price_components(forecasts: list[ForecastOutput]) -> list[ForecastOutput]:
    """PRICE_FORECAST 且 quantile contract 合法（quantile_valid=True 或 NOT_AVAILABLE 但有 path）。"""
    out = []
    for f in forecasts:
        if f.model_task != ModelTask.PRICE_FORECAST.value:
            continue
        if f.quantile_type == QuantileType.PREDICTIVE.value and f.quantile_valid is False:
            continue  # invalid quantile 不得進 price aggregation
        out.append(f)
    return out


def _direction_components(forecasts: list[ForecastOutput]) -> list[ForecastOutput]:
    """正式 direction vote 只收 DIRECTION_CLASSIFICATION 且 eligible_for_direction_vote 的 components。"""
    return [
        f for f in forecasts
        if f.model_task == ModelTask.DIRECTION_CLASSIFICATION.value
        and f.eligible_for_direction_vote
    ]


def _direction_research_components(forecasts: list[ForecastOutput]) -> list[ForecastOutput]:
    """raw research view：所有 DIRECTION_CLASSIFICATION（含未驗證）僅供研究資訊，不進正式 vote。"""
    return [f for f in forecasts if f.model_task == ModelTask.DIRECTION_CLASSIFICATION.value]


def _plurality_deterministic(dirs: list[str]) -> tuple[str | None, int]:
    """Deterministic plurality。unique max → (winner, count)；tie → (None, count)。

    取代 max(set(dirs), key=dirs.count)：set 迭代順序在 process 間會變（PYTHONHASHSEED），
    導致平手時 final_direction 依 process 而異。此函式固定回 None（=NO_CONSENSUS）不選邊。
    """
    if not dirs:
        return None, 0
    counts: dict[str, int] = {}
    for d in dirs:
        counts[d] = counts.get(d, 0) + 1
    max_count = max(counts.values())
    winners = [d for d, c in counts.items() if c == max_count]
    if len(winners) == 1:
        return winners[0], max_count
    return None, max_count


def _combine(
    forecasts: list[ForecastOutput],
    weights: np.ndarray,
    symbol: str,
    horizon: str,
    excluded: list[str],
    weighting_method: str,
) -> ForecastOutput:
    n = len(forecasts)

    # ── price ensemble：只聚合 PRICE_FORECAST 的真 quantile / path ──
    price_parts = _price_components(forecasts)
    price_ens: dict = {"status": "NO_PRICE_FORECAST_COMPONENTS"}
    if price_parts:
        pw = np.array([weights[forecasts.index(f)] for f in price_parts], dtype=float)
        pw = pw / pw.sum() if pw.sum() > 0 else np.ones(len(price_parts)) / len(price_parts)
        terminal = float(np.average([f.terminal_forecast or f.point_forecast for f in price_parts], weights=pw))
        exp_ret = float(np.average([f.expected_return for f in price_parts], weights=pw))
        path_components = [f for f in price_parts if f.forecast_path]
        price_path: list[dict] = []
        dates: list[str] = []
        if path_components:
            steps = len(path_components[0].forecast_path)
            ppw = np.array([pw[price_parts.index(f)] for f in path_components], dtype=float)
            ppw = ppw / ppw.sum() if ppw.sum() > 0 else np.ones(len(path_components)) / len(path_components)
            for i in range(steps):
                step_vals = {
                    k: float(np.average([f.forecast_path[i][k] for f in path_components], weights=ppw))
                    for k in ("p10", "p50", "p90")
                }
                price_path.append({"step": i + 1, "date": path_components[0].forecast_path[i]["date"], **step_vals})
            dates = path_components[0].forecast_dates
        # 真 quantile 聚合：只在 quantile_type=PREDICTIVE 的 component 上
        q_parts = [f for f in price_parts if f.quantile_type == QuantileType.PREDICTIVE.value]
        price_quantiles: dict[str, float | None] = {"p10": None, "p50": None, "p90": None}
        quantile_valid = False
        if q_parts:
            qw = np.array([pw[price_parts.index(f)] for f in q_parts], dtype=float)
            qw = qw / qw.sum() if qw.sum() > 0 else np.ones(len(q_parts)) / len(q_parts)
            price_quantiles = {
                "p10": float(np.average([f.quantiles["p10"] for f in q_parts], weights=qw)),
                "p50": float(np.average([f.quantiles["p50"] for f in q_parts], weights=qw)),
                "p90": float(np.average([f.quantiles["p90"] for f in q_parts], weights=qw)),
            }
            quantile_valid = price_quantiles["p10"] <= price_quantiles["p50"] <= price_quantiles["p90"]
            if not quantile_valid:
                price_quantiles = {"p10": None, "p50": None, "p90": None}
        price_ens = {
            "status": "OK",
            "components": [f.model for f in price_parts],
            "component_weights": {f.model: float(pw[price_parts.index(f)]) for f in price_parts},
            "point_forecast": terminal,
            "expected_return": exp_ret,
            "terminal_forecast": terminal,
            "forecast_path": price_path,
            "forecast_dates": dates,
            "quantiles": price_quantiles,
            "quantile_type": QuantileType.PREDICTIVE.value if quantile_valid else QuantileType.NOT_AVAILABLE.value,
            "quantile_valid": quantile_valid if quantile_valid else None,
            "target_calendar": price_parts[0].target_calendar,
            "calendar_grade": price_parts[0].calendar_grade,
        }

    # ── direction ensemble：只聚合 DIRECTION_CLASSIFICATION 且有投票資格的 components ──
    dir_parts = _direction_components(forecasts)
    dir_research = _direction_research_components(forecasts)
    dir_ens: dict = {"status": "NO_DIRECTION_CLASSIFICATION_COMPONENTS"}
    vote_dir = prob_argmax = final_dir = "N/A"
    resolution_method = "no_evidence"
    disagreement = False
    if dir_parts:
        dw = np.array([weights[forecasts.index(f)] for f in dir_parts], dtype=float)
        dw = dw / dw.sum() if dw.sum() > 0 else np.ones(len(dir_parts)) / len(dir_parts)
        dirs = [f.direction for f in dir_parts]
        _, top_count = _plurality_deterministic(dirs)
        keys = sorted({k for f in dir_parts for k in (f.class_probabilities or {})})
        avg_probs = {
            k: float(np.average([(f.class_probabilities or {}).get(k) or 0.0 for f in dir_parts], weights=dw))
            for k in keys
        }
        vote_dir, prob_argmax, final_dir, resolution_method, disagreement = _resolve_direction(
            dirs, avg_probs, None
        )
        dir_ens = {
            "status": "OK",
            "components": [f.model for f in dir_parts],
            "component_weights": {f.model: float(dw[dir_parts.index(f)]) for f in dir_parts},
            "eligible_direction_vote_count": len(dir_parts),
            # raw research view（與正式 vote 分離；未驗證 classifier 不得寫入 final_direction）
            "raw_direction_research": {
                "raw_component_directions": [f.direction for f in dir_research],
                "raw_class_scores": _raw_class_scores(dir_research),
                "raw_argmax": _raw_argmax(dir_research),
                "unvalidated_components": [f.model for f in dir_research if not f.eligible_for_direction_vote],
            },
            "vote_direction": vote_dir,
            "vote_direction_count": top_count,
            "probability_argmax_direction": prob_argmax,
            "final_direction": final_dir,
            "direction_resolution_method": resolution_method,
            "direction_disagreement": disagreement,
            "class_probabilities": avg_probs,
            "class_probabilities_calibrated": False,
            # 舊欄位（backward compat）= final_direction
            "direction": final_dir,
            "direction_vote_count": top_count,
        }
    else:
        # 無 eligible direction vote（含：無分類器 或 分類器全未驗證）
        # 未驗證 XGB/LGBM 仍保留研究資訊（raw research，非正式 validated direction）
        dir_ens = {
            "status": "NO_ELIGIBLE_VOTES" if dir_research else "NO_DIRECTION_CLASSIFICATION_COMPONENTS",
            "components": [],
            "eligible_direction_vote_count": 0,
            "raw_direction_research": {
                "raw_component_directions": [f.direction for f in dir_research],
                "raw_class_scores": _raw_class_scores(dir_research),
                "raw_argmax": _raw_argmax(dir_research),
                "unvalidated_components": [f.model for f in dir_research if not f.eligible_for_direction_vote],
            },
            "vote_direction": "N/A",
            "probability_argmax_direction": "N/A",
            "final_direction": "NO_VALIDATED_MODEL_CONSENSUS",
            "direction_resolution_method": "NO_ELIGIBLE_VOTES",
            "direction_disagreement": False,
            "class_probabilities": {},
            "class_probabilities_calibrated": False,
            "direction": "NO_VALIDATED_MODEL_CONSENSUS",
            "direction_vote_count": 0,
        }
        vote_dir, prob_argmax, final_dir, resolution_method = (
            "N/A", "N/A", "NO_VALIDATED_MODEL_CONSENSUS", "NO_ELIGIBLE_VOTES",
        )

    # ── 整體 ensemble 的 direction：無 eligible classifier vote → NO_VALIDATED_MODEL_CONSENSUS ──
    # price direction 只是 research 資訊，不再冒充 final_direction（V2 移除 price_plurality fallback）。

    # ── legacy blend view（backward compatible；legacy_research_only）──
    p50_legacy = float(np.average([f.point_forecast for f in forecasts], weights=weights))
    exp_ret_legacy = float(np.average([f.expected_return for f in forecasts], weights=weights))
    directions = [f.direction for f in forecasts]
    direction_legacy, _ = _plurality_deterministic(directions)
    direction_legacy = direction_legacy if direction_legacy is not None else "TIE"
    agree_ratio = directions.count(direction_legacy) / len(directions)
    agreement = "HIGH" if agree_ratio >= 0.75 else ("MEDIUM" if agree_ratio >= 0.5 else "LOW")

    # ── V2 validated direction agreement（HIGH-4 fix）：只算 eligible voters ──
    eligible_dir_voters = [f.direction for f in forecasts if f.eligible_for_direction_vote]
    if eligible_dir_voters:
        _, v_count = _plurality_deterministic(eligible_dir_voters)
        v_ratio = v_count / len(eligible_dir_voters)
        validated_direction_agreement = "HIGH" if v_ratio >= 0.75 else ("MEDIUM" if v_ratio >= 0.5 else "LOW")
    else:
        validated_direction_agreement = "N/A"

    any_validated = any(
        f.predictive_validation_status == PredictiveValidationStatus.VALIDATED.value for f in forecasts
    )
    validation_level = "VALIDATED" if any_validated else "RESEARCH"

    n_base = sum(1 for f in forecasts if f.model_role == ModelRole.BASE_MODEL.value)
    n_price_eligible = sum(1 for f in forecasts if f.eligible_for_price_reference and f.model_task == ModelTask.PRICE_FORECAST.value)
    n_vote_eligible = sum(1 for f in forecasts if f.eligible_for_direction_vote)

    warnings = [
        f"model_agreement={agreement}",
        f"weighting_method={weighting_method}",
        f"experimental=True",
        f"validation_level={validation_level}",
        "legacy blend view is research-only; use price_ensemble / direction_ensemble fields",
    ]
    if excluded:
        warnings.append(f"excluded_components={excluded}; weights renormalized over remaining {n} components")
    if not price_parts and dir_parts:
        warnings.append("no PRICE_FORECAST components; price quantiles NOT_AVAILABLE")
    if not any(f.quantile_type == QuantileType.PREDICTIVE.value and f.quantile_valid for f in forecasts):
        warnings.append("no valid predictive quantiles available in ensemble")

    fo = ForecastOutput(
        model="ensemble",
        symbol=symbol,
        as_of=datetime.now(timezone.utc),
        horizon=horizon,
        point_forecast=p50_legacy,
        expected_return=exp_ret_legacy,
        quantiles=price_ens.get("quantiles", {"p10": None, "p50": None, "p90": None}),
        direction=direction_legacy,
        confidence=float(np.average([f.confidence for f in forecasts], weights=weights)),
        data_grade=forecasts[0].data_grade,
        requested_horizon=horizon,
        effective_horizon_steps=forecasts[0].effective_horizon_steps,
        data_frequency=forecasts[0].data_frequency,
        horizon_applied=bool(forecasts[0].horizon_applied),
        forecast_path=price_ens.get("forecast_path", []),
        forecast_dates=price_ens.get("forecast_dates", []),
        terminal_forecast=price_ens.get("terminal_forecast"),
        model_role=ModelRole.ENSEMBLE.value,
        engineering_status=EngineeringStatus.PASS.value,
        predictive_validation_status=PredictiveValidationStatus.UNVALIDATED.value,
        eligible_for_price_reference=bool(price_parts),
        eligible_for_direction_vote=False,
        eligible_for_ensemble_weighting=False,
        model_task="",
        quantile_type=price_ens.get("quantile_type", QuantileType.NOT_AVAILABLE.value),
        quantile_valid=price_ens.get("quantile_valid"),
        target_calendar=price_ens.get("target_calendar", ""),
        calendar_grade=price_ens.get("calendar_grade", ""),
        model_metadata={
            "component_models": [f.model for f in forecasts],
            "weights": {f.model: float(w) for f, w in zip(forecasts, weights)},
            "weighting_method": weighting_method,
            "experimental": True,
            "validation_level": validation_level,
            "excluded_components": excluded,
            "component_table": _component_table(forecasts, weights, excluded),
            "price_ensemble": price_ens,
            "direction_ensemble": dir_ens,
            "independent_base_model_count": n_base,
            "eligible_direction_vote_count": n_vote_eligible,
            "eligible_price_reference_count": n_price_eligible,
            "legacy_research_only": True,
            # raw agreement（全部 component，含 unvalidated）→ 更名，不得當 direction consensus
            "legacy_raw_unvalidated_agreement": agreement,
            "model_agreement": agreement,  # backward compat alias（raw；不得當 consensus）
            # validated agreement（只算 eligible voters；0 → N/A）
            "validated_direction_agreement": validated_direction_agreement,
            # V1.2 direction resolution（final_direction 由固定規則產生，見 _resolve_direction）
            "final_direction": final_dir,
            "direction_resolution_method": resolution_method,
            "direction_disagreement": disagreement,
            "vote_direction": vote_dir,
            "probability_argmax_direction": prob_argmax,
            # 2Q-F.4：單一 authoritative direction contract（answer layer 不需自行推理）
            "direction_status": _direction_status(final_dir),
            "direction_value": _direction_value(final_dir),
        },
        warnings=warnings,
    )
    return fo.attach_build(build_fingerprint())


def model_agreement(forecasts: list[ForecastOutput]) -> str:
    if not forecasts:
        return "LOW"
    directions = [f.direction for f in forecasts]
    _, max_count = _plurality_deterministic(directions)
    ratio = max_count / len(directions)
    return "HIGH" if ratio >= 0.75 else ("MEDIUM" if ratio >= 0.5 else "LOW")


_DIR_CLASS = {-1: "down", 0: "flat", 1: "up"}


def _resolve_direction(
    component_directions: list[str],
    avg_probs: dict[str, float],
    price_dir: str | None,
) -> tuple[str, str, str, str, bool]:
    """V2 direction resolution（固定規則，寫死在 code；deterministic across process restart）。

    - vote_direction：eligible classifier component direction 的 deterministic plurality
      （平手 → "TIE"，不依 set iteration order 選邊）
    - probability_argmax_direction：aggregated class probability 的 deterministic argmax
    - final_direction：vote 唯一勝出 → vote；vote 平手 → NO_CONSENSUS；
      無 vote → NO_VALIDATED_MODEL_CONSENSUS。
    - price_dir 不再進入 final_direction（price 只是 research 資訊，不是 direction vote）。
    """
    if component_directions:
        vote, _ = _plurality_deterministic(component_directions)
        vote = vote if vote is not None else "TIE"
    else:
        vote = "N/A"

    prob_argmax = "N/A"
    if avg_probs:
        # deterministic argmax：sorted keys 固定迭代順序，value 平手時選字典序最小 key
        best_key = max(sorted(avg_probs), key=lambda k: (avg_probs[k] or 0.0, -_dir_index(k)))
        try:
            c = int(best_key.split("_")[-1])
            prob_argmax = _DIR_CLASS.get(c, "N/A")
        except (ValueError, IndexError):
            prob_argmax = "N/A"

    if vote == "TIE":
        final, method = "NO_CONSENSUS", "TIE"
    elif vote != "N/A":
        final, method = vote, "vote_priority"
    else:
        final, method = "NO_VALIDATED_MODEL_CONSENSUS", "NO_ELIGIBLE_VOTES"

    disagreement = (vote not in ("N/A", "TIE") and prob_argmax != "N/A" and vote != prob_argmax)
    return vote, prob_argmax, final, method, disagreement


def _dir_index(key: str) -> int:
    """class_<c> → 數值 c（供 deterministic argmax tie-break）。"""
    try:
        return int(key.split("_")[-1])
    except (ValueError, IndexError):
        return 0


def _direction_status(final_dir: str) -> str:
    """2Q-F.4：authoritative direction status（enum-like）。"""
    if final_dir in ("NO_VALIDATED_MODEL_CONSENSUS", "no_evidence"):
        return "NO_VALIDATED_MODEL_CONSENSUS"
    if final_dir == "NO_CONSENSUS":
        return "NO_CONSENSUS"
    return "VALIDATED_CONSENSUS"


def _direction_value(final_dir: str) -> str | None:
    """2Q-F.4：無 validated consensus 時回 None（不輸出 up/down/flat）。"""
    if final_dir in ("NO_VALIDATED_MODEL_CONSENSUS", "NO_CONSENSUS", "no_evidence", "N/A"):
        return None
    return final_dir


def _raw_class_scores(components: list[ForecastOutput]) -> dict[str, dict[str, float | None]]:
    """raw research class scores（未校準原始分數，不稱 probability）。"""
    out: dict[str, dict[str, float | None]] = {}
    for f in components:
        out[f.model] = f.class_probabilities or {}
    return out


def _raw_argmax(components: list[ForecastOutput]) -> dict[str, str]:
    """raw argmax（deterministic：sorted keys）。未驗證分類器的研究資訊，非正式方向。"""
    out: dict[str, str] = {}
    for f in components:
        probs = f.class_probabilities or {}
        if not probs:
            out[f.model] = "N/A"
            continue
        best_key = max(sorted(probs), key=lambda k: (probs[k] or 0.0, -_dir_index(k)))
        try:
            c = int(best_key.split("_")[-1])
            out[f.model] = _DIR_CLASS.get(c, "N/A")
        except (ValueError, IndexError):
            out[f.model] = "N/A"
    return out


def independent_vote_summary(forecasts: list[ForecastOutput]) -> dict:
    """V1.1 count semantics：把「模型存在」與「有投票資格」分開計數。"""
    base = [f for f in forecasts if f.model_role == ModelRole.BASE_MODEL.value]
    voters = [f for f in base if f.eligible_for_direction_vote]
    price_ref = [f for f in base if f.eligible_for_price_reference and f.model_task == ModelTask.PRICE_FORECAST.value]
    votes = {f.model: f.direction for f in voters}
    if not votes:
        agreement = "N/A"
    else:
        directions = list(votes.values())
        _, max_count = _plurality_deterministic(directions)
        ratio = max_count / len(directions)
        agreement = "HIGH" if ratio >= 0.75 else ("MEDIUM" if ratio >= 0.5 else "LOW")
    return {
        "independent_base_model_count": len(base),
        "eligible_direction_vote_count": len(voters),
        "eligible_price_reference_count": len(price_ref),
        "independent_direction_votes": votes,
        "independent_model_agreement": agreement,
        # 舊欄位保留（backward compat，等同 independent_base_model_count 的舊語義）
        "independent_model_count": len(base),
    }
