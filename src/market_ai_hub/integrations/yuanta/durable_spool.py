"""Durable quote spool for the Yuanta quote recorder."""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


class DurableSpoolError(RuntimeError):
    pass


class DurableSpoolCorruption(DurableSpoolError):
    pass


class DurableSpoolFull(DurableSpoolError):
    pass

def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=str,
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ack_state_sha256(*, version: int, acked_seq: int, batch_id: str) -> str:
    return sha256_hex(canonical_bytes({
        "version": int(version),
        "acked_seq": int(acked_seq),
        "batch_id": str(batch_id),
    }))


def durable_replace(source: Path, destination: Path, *, attempts: int = 5) -> None:
    for attempt in range(max(1, attempts)):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if os.name != "nt" or attempt + 1 >= attempts:
                raise
            time.sleep(0.01 * (2 ** attempt))


def durable_json_replace(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp-" + uuid4().hex)
    data = canonical_bytes(payload)
    try:
        with tmp.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        durable_replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)

@dataclass(frozen=True)
class SpoolRecord:
    seq: int
    record_id: str
    payload_sha256: str
    payload: dict
    path: Path
    size_bytes: int


class DurableQuoteSpool:
    VERSION = 1

    def __init__(self, root: Path, *, max_bytes: int, max_records: int) -> None:
        if max_bytes < 1 or max_records < 1:
            raise ValueError("spool limits must be positive")
        self.root = root
        self.pending_dir = root / "pending"
        self.ack_path = root / "ack.json"
        self.max_bytes = int(max_bytes)
        self.max_records = int(max_records)
        self.lock = threading.Lock()
        self.pending_dir.mkdir(parents=True, exist_ok=True)
        self.acked_seq = self._load_ack()
        self._recover_partials()
        self.pending = self._load_pending()
        self.pending_bytes = sum(x.size_bytes for x in self.pending)
        if len(self.pending) > self.max_records or self.pending_bytes > self.max_bytes:
            raise DurableSpoolFull("existing spool exceeds configured quota")
        self.next_seq = max([self.acked_seq, *[x.seq for x in self.pending]]) + 1

    def _load_ack(self) -> int:
        if not self.ack_path.exists():
            return 0
        try:
            value = json.loads(self.ack_path.read_text(encoding="utf-8"))
            if value.get("version") != self.VERSION:
                raise ValueError("version")
            acked_seq = int(value["acked_seq"])
            batch_id = str(value["batch_id"])
            if acked_seq < 0 or not batch_id:
                raise ValueError("ack identity")
            expected = ack_state_sha256(
                version=self.VERSION, acked_seq=acked_seq, batch_id=batch_id,
            )
            if value.get("state_sha256") != expected:
                raise ValueError("ack checksum")
            return acked_seq
        except Exception as exc:
            raise DurableSpoolCorruption("invalid spool ack state") from exc

    def _decode_record(self, path: Path) -> SpoolRecord:
        try:
            raw = path.read_bytes()
            value = json.loads(raw.decode("utf-8"))
            if value.get("version") != self.VERSION:
                raise ValueError("version")
            seq = int(value["seq"])
            record_id = str(value["record_id"])
            payload = value["payload"]
            digest = str(value["payload_sha256"])
            if seq < 1 or not record_id or not isinstance(payload, dict):
                raise ValueError("identity")
            if sha256_hex(canonical_bytes(payload)) != digest:
                raise ValueError("checksum")
            return SpoolRecord(seq, record_id, digest, payload, path, len(raw))
        except Exception as exc:
            raise DurableSpoolCorruption(f"invalid spool record: {path.name}") from exc

    def _recover_partials(self) -> None:
        for partial in sorted(self.pending_dir.glob("*.json.partial")):
            record = self._decode_record(partial)
            final = partial.with_suffix("")
            if record.seq <= self.acked_seq:
                partial.unlink(missing_ok=True)
                continue
            if final.exists():
                existing = self._decode_record(final)
                same = (
                    existing.seq == record.seq
                    and existing.record_id == record.record_id
                    and existing.payload_sha256 == record.payload_sha256
                )
                if not same:
                    raise DurableSpoolCorruption("partial/final spool conflict")
                partial.unlink(missing_ok=True)
                continue
            durable_replace(partial, final)

    def _load_pending(self) -> list[SpoolRecord]:
        records = []
        for path in sorted(self.pending_dir.glob("*.json")):
            record = self._decode_record(path)
            if record.seq <= self.acked_seq:
                path.unlink(missing_ok=True)
                continue
            records.append(record)
        records.sort(key=lambda item: item.seq)
        expected = self.acked_seq + 1
        for record in records:
            if record.seq != expected:
                raise DurableSpoolCorruption("spool sequence gap or duplicate")
            expected += 1
        return records

    def append(self, payload: dict) -> SpoolRecord:
        with self.lock:
            if len(self.pending) >= self.max_records:
                raise DurableSpoolFull("spool record quota exceeded")
            seq = self.next_seq
            record_id = uuid4().hex
            digest = sha256_hex(canonical_bytes(payload))
            envelope = {
                "version": self.VERSION,
                "seq": seq,
                "record_id": record_id,
                "payload_sha256": digest,
                "payload": payload,
            }
            encoded = canonical_bytes(envelope)
            if self.pending_bytes + len(encoded) > self.max_bytes:
                raise DurableSpoolFull("spool byte quota exceeded")
            final = self.pending_dir / f"{seq:020d}-{record_id}.json"
            partial = final.with_suffix(".json.partial")
            try:
                with partial.open("xb") as handle:
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())
                durable_replace(partial, final)
            finally:
                partial.unlink(missing_ok=True)
            record = SpoolRecord(seq, record_id, digest, dict(payload), final, len(encoded))
            self.pending.append(record)
            self.pending_bytes += len(encoded)
            self.next_seq += 1
            return record

    def peek(self, limit: int) -> list[SpoolRecord]:
        with self.lock:
            return list(self.pending[:max(0, int(limit))])

    def batch_id(self, records: list[SpoolRecord]) -> str:
        if not records:
            raise ValueError("batch requires records")
        digest = hashlib.sha256()
        for record in records:
            digest.update(f"{record.seq}:".encode("ascii"))
            digest.update(record.payload_sha256.encode("ascii"))
        return (
            f"wal-{records[0].seq:020d}-{records[-1].seq:020d}-"
            f"{digest.hexdigest()[:16]}"
        )

    def ack_through(self, last_seq: int, *, batch_id: str) -> None:
        with self.lock:
            if last_seq <= self.acked_seq:
                return
            selected = [item for item in self.pending if item.seq <= last_seq]
            if not selected or selected[-1].seq != last_seq:
                raise DurableSpoolCorruption("ack must commit an existing oldest prefix")
            if selected[0].seq != self.acked_seq + 1:
                raise DurableSpoolCorruption("ack prefix is not contiguous")
            ack_payload = {
                "version": self.VERSION,
                "acked_seq": int(last_seq),
                "batch_id": str(batch_id),
                "acked_at": datetime.now(timezone.utc).isoformat(),
            }
            ack_payload["state_sha256"] = ack_state_sha256(
                version=self.VERSION, acked_seq=int(last_seq), batch_id=str(batch_id),
            )
            durable_json_replace(self.ack_path, ack_payload)
            self.acked_seq = int(last_seq)

            cleanup_error = None
            removed_bytes = 0
            for item in selected:
                try:
                    item.path.unlink(missing_ok=True)
                    removed_bytes += item.size_bytes
                except OSError as exc:
                    cleanup_error = exc
                    break
            self.pending = [item for item in self.pending if item.seq > last_seq]
            self.pending_bytes = max(0, self.pending_bytes - removed_bytes)
            if cleanup_error is not None:
                raise DurableSpoolError("spool ack cleanup failed") from cleanup_error

    def stats(self) -> dict:
        with self.lock:
            return {
                "pending_records": len(self.pending),
                "pending_bytes": self.pending_bytes,
                "acked_seq": self.acked_seq,
                "max_records": self.max_records,
                "max_bytes": self.max_bytes,
            }
