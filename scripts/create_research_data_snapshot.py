from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from market_ai_hub.config.runtime_paths import data_root as canonical_data_root

SCHEMA = "MARKET_AI_RESEARCH_SNAPSHOT_V1"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def value_digest(values) -> str:
    h = hashlib.sha256()
    for value in sorted(str(v) for v in values if v is not None):
        encoded = value.encode("utf-8")
        h.update(len(encoded).to_bytes(8, "big"))
        h.update(encoded)
    return h.hexdigest()


def qident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def sql_path(path: Path) -> str:
    return path.as_posix().replace("'", "''")


def duckdb_stats(path: Path) -> list[dict]:
    out: list[dict] = []
    with duckdb.connect(str(path), read_only=True) as con:
        tables = con.execute(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_type='BASE TABLE' AND table_schema NOT IN ('information_schema','pg_catalog') "
            "ORDER BY table_schema, table_name"
        ).fetchall()
        for schema, table in tables:
            target = f"{qident(schema)}.{qident(table)}"
            row_count = int(con.execute(f"SELECT COUNT(*) FROM {target}").fetchone()[0])
            columns = {
                row[0]
                for row in con.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema=? AND table_name=?",
                    [schema, table],
                ).fetchall()
            }
            pred_digest = None
            if "prediction_id" in columns:
                values = con.execute(
                    f"SELECT CAST(prediction_id AS VARCHAR) FROM {target} "
                    "WHERE prediction_id IS NOT NULL ORDER BY 1"
                ).fetchall()
                pred_digest = value_digest(row[0] for row in values)
            out.append({
                "schema": schema,
                "table": table,
                "row_count": row_count,
                "prediction_id_digest": pred_digest,
            })
    return out


def sqlite_stats(path: Path) -> list[dict]:
    out: list[dict] = []
    uri = f"file:{path.as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        tables = [
            row[0]
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        for table in tables:
            target = qident(table)
            row_count = int(con.execute(f"SELECT COUNT(*) FROM {target}").fetchone()[0])
            columns = {row[1] for row in con.execute(f"PRAGMA table_info({target})")}
            pred_digest = None
            if "prediction_id" in columns:
                values = con.execute(
                    f"SELECT CAST(prediction_id AS TEXT) FROM {target} "
                    "WHERE prediction_id IS NOT NULL ORDER BY 1"
                ).fetchall()
                pred_digest = value_digest(row[0] for row in values)
            out.append({"table": table, "row_count": row_count, "prediction_id_digest": pred_digest})
    finally:
        con.close()
    return out


def parquet_stats(path: Path) -> dict:
    pf = pq.ParquetFile(path)
    names = pf.schema_arrow.names
    pred_digest = None
    if "prediction_id" in names:
        column = pq.read_table(path, columns=["prediction_id"])["prediction_id"]
        pred_digest = value_digest(column.to_pylist())
    return {
        "row_count": int(pf.metadata.num_rows),
        "prediction_id_digest": pred_digest,
    }


