"""Provision the pinned P7 NautilusTrader environment outside the core venv."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from market_ai_hub.research.accuracy_v2_p7 import load_p7_protocol
from market_ai_hub.research.accuracy_v2_p7_engine import canonical_nautilus_python


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    p = load_p7_protocol()
    exe = canonical_nautilus_python(p)
    env_root = exe.parent.parent
    plan = {
        "status": "DRY_RUN" if not args.apply else "APPLYING",
        "engine": "nautilus_trader",
        "version": p.raw["engine"]["release"],
        "environment": str(env_root),
        "python": str(exe),
        "core_python": sys.executable,
        "core_venv_mutated": False,
        "live_execution_allowed": False,
    }
    if not args.apply:
        print(json.dumps(plan, sort_keys=True))
        return 0
    env_root.parent.mkdir(parents=True, exist_ok=True)
    if not exe.exists():
        subprocess.run([sys.executable, "-m", "venv", str(env_root)], check=True)
    subprocess.run(
        [str(exe), "-m", "pip", "install", "--disable-pip-version-check",
         f"nautilus_trader=={p.raw['engine']['release']}"],
        check=True,
    )
    check = subprocess.run(
        [str(exe), "-c", "import nautilus_trader; print(nautilus_trader.__version__)"],
        capture_output=True,
        text=True,
        check=True,
    )
    plan["status"] = "VERIFIED" if check.stdout.strip() == p.raw["engine"]["release"] else "VERSION_MISMATCH"
    plan["actual_version"] = check.stdout.strip()
    print(json.dumps(plan, sort_keys=True))
    return 0 if plan["status"] == "VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
