from __future__ import annotations

import argparse
import shutil
import uuid
from pathlib import Path

from verify_research_data_snapshot import (
    safe_data_path,
    verify_data_tree,
    verify_snapshot,
)


def under(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def restore_snapshot(snapshot: Path, destination: Path) -> dict:
    snapshot = snapshot.resolve()
    destination = destination.resolve()
    manifest = verify_snapshot(snapshot)

    if destination.exists():
        raise RuntimeError("restore destination must not already exist")
    if under(destination, snapshot) or under(snapshot, destination):
        raise RuntimeError("restore destination must not overlap snapshot")
    destination.parent.mkdir(parents=True, exist_ok=True)

    partial = destination.parent / f".{destination.name}.restore-{uuid.uuid4().hex[:8]}"
    if partial.exists():
        raise RuntimeError(f"restore partial already exists: {partial}")
    partial.mkdir()
    created_final = False
    try:
        entries = manifest["entries"]
        for entry in entries:
            relative = entry["relative_path"]
            source = safe_data_path(snapshot / "data", relative)
            target = partial / Path(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

        verify_data_tree(partial, entries)
        partial.rename(destination)
        created_final = True
        verify_data_tree(destination, entries)
        return manifest
    except Exception:
        if partial.exists():
            shutil.rmtree(partial, ignore_errors=True)
        if created_final and destination.exists():
            shutil.rmtree(destination, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args()
    destination = Path(args.destination)
    manifest = restore_snapshot(Path(args.snapshot), destination)
    counts = manifest.get("counts", {})
    print("RESEARCH_SNAPSHOT_RESTORE_PASS")
    print(f"destination={destination.resolve()}")
    print(f"duckdb={counts.get('duckdb', 0)}")
    print(f"sqlite={counts.get('sqlite', 0)}")
    print(f"parquet={counts.get('parquet', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
