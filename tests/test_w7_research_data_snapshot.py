import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest
import pyarrow as pa
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[1]
CREATE = ROOT / "scripts" / "create_research_data_snapshot.py"
VERIFY = ROOT / "scripts" / "verify_research_data_snapshot.py"
RESTORE = ROOT / "scripts" / "restore_research_data_snapshot.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _fixture(data: Path) -> None:
    duck = data / "audit" / "prediction_audit.duckdb"
    duck.parent.mkdir(parents=True)
    with duckdb.connect(str(duck)) as con:
        con.execute("create table predictions(prediction_id varchar, value double)")
        con.execute("insert into predictions values ('p2',2.0),('p1',1.0)")
    sqlite = data / "registry" / "local.sqlite"
    sqlite.parent.mkdir(parents=True)
    con = sqlite3.connect(sqlite)
    try:
        con.execute("create table items(prediction_id text, value integer)")
        con.executemany("insert into items values (?,?)", [("s2", 2), ("s1", 1)])
        con.commit()
    finally:
        con.close()

    parquet = data / "normalized" / "sample.parquet"
    parquet.parent.mkdir(parents=True)
    pq.write_table(
        pa.table({"prediction_id": ["q2", "q1"], "value": [2, 1]}),
        parquet,
    )

    live = data / "live" / "yuanta" / "parquet" / "2026-09-25" / "live.parquet"
    live.parent.mkdir(parents=True)
    pq.write_table(pa.table({"prediction_id": ["live"], "value": [9]}), live)


def _create(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    destination = tmp_path / "snapshots"
    _fixture(data)
    result = _run(str(CREATE), "--data-root", str(data), "--destination", str(destination))
    assert result.returncode == 0, result.stdout + result.stderr
    line = next(line for line in result.stdout.splitlines() if line.startswith("snapshot="))
    return Path(line.split("=", 1)[1])


def test_research_snapshot_create_and_verify_excludes_live(tmp_path):
    snapshot = _create(tmp_path)
    manifest = json.loads((snapshot / "SNAPSHOT_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["counts"]["duckdb"] == 1
    assert manifest["counts"]["sqlite"] == 1
    assert manifest["counts"]["parquet"] == 1
    assert manifest["counts"]["excluded_live_files"] == 1
    assert all(not item["relative_path"].startswith("live/") for item in manifest["entries"])

    result = _run(str(VERIFY), "--snapshot", str(snapshot))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "RESEARCH_SNAPSHOT_VERIFY_PASS" in result.stdout

    duck = next(item for item in manifest["entries"] if item["kind"] == "duckdb")
    table = duck["tables"][0]
    assert table["row_count"] == 2
    assert table["prediction_id_digest"]


def test_research_snapshot_verifier_rejects_tamper_and_extra_file(tmp_path):
    snapshot = _create(tmp_path)
    target = next((snapshot / "data").rglob("*.parquet"))
    payload = bytearray(target.read_bytes())
    payload[-1] ^= 0x01
    target.write_bytes(payload)
    bad = _run(str(VERIFY), "--snapshot", str(snapshot))
    assert bad.returncode != 0
    assert "sha256 mismatch" in (bad.stdout + bad.stderr)


    snapshot = _create(tmp_path / "second")
    (snapshot / "extra.bin").write_bytes(b"x")
    extra = _run(str(VERIFY), "--snapshot", str(snapshot))
    assert extra.returncode != 0
    assert "unmanifested snapshot files" in (extra.stdout + extra.stderr)


def test_research_snapshot_restore_to_new_data_root(tmp_path):
    snapshot = _create(tmp_path)
    restored = tmp_path / "restored data"
    result = _run(str(RESTORE), "--snapshot", str(snapshot), "--destination", str(restored))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "RESEARCH_SNAPSHOT_RESTORE_PASS" in result.stdout
    assert not (restored / "live").exists()
    assert (restored / "audit" / "prediction_audit.duckdb").is_file()
    assert (restored / "registry" / "local.sqlite").is_file()
    assert (restored / "normalized" / "sample.parquet").is_file()

    second = _run(str(RESTORE), "--snapshot", str(snapshot), "--destination", str(restored))
    assert second.returncode != 0
    assert "must not already exist" in (second.stdout + second.stderr)

    overlap = _run(
        str(RESTORE), "--snapshot", str(snapshot),
        "--destination", str(snapshot / "restored"),
    )
    assert overlap.returncode != 0
    assert "must not overlap snapshot" in (overlap.stdout + overlap.stderr)


def test_research_snapshot_rejects_symlink_in_scope(tmp_path):
    data = tmp_path / "data"
    _fixture(data)
    outside = tmp_path / "outside.parquet"
    pq.write_table(pa.table({"prediction_id": ["outside"]}), outside)
    link = data / "normalized" / "linked.parquet"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    result = _run(
        str(CREATE), "--data-root", str(data),
        "--destination", str(tmp_path / "snapshots"),
    )
    assert result.returncode != 0
    assert "symlink is not allowed" in (result.stdout + result.stderr)


def test_research_snapshot_rejects_destination_inside_data_root(tmp_path):
    data = tmp_path / "data"
    _fixture(data)
    result = _run(
        str(CREATE),
        "--data-root",
        str(data),
        "--destination",
        str(data / "snapshots"),
    )
    assert result.returncode != 0
    assert "outside DATA_ROOT" in (result.stdout + result.stderr)
