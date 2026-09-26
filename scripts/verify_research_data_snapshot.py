from __future__ import annotations

import argparse
import json
from pathlib import Path

from create_research_data_snapshot import (
    SCHEMA,
    duckdb_stats,
    parquet_stats,
    sha256_file,
    sqlite_stats,
)


def safe_data_path(data_root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise RuntimeError(f"invalid relative path: {relative!r}")
    raw = data_root / Path(relative)
    cursor = data_root
    for part in Path(relative).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise RuntimeError(f"symlink is not allowed in research snapshot: {relative}")
    base = data_root.resolve()
    target = raw.resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise RuntimeError(f"snapshot path escapes data root: {relative}") from exc
    return target


def verify_entry_at_root(data_root: Path, entry: dict) -> None:
    relative = entry.get("relative_path")
    target = safe_data_path(data_root, relative)
    if not target.is_file():
        raise RuntimeError(f"snapshot file missing: {relative}")
    if target.stat().st_size != int(entry.get("size", -1)):
        raise RuntimeError(f"size mismatch: {relative}")
    if sha256_file(target) != entry.get("sha256"):
        raise RuntimeError(f"sha256 mismatch: {relative}")

    kind = entry.get("kind")
    if kind == "duckdb":
        actual = duckdb_stats(target)
        if actual != entry.get("tables"):
            raise RuntimeError(f"DuckDB table statistics mismatch: {relative}")
    elif kind == "sqlite":
        actual = sqlite_stats(target)
        if actual != entry.get("tables"):
            raise RuntimeError(f"SQLite table statistics mismatch: {relative}")
    elif kind == "parquet":
        actual = parquet_stats(target)
        expected = {
            "row_count": entry.get("row_count"),
            "prediction_id_digest": entry.get("prediction_id_digest"),
        }
        if actual != expected:
            raise RuntimeError(f"Parquet statistics mismatch: {relative}")
    else:
        raise RuntimeError(f"unknown snapshot entry kind: {kind!r}")


def verify_data_tree(data_root: Path, entries: list[dict]) -> None:
    data_root = data_root.resolve()
    if not data_root.is_dir():
        raise RuntimeError(f"data tree not found: {data_root}")

    seen: set[str] = set()
    for entry in entries:
        relative = entry.get("relative_path")
        if relative in seen:
            raise RuntimeError(f"duplicate snapshot entry: {relative}")
        seen.add(relative)
        verify_entry_at_root(data_root, entry)

    actual: set[str] = set()
    for path in data_root.rglob("*"):
        if path.is_symlink():
            raise RuntimeError(f"symlink is not allowed in restored data: {path}")
        if path.is_file():
            actual.add(path.relative_to(data_root).as_posix())
    extra = sorted(actual - seen)
    missing = sorted(seen - actual)
    if extra:
        raise RuntimeError(f"unmanifested data files: {extra}")
    if missing:
        raise RuntimeError(f"manifested data files missing: {missing}")


def verify_snapshot(snapshot: Path) -> dict:
    snapshot = snapshot.resolve()
    manifest_path = snapshot / "SNAPSHOT_MANIFEST.json"
    if not manifest_path.is_file():
        raise RuntimeError("SNAPSHOT_MANIFEST.json not found")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA:
        raise RuntimeError(f"unsupported snapshot schema: {manifest.get('schema')!r}")
    if manifest.get("scope") != "duckdb+sqlite+parquet":
        raise RuntimeError("unexpected snapshot scope")
    exclusions = manifest.get("exclusions", [])
    if "live/**" not in exclusions or "backups/**" not in exclusions:
        raise RuntimeError("required snapshot exclusions are not declared")

    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise RuntimeError("manifest entries must be a list")
    verify_data_tree(snapshot / "data", entries)

    actual_snapshot_files = {
        path.relative_to(snapshot).as_posix()
        for path in snapshot.rglob("*")
        if path.is_file()
    }
    expected_snapshot_files = {"SNAPSHOT_MANIFEST.json"}
    expected_snapshot_files.update(f"data/{entry['relative_path']}" for entry in entries)
    extra = sorted(actual_snapshot_files - expected_snapshot_files)
    missing = sorted(expected_snapshot_files - actual_snapshot_files)
    if extra:
        raise RuntimeError(f"unmanifested snapshot files: {extra}")
    if missing:
        raise RuntimeError(f"manifested snapshot files missing: {missing}")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True)
    args = parser.parse_args()
    manifest = verify_snapshot(Path(args.snapshot))
    counts = manifest.get("counts", {})
    print("RESEARCH_SNAPSHOT_VERIFY_PASS")
    print(f"duckdb={counts.get('duckdb', 0)}")
    print(f"sqlite={counts.get('sqlite', 0)}")
    print(f"parquet={counts.get('parquet', 0)}")
    print(f"excluded_live_files={counts.get('excluded_live_files', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