def snapshot_duckdb(src: Path, dst: Path) -> dict:
    before = duckdb_stats(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    con = duckdb.connect()
    try:
        con.execute(f"ATTACH '{sql_path(src)}' AS src (READ_ONLY)")
        con.execute(f"ATTACH '{sql_path(dst)}' AS dst")
        con.execute("COPY FROM DATABASE src TO dst")
    finally:
        con.close()
    copied = duckdb_stats(dst)
    after = duckdb_stats(src)
    if before != copied or after != copied:
        raise RuntimeError(f"DuckDB changed during snapshot: {src}")
    return {"tables": copied}


def snapshot_sqlite(src: Path, dst: Path) -> dict:
    before = sqlite_stats(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    source = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True)
    target = sqlite3.connect(dst)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    copied = sqlite_stats(dst)
    after = sqlite_stats(src)
    if before != copied or after != copied:
        raise RuntimeError(f"SQLite changed during snapshot: {src}")
    return {"tables": copied}


def stable_copy(src: Path, dst: Path) -> tuple[str, dict]:
    before = sha256_file(src)
    stats = parquet_stats(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    after = sha256_file(src)
    copied = sha256_file(dst)
    if before != after or before != copied:
        raise RuntimeError(f"source changed during parquet snapshot: {src}")
    return copied, stats


def under(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def discover(data_root: Path) -> tuple[list[Path], list[Path], list[Path], dict]:
    live = data_root / "live"
    backups = data_root / "backups"
    dbs: list[Path] = []
    sqlite_files: list[Path] = []
    parquets: list[Path] = []
    excluded_live = 0
    out_of_scope = 0
    for path in data_root.rglob("*"):
        if path.is_symlink():
            raise RuntimeError(f"symlink is not allowed in research snapshot scope: {path}")
        if not path.is_file():
            continue
        if under(path, live):
            excluded_live += 1
            continue
        if under(path, backups):
            continue
        suffix = path.suffix.lower()
        if suffix == ".duckdb":
            dbs.append(path)
        elif suffix in {".sqlite", ".sqlite3"}:
            sqlite_files.append(path)
        elif suffix == ".parquet":
            parquets.append(path)
        else:
            out_of_scope += 1
    return sorted(dbs), sorted(sqlite_files), sorted(parquets), {
        "excluded_live_files": excluded_live,
        "out_of_scope_files": out_of_scope,
    }


def create_snapshot(data_root: Path, destination: Path) -> Path:
    data_root = data_root.resolve()
    destination = destination.resolve()
    if under(destination, data_root):
        raise RuntimeError("snapshot destination must be outside DATA_ROOT")
    destination.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = f"research_snapshot_{stamp}_{uuid.uuid4().hex[:8]}"
    partial = destination / f".{name}.partial"
    final = destination / name
    partial.mkdir(parents=False)

    entries: list[dict] = []
    dbs, sqlite_files, parquets, counts = discover(data_root)
    parquet_set_before = [p.relative_to(data_root).as_posix() for p in parquets]

    try:
        for src in dbs:
            rel = src.relative_to(data_root)
            dst = partial / "data" / rel
            meta = snapshot_duckdb(src, dst)
            entries.append({
                "kind": "duckdb", "relative_path": rel.as_posix(),
                "sha256": sha256_file(dst), "size": dst.stat().st_size, **meta,
            })
        for src in sqlite_files:
            rel = src.relative_to(data_root)
            dst = partial / "data" / rel
            meta = snapshot_sqlite(src, dst)
            entries.append({
                "kind": "sqlite", "relative_path": rel.as_posix(),
                "sha256": sha256_file(dst), "size": dst.stat().st_size, **meta,
            })

        for src in parquets:
            rel = src.relative_to(data_root)
            dst = partial / "data" / rel
            digest, meta = stable_copy(src, dst)
            entries.append({
                "kind": "parquet", "relative_path": rel.as_posix(),
                "sha256": digest, "size": dst.stat().st_size, **meta,
            })

        _, _, parquets_after, _ = discover(data_root)
        parquet_set_after = [p.relative_to(data_root).as_posix() for p in parquets_after]
        if parquet_set_after != parquet_set_before:
            raise RuntimeError("parquet inventory changed during snapshot")

        manifest = {
            "schema": SCHEMA,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_data_root": str(data_root),
            "exclusions": ["live/**", "backups/**"],
            "scope": "duckdb+sqlite+parquet",
            "counts": {**counts, "duckdb": len(dbs), "sqlite": len(sqlite_files), "parquet": len(parquets)},
            "entries": entries,
        }
        manifest_path = partial / "SNAPSHOT_MANIFEST.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        partial.rename(final)
        return final
    except Exception:
        shutil.rmtree(partial, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root")
    parser.add_argument("--destination", required=True)
    args = parser.parse_args()

    root = Path(args.data_root).resolve() if args.data_root else canonical_data_root().resolve()
    snapshot = create_snapshot(root, Path(args.destination))
    print("RESEARCH_SNAPSHOT_CREATED")
    print(f"snapshot={snapshot}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
