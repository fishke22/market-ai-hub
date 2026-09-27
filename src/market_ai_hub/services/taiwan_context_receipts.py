"""Append-only, content-addressed receipts for Taiwan target context.

The store captures what was actually retrieved and when. It deliberately does
not turn a live historical query into historical PIT evidence: only receipts
whose retrieved_at was already at or before a later decision time are
selectable for that decision.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

from market_ai_hub.config.runtime_paths import taiwan_context_receipts_root


RECEIPT_SCHEMA_VERSION = "TAIWAN_CONTEXT_RECEIPT_V1"
RECEIPT_POLICY_VERSION = "APPEND_ONLY_CONTENT_ADDRESSED_RECEIPT_TIME_V1"
STATUS_CAPTURED = "CAPTURED"
STATUS_ALREADY_CAPTURED = "ALREADY_CAPTURED"
STATUS_NOT_AVAILABLE_BEFORE_DECISION = "NOT_AVAILABLE_BEFORE_DECISION"


class TaiwanContextReceiptIntegrityError(RuntimeError):
    pass


def _canonical_json(payload: Any) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        allow_nan=False,
    )


def _sha256(payload: Any) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _utc(value: Any, *, field: str) -> pd.Timestamp:
    try:
        ts = pd.Timestamp(value)
    except Exception as exc:
        raise TaiwanContextReceiptIntegrityError(f"{field} invalid") from exc
    if pd.isna(ts):
        raise TaiwanContextReceiptIntegrityError(f"{field} invalid")
    if ts.tzinfo is None:
        raise TaiwanContextReceiptIntegrityError(f"{field} must be timezone-aware")
    return ts.tz_convert("UTC")


def _context_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    payload = dict(snapshot)
    payload.pop("receipt", None)
    payload.pop("receipt_store", None)
    return payload


def _envelope(snapshot: dict[str, Any]) -> dict[str, Any]:
    payload = _context_payload(snapshot)
    stock_id = str(payload.get("stock_id") or "").strip()
    symbol = str(payload.get("symbol") or "").strip()
    if not stock_id or not symbol:
        raise TaiwanContextReceiptIntegrityError("stock_id and symbol required")
    retrieved_at = _utc(payload.get("retrieved_at"), field="retrieved_at")
    cutoff = _utc(payload.get("cutoff") or payload.get("as_of"), field="cutoff")
    payload_hash = _sha256(payload)
    identity_payload = {
        "receipt_schema_version": RECEIPT_SCHEMA_VERSION,
        "receipt_policy_version": RECEIPT_POLICY_VERSION,
        "source_context_schema_version": str(payload.get("schema_version") or ""),
        "stock_id": stock_id,
        "symbol": symbol,
        "cutoff": cutoff.isoformat(),
        "retrieved_at": retrieved_at.isoformat(),
        "payload_hash": payload_hash,
    }
    receipt_id = "tw-context:" + _sha256(identity_payload)[:32]
    return {
        **identity_payload,
        "receipt_id": receipt_id,
        "historical_backfill_eligible": bool(retrieved_at <= cutoff),
        "predictive_feature_allowed": False,
        "context": payload,
    }


def _filename(receipt_id: str) -> str:
    prefix = "tw-context:"
    if not str(receipt_id).startswith(prefix):
        raise TaiwanContextReceiptIntegrityError("receipt_id prefix invalid")
    digest = str(receipt_id)[len(prefix):]
    if len(digest) != 32 or any(ch not in "0123456789abcdef" for ch in digest):
        raise TaiwanContextReceiptIntegrityError("receipt_id digest invalid")
    return digest + ".json"


class TaiwanContextReceiptStore:
    """Filesystem append-only store; existing receipt bytes are never replaced."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else taiwan_context_receipts_root()
        self.snapshots_dir = self.root / "snapshots"

    def _path(self, receipt_id: str) -> Path:
        return self.snapshots_dir / _filename(receipt_id)

    def capture(
        self,
        snapshot: dict[str, Any],
        *,
        observed_at: datetime | str | pd.Timestamp | None = None,
    ) -> dict[str, Any]:
        envelope = _envelope(snapshot)
        retrieved_at = _utc(envelope["retrieved_at"], field="retrieved_at")
        capture_time = _utc(
            datetime.now(timezone.utc) if observed_at is None else observed_at,
            field="observed_at",
        )
        if retrieved_at > capture_time:
            raise TaiwanContextReceiptIntegrityError(
                "retrieved_at cannot be later than receipt capture observation"
            )
        path = self._path(envelope["receipt_id"])
        body = (_canonical_json(envelope) + "\n").encode("utf-8")
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError:
            existing = self.load(envelope["receipt_id"])
            if existing != envelope:
                raise TaiwanContextReceiptIntegrityError(
                    "existing receipt content differs from content-addressed identity"
                )
            return self._capture_result(envelope, status=STATUS_ALREADY_CAPTURED, path=path)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(body)
                fh.flush()
                os.fsync(fh.fileno())
        except Exception:
            try:
                path.unlink(missing_ok=True)
            finally:
                raise
        return self._capture_result(envelope, status=STATUS_CAPTURED, path=path)

    def _capture_result(
        self,
        envelope: dict[str, Any],
        *,
        status: str,
        path: Path,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "receipt_schema_version": RECEIPT_SCHEMA_VERSION,
            "receipt_policy_version": RECEIPT_POLICY_VERSION,
            "receipt_id": envelope["receipt_id"],
            "payload_hash": envelope["payload_hash"],
            "retrieved_at": envelope["retrieved_at"],
            "cutoff": envelope["cutoff"],
            "historical_backfill_eligible": envelope["historical_backfill_eligible"],
            "append_only": True,
            "content_addressed": True,
            "predictive_feature_allowed": False,
            "artifact_path": path.relative_to(self.root).as_posix(),
        }

    def load(self, receipt_id: str) -> dict[str, Any]:
        path = self._path(receipt_id)
        if not path.exists():
            raise FileNotFoundError(path)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise TaiwanContextReceiptIntegrityError("receipt JSON unreadable") from exc
        if not isinstance(raw, dict):
            raise TaiwanContextReceiptIntegrityError("receipt envelope must be an object")
        context = raw.get("context")
        if not isinstance(context, dict):
            raise TaiwanContextReceiptIntegrityError("receipt context missing")
        expected = _envelope(context)
        if raw != expected:
            raise TaiwanContextReceiptIntegrityError(
                "receipt content/hash/identity mismatch"
            )
        if expected["receipt_id"] != receipt_id:
            raise TaiwanContextReceiptIntegrityError("receipt filename identity mismatch")
        return raw

    def receipt_ids(self) -> list[str]:
        if not self.snapshots_dir.exists():
            return []
        return [
            "tw-context:" + path.stem
            for path in sorted(self.snapshots_dir.glob("*.json"))
        ]

    def select_for_decision(
        self,
        stock_id: str,
        decision_time: datetime | str | pd.Timestamp,
    ) -> dict[str, Any]:
        decision = _utc(decision_time, field="decision_time")
        candidates: list[dict[str, Any]] = []
        for receipt_id in self.receipt_ids():
            envelope = self.load(receipt_id)
            if str(envelope.get("stock_id") or "") != str(stock_id):
                continue
            retrieved_at = _utc(envelope["retrieved_at"], field="retrieved_at")
            if retrieved_at <= decision:
                candidates.append(envelope)
        if not candidates:
            return {
                "status": STATUS_NOT_AVAILABLE_BEFORE_DECISION,
                "stock_id": str(stock_id),
                "decision_time": decision.isoformat(),
                "receipt_id": None,
                "predictive_feature_allowed": False,
            }
        selected = max(
            candidates,
            key=lambda item: (
                _utc(item["retrieved_at"], field="retrieved_at"),
                str(item["receipt_id"]),
            ),
        )
        return {
            "status": "AVAILABLE_RECEIPT",
            "stock_id": str(stock_id),
            "decision_time": decision.isoformat(),
            "receipt_id": selected["receipt_id"],
            "retrieved_at": selected["retrieved_at"],
            "cutoff": selected["cutoff"],
            "context": selected["context"],
            "append_only": True,
            "content_addressed": True,
            "receipt_time_revision_safe": True,
            "revision_safety_semantics": (
                "IMMUTABLE_RECEIPT_EXISTED_AT_OR_BEFORE_DECISION;"
                "DOES_NOT_RECLASSIFY_PRE_RECEIPT_VENDOR_HISTORY_AS_PIT"
            ),
            "predictive_feature_allowed": False,
        }
