"""Append-only JNU three-engine forward-validation ledger primitives."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib, json

def _canonical(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def record_hash(record: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(record).encode("utf-8")).hexdigest()

def build_forecast_snapshot(analysis: dict[str, Any]) -> dict[str, Any]:
    body = {"record_type":"FORECAST_SNAPSHOT","recorded_at":datetime.now(timezone.utc).isoformat(),"analysis":analysis}
    body["record_hash"] = record_hash(body)
    return body

def build_outcome_record(*, forecast_hash: str, horizon: str, outcome: dict[str, Any]) -> dict[str, Any]:
    body={"record_type":"OUTCOME","recorded_at":datetime.now(timezone.utc).isoformat(),"forecast_hash":forecast_hash,"horizon":horizon,"outcome":outcome}
    body["record_hash"]=record_hash(body)
    return body

def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(_canonical(record)+"\n")
