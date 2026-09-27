"""Historical prequential replay for exact-contract JNU settlement research.

This module intentionally separates retrospective pseudo-forward evidence from
W3.2 real forward evidence.  Each replay sample freezes one exact contract at
one historical origin, gives the model only the preceding context through that
origin, and reveals the next exact-contract settlement only after forecasting.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from market_ai_hub.automation.data_lake import default_data_root
from market_ai_hub.config.settings import project_root
from market_ai_hub.integrations.yuanta.resolver import ose_last_trading_date
from market_ai_hub.research.paired_uncertainty import paired_block_bootstrap_ci
from market_ai_hub.research.tournament import get_model_entry
from market_ai_hub.schemas.market_data import validate_price_path
from market_ai_hub.services.calendar import next_ose_derivatives_session
from market_ai_hub.services.validation import (
    drift_baseline,
    evaluate_against_baselines,
    moving_average_baseline,
)
from market_ai_hub.targets.jpx_daily import JPXOSEDailyReportProvider


HISTORICAL_PREQUENTIAL_SCHEMA_VERSION = "HPQ1"
DEFAULT_PROTOCOL_ID = "jnu_front_exact_settlement_1d_v1"
DEFAULT_PROTOCOL_PATH = project_root() / "config" / "historical_prequential_protocols.yaml"


@dataclass(frozen=True)
class HistoricalPrequentialProtocol:
    protocol_id: str
    market_family: str
    product: str
    target_field: str
    horizon_steps: int
    history_len: int
    contract_rule: str
    source_scope: str
    source_availability_semantics: str
    development_origin_end: date
    validation_origin_end: date
    final_holdout_origin_end: date
    boundary_selection_basis: str
    final_holdout_one_use: bool
    model_training_cutoff_policy: str


@dataclass(frozen=True)
class ReplayOrigin:
    origin_date: date
    target_date: date
    contract_month: str
    partition: str
    context: pd.Series
    actual: float
    origin_price: float
    source_hash: str
    target_source_hash: str

    @property
    def context_hash(self) -> str:
        arr = np.asarray(self.context, dtype=np.float32)
        return hashlib.sha256(arr.tobytes()).hexdigest()[:16]


def load_protocol(
    protocol_id: str = DEFAULT_PROTOCOL_ID,
    path: str | Path | None = None,
) -> HistoricalPrequentialProtocol:
    p = Path(path) if path is not None else DEFAULT_PROTOCOL_PATH
    payload = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if str(payload.get("schema_version")) != HISTORICAL_PREQUENTIAL_SCHEMA_VERSION:
        raise ValueError("historical prequential protocol schema mismatch")
    raw = (payload.get("protocols") or {}).get(protocol_id)
    if not isinstance(raw, dict):
        raise KeyError(protocol_id)
    return HistoricalPrequentialProtocol(
        protocol_id=protocol_id,
        market_family=str(raw["market_family"]),
        product=str(raw["product"]),
        target_field=str(raw["target_field"]),
        horizon_steps=int(raw["horizon_steps"]),
        history_len=int(raw["history_len"]),
        contract_rule=str(raw["contract_rule"]),
        source_scope=str(raw["source_scope"]),
        source_availability_semantics=str(raw["source_availability_semantics"]),
        development_origin_end=date.fromisoformat(str(raw["development_origin_end"])),
        validation_origin_end=date.fromisoformat(str(raw["validation_origin_end"])),
        final_holdout_origin_end=date.fromisoformat(str(raw["final_holdout_origin_end"])),
        boundary_selection_basis=str(raw["boundary_selection_basis"]),
        final_holdout_one_use=bool(raw["final_holdout_one_use"]),
        model_training_cutoff_policy=str(raw["model_training_cutoff_policy"]),
    )


def _partition(origin: date, protocol: HistoricalPrequentialProtocol) -> str | None:
    if origin <= protocol.development_origin_end:
        return "HISTORICAL_DEVELOPMENT"
    if origin <= protocol.validation_origin_end:
        return "HISTORICAL_VALIDATION"
    if origin <= protocol.final_holdout_origin_end:
        return "HISTORICAL_FINAL_HOLDOUT"
    return None


def _normalized_source_frame(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"contract_month", "date", "settlement"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"missing source columns: {sorted(missing)}")
    df = frame.copy()
    df["contract_month"] = df["contract_month"].astype(str)
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df["settlement"] = pd.to_numeric(df["settlement"], errors="coerce")
    if "source_hash" not in df.columns:
        df["source_hash"] = ""
    df["source_hash"] = df["source_hash"].fillna("").astype(str)
    df = df.dropna(subset=["date", "settlement"])
    df = df[np.isfinite(df["settlement"]) & (df["settlement"] > 0)]
    df = df.sort_values(["contract_month", "date", "source_hash"]).drop_duplicates(
        subset=["contract_month", "date"], keep="last"
    )
    return df.reset_index(drop=True)


def load_jnu_public_source_frame() -> pd.DataFrame:
    """Load only persisted JPX public OSE daily-report Micro settlements."""
    return _normalized_source_frame(JPXOSEDailyReportProvider().load("Nikkei 225 Micro"))


def build_front_contract_origins(
    frame: pd.DataFrame,
    protocol: HistoricalPrequentialProtocol,
) -> list[ReplayOrigin]:
    """Build one exact-contract sample per origin date with no roll stitching."""
    df = _normalized_source_frame(frame)
    if df.empty:
        return []
    by_contract: dict[str, pd.DataFrame] = {}
    candidates: dict[date, list[ReplayOrigin]] = {}
    for contract, g in df.groupby("contract_month", sort=True):
        if len(contract) != 6 or not contract.isdigit():
            continue
        expiry = ose_last_trading_date(int(contract[:4]), int(contract[4:]))
        g = g.sort_values("date").reset_index(drop=True)
        by_contract[contract] = g
        for pos in range(protocol.history_len - 1, len(g) - 1):
            origin_date = g.loc[pos, "date"]
            target_date = g.loc[pos + 1, "date"]
            if str(target_date) != next_ose_derivatives_session(origin_date):
                continue
            if origin_date > expiry or target_date > expiry:
                continue
            part = _partition(origin_date, protocol)
            if part is None:
                continue
            ctx_rows = g.iloc[pos - protocol.history_len + 1 : pos + 1]
            if len(ctx_rows) != protocol.history_len:
                continue
            ctx_index = (pd.DatetimeIndex(pd.to_datetime(ctx_rows["date"])).tz_localize("Asia/Tokyo") + pd.Timedelta(hours=15, minutes=45)).tz_convert("UTC")
            context = pd.Series(
                ctx_rows["settlement"].astype(float).to_numpy(),
                index=pd.DatetimeIndex(ctx_index),
                name="settlement",
            )
            sample = ReplayOrigin(
                origin_date=origin_date,
                target_date=target_date,
                contract_month=contract,
                partition=part,
                context=context,
                actual=float(g.loc[pos + 1, "settlement"]),
                origin_price=float(g.loc[pos, "settlement"]),
                source_hash=str(g.loc[pos, "source_hash"]),
                target_source_hash=str(g.loc[pos + 1, "source_hash"]),
            )
            candidates.setdefault(origin_date, []).append(sample)

    out = []
    for origin_date in sorted(candidates):
        # Front exact contract = nearest expiry month among eligible exact contracts.
        out.append(sorted(candidates[origin_date], key=lambda x: x.contract_month)[0])
    return out


def source_fingerprint(origins: list[ReplayOrigin]) -> str:
    payload = [
        {
            "origin": str(x.origin_date),
            "target": str(x.target_date),
            "contract": x.contract_month,
            "origin_price": x.origin_price,
            "actual": x.actual,
            "source_hash": x.source_hash,
            "target_source_hash": x.target_source_hash,
            "context_hash": x.context_hash,
        }
        for x in origins
    ]
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _model_identity(name: str) -> dict[str, Any]:
    entry = get_model_entry(name)
    cutoff = str(entry.get("training_cutoff") or "unknown")
    return {
        "name": name,
        "model_id": str(entry.get("model_id") or ""),
        "revision": str(entry.get("revision") or "unknown"),
        "training_cutoff": cutoff,
        "training_cutoff_known": cutoff.lower() not in {"", "unknown", "n/a"},
    }


def protocol_payload(protocol: HistoricalPrequentialProtocol) -> dict[str, Any]:
    return {
        "schema_version": HISTORICAL_PREQUENTIAL_SCHEMA_VERSION,
        "protocol_id": protocol.protocol_id,
        "market_family": protocol.market_family,
        "product": protocol.product,
        "target_field": protocol.target_field,
        "horizon_steps": protocol.horizon_steps,
        "history_len": protocol.history_len,
        "contract_rule": protocol.contract_rule,
        "source_scope": protocol.source_scope,
        "source_availability_semantics": protocol.source_availability_semantics,
        "development_origin_end": str(protocol.development_origin_end),
        "validation_origin_end": str(protocol.validation_origin_end),
        "final_holdout_origin_end": str(protocol.final_holdout_origin_end),
        "boundary_selection_basis": protocol.boundary_selection_basis,
        "final_holdout_one_use": protocol.final_holdout_one_use,
        "model_training_cutoff_policy": protocol.model_training_cutoff_policy,
    }


def evidence_identity(
    protocol: HistoricalPrequentialProtocol,
    origins: list[ReplayOrigin],
    model_names: tuple[str, ...],
) -> dict[str, Any]:
    models = [_model_identity(x) for x in model_names]
    base = {
        "protocol": protocol_payload(protocol),
        "source_fingerprint": source_fingerprint(origins),
        "models": models,
    }
    raw = json.dumps(base, sort_keys=True, separators=(",", ":")).encode()
    return {**base, "evidence_id": hashlib.sha256(raw).hexdigest()[:24]}


def _metric_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"n": 0, "status": "NO_SAMPLES"}
    actual = np.asarray([r["actual"] for r in rows], dtype=float)
    origin = np.asarray([r["origin_price"] for r in rows], dtype=float)
    forecast = np.asarray([r["p50"] for r in rows], dtype=float)
    drift = np.asarray([r["drift"] for r in rows], dtype=float)
    ma20 = np.asarray([r["ma20"] for r in rows], dtype=float)
    ev = evaluate_against_baselines(
        "JNU_FRONT_EXACT_SETTLEMENT",
        actual,
        origin,
        forecast.tolist(),
        steps=1,
        drift_forecasts=drift,
        moving_average_forecasts=ma20,
    )
    deltas = np.abs(actual - forecast) - np.abs(actual - origin)
    paired = paired_block_bootstrap_ci(deltas, list(range(len(rows))), steps=1)
    paired.update(
        {
            "delta_model_minus_naive": float(deltas.mean()),
            "delta_semantics": "MODEL_MINUS_NAIVE_LOSS_NEGATIVE_FAVORS_MODEL",
        }
    )
    lo = np.asarray([r["p10"] for r in rows], dtype=float)
    hi = np.asarray([r["p90"] for r in rows], dtype=float)
    interval = {
        "nominal_level": 0.8,
        "coverage": float(((actual >= lo) & (actual <= hi)).mean()),
        "mean_width": float(np.mean(hi - lo)),
    }
    return {"n": len(rows), "evaluation": ev, "paired_vs_last_price_naive": paired, "interval": interval}


def run_replay(
    adapters: dict[str, Any],
    *,
    frame: pd.DataFrame | None = None,
    protocol: HistoricalPrequentialProtocol | None = None,
) -> dict[str, Any]:
    protocol = protocol or load_protocol()
    if protocol.horizon_steps != 1:
        raise ValueError("HPQ1 supports only next-observation horizon_steps=1")
    if not adapters:
        raise ValueError("at least one model is required")
    origins = build_front_contract_origins(
        load_jnu_public_source_frame() if frame is None else frame,
        protocol,
    )
    if not origins:
        return {"status": "NO_ELIGIBLE_ORIGINS", "protocol": protocol_payload(protocol)}
    identity = evidence_identity(protocol, origins, tuple(adapters))
    model_results: dict[str, Any] = {}
    for model_name, adapter in adapters.items():
        rows: list[dict[str, Any]] = []
        for sample in origins:
            prediction = adapter.predict(sample.context, horizon=protocol.horizon_steps)
            path = prediction["path"]
            validate_price_path(path, protocol.horizon_steps)
            rows.append(
                {
                    "origin_date": str(sample.origin_date),
                    "target_date": str(sample.target_date),
                    "contract_month": sample.contract_month,
                    "partition": sample.partition,
                    "context_hash": sample.context_hash,
                    "origin_price": sample.origin_price,
                    "actual": sample.actual,
                    "p10": float(path["p10"][-1]),
                    "p50": float(path["p50"][-1]),
                    "p90": float(path["p90"][-1]),
                    "drift": float(drift_baseline(sample.context, 1)),
                    "ma20": float(moving_average_baseline(sample.context, 1, window=min(20, len(sample.context)))),
                    "source_hash": sample.source_hash,
                    "target_source_hash": sample.target_source_hash,
                }
            )
        partitions = {}
        for part in ("HISTORICAL_DEVELOPMENT", "HISTORICAL_VALIDATION", "HISTORICAL_FINAL_HOLDOUT"):
            partitions[part] = _metric_summary([r for r in rows if r["partition"] == part])
        model_results[model_name] = {
            "identity": _model_identity(model_name),
            "all": _metric_summary(rows),
            "partitions": partitions,
            "records": rows,
        }
    cutoff_known = all(x["training_cutoff_known"] for x in identity["models"])
    return {
        "status": "OK",
        "schema_version": HISTORICAL_PREQUENTIAL_SCHEMA_VERSION,
        "evidence_id": identity["evidence_id"],
        "protocol": identity["protocol"],
        "source_fingerprint": identity["source_fingerprint"],
        "origin_count": len(origins),
        "partition_counts": {
            part: sum(x.partition == part for x in origins)
            for part in ("HISTORICAL_DEVELOPMENT", "HISTORICAL_VALIDATION", "HISTORICAL_FINAL_HOLDOUT")
        },
        "first_origin": str(origins[0].origin_date),
        "last_origin": str(origins[-1].origin_date),
        "models": model_results,
        "evidence_grade": (
            "HISTORICAL_PREQUENTIAL_OOS_NOT_VERIFIED"
            if cutoff_known
            else "HISTORICAL_PREQUENTIAL_TRAINING_CUTOFF_UNKNOWN"
        ),
        "sample_origin": "HISTORICAL_PSEUDO_FORWARD",
        "not_forward_evidence": True,
        "not_calibration_evidence": True,
        "not_trading_edge": True,
    }


def evidence_dir(data_root: Path | None = None) -> Path:
    root = data_root or default_data_root()
    return root / "research" / "historical_prequential" / DEFAULT_PROTOCOL_ID


def save_one_use_evidence(result: dict[str, Any], data_root: Path | None = None) -> Path:
    """Exclusively seal the first artifact; only identical content is idempotent."""
    if result.get("status") != "OK":
        raise ValueError("cannot seal non-OK replay")
    out_dir = evidence_dir(data_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    sealed = out_dir / "SEALED.json"
    payload = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    try:
        handle = sealed.open("x", encoding="utf-8")
    except FileExistsError:
        existing = json.loads(sealed.read_text(encoding="utf-8"))
        if existing != result:
            raise RuntimeError("FINAL_HOLDOUT_ALREADY_OPENED_FOR_DIFFERENT_CONTENT")
        return sealed
    # An interrupted write remains a blocking artifact, never silently overwritten.
    with handle:
        handle.write(payload)
    return sealed


def load_sealed_evidence(data_root: Path | None = None) -> dict[str, Any] | None:
    sealed = evidence_dir(data_root) / "SEALED.json"
    if not sealed.exists():
        return None
    return json.loads(sealed.read_text(encoding="utf-8"))


def equal_weight_ensemble_summary(evidence: dict[str, Any]) -> dict[str, Any]:
    """Derive the existing equal-weight JNU ensemble from already sealed records.

    This never invokes a model and never reopens the final holdout.  It is a
    deterministic read-only transformation of forecasts already present in the
    sealed artifact.
    """
    if _horizon_mismatches(evidence):
        return {"status": "BLOCKED_HORIZON_MISMATCH"}
    models = evidence.get("models") or {}
    if len(models) < 2:
        return {"status": "INSUFFICIENT_MODELS"}
    names = sorted(models)
    record_sets = [models[name].get("records") or [] for name in names]
    if not record_sets or not record_sets[0]:
        return {"status": "NO_RECORDS"}
    keys = [
        [(r["origin_date"], r["contract_month"], r["target_date"]) for r in rows]
        for rows in record_sets
    ]
    if any(k != keys[0] for k in keys[1:]):
        return {"status": "BLOCKED_RECORD_IDENTITY_MISMATCH"}

    combined: list[dict[str, Any]] = []
    for i in range(len(record_sets[0])):
        rows = [x[i] for x in record_sets]
        first = rows[0]
        combined.append(
            {
                "origin_date": first["origin_date"],
                "target_date": first["target_date"],
                "contract_month": first["contract_month"],
                "partition": first["partition"],
                "origin_price": first["origin_price"],
                "actual": first["actual"],
                "p10": float(np.mean([r["p10"] for r in rows])),
                "p50": float(np.mean([r["p50"] for r in rows])),
                "p90": float(np.mean([r["p90"] for r in rows])),
                "drift": first["drift"],
                "ma20": first["ma20"],
            }
        )
    partitions = {
        part: _metric_summary([r for r in combined if r["partition"] == part])
        for part in ("HISTORICAL_DEVELOPMENT", "HISTORICAL_VALIDATION", "HISTORICAL_FINAL_HOLDOUT")
    }
    return {
        "status": "OK",
        "method": "equal_weight_sealed_model_forecasts",
        "model_names": names,
        "all": _metric_summary(combined),
        "partitions": partitions,
    }


def _horizon_mismatches(evidence: dict[str, Any]) -> list[dict[str, str]]:
    """Old immutable artifacts still need today's contract checks before reuse."""
    mismatches = []
    for name, model in (evidence.get("models") or {}).items():
        for row in model.get("records") or []:
            expected = next_ose_derivatives_session(row["origin_date"])
            if row["target_date"] != expected:
                mismatches.append({"model": name, "origin_date": row["origin_date"],
                    "target_date": row["target_date"], "expected_target_date": expected})
    return mismatches


def compact_evidence_summary(evidence: dict[str, Any] | None) -> dict[str, Any]:
    """Compact audit/public summary without returning 100s of per-origin records."""
    if not evidence or evidence.get("status") != "OK":
        return {"status": "NOT_AVAILABLE"}
    mismatches = _horizon_mismatches(evidence)
    if mismatches:
        return {"status": "BLOCKED_HORIZON_MISMATCH", "evidence_id": evidence.get("evidence_id"),
                "mismatches": mismatches, "not_forward_evidence": True,
                "not_calibration_evidence": True, "not_trading_edge": True}
    models: dict[str, Any] = {}
    for name, raw in (evidence.get("models") or {}).items():
        models[name] = {
            "identity": raw.get("identity"),
            "all": raw.get("all"),
            "partitions": raw.get("partitions"),
        }
    return {
        "status": "OK",
        "evidence_id": evidence.get("evidence_id"),
        "evidence_grade": evidence.get("evidence_grade"),
        "sample_origin": evidence.get("sample_origin"),
        "origin_count": evidence.get("origin_count"),
        "partition_counts": evidence.get("partition_counts"),
        "first_origin": evidence.get("first_origin"),
        "last_origin": evidence.get("last_origin"),
        "protocol": evidence.get("protocol"),
        "models": models,
        "ensemble": equal_weight_ensemble_summary(evidence),
        "not_forward_evidence": True,
        "not_calibration_evidence": True,
        "not_trading_edge": True,
    }
