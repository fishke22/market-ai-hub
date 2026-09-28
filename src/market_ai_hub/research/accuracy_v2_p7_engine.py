"""Accuracy v2 P7 independent-engine, cost, paper and migration acceptance."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from market_ai_hub.config.runtime_paths import data_root
from market_ai_hub.config.settings import project_root
from market_ai_hub.research.accuracy_v2_p7 import P7Protocol, load_p7_protocol
from market_ai_hub.strategy.cost import CostModel


P7_ENGINE_SCHEMA_VERSION = "AV2P7E.1"
P7_PREREG_COMMIT = "3bd723e820b67212673c2ea5d7d83254fd7a11ae"


def canonical_nautilus_python(protocol: P7Protocol | None = None) -> Path:
    p = protocol or load_p7_protocol()
    rel = Path(str(p.raw["engine"]["canonical_relative_python"]))
    return data_root() / rel


def _runner_path() -> Path:
    return project_root() / "scripts" / "nautilus_p7_runner.py"


def verify_isolated_engine(protocol: P7Protocol | None = None) -> dict[str, Any]:
    p = protocol or load_p7_protocol()
    exe = canonical_nautilus_python(p)
    if not exe.exists():
        return {
            "status": "NOT_INSTALLED",
            "python": str(exe),
            "expected_version": p.raw["engine"]["release"],
            "core_venv_untouched": True,
            "live_execution_allowed": False,
        }
    proc = subprocess.run(
        [str(exe), "-c", "import nautilus_trader,sys; print(nautilus_trader.__version__); print(sys.executable)"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    lines = [x.strip() for x in proc.stdout.splitlines() if x.strip()]
    version = lines[0] if lines else ""
    actual_exe = lines[1] if len(lines) > 1 else ""
    expected = str(p.raw["engine"]["release"])
    ok = proc.returncode == 0 and version == expected and Path(actual_exe).resolve() == exe.resolve()
    return {
        "status": "VERIFIED" if ok else "VERSION_MISMATCH",
        "python": str(exe),
        "actual_python": actual_exe or None,
        "expected_version": expected,
        "actual_version": version or None,
        "exit_code": int(proc.returncode),
        "core_venv_untouched": True,
        "live_execution_allowed": False,
    }


def _run_isolated_once(
    *,
    protocol: P7Protocol,
    input_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    exe = canonical_nautilus_python(protocol)
    runner = _runner_path()
    proc = subprocess.run(
        [str(exe), str(runner), "--input", str(input_path), "--output", str(output_path)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env={
            **os.environ,
            "PYTHONNOUSERSITE": "1",
        },
    )
    if proc.returncode != 0:
        return {
            "status": "RUNNER_FAILED",
            "exit_code": int(proc.returncode),
            "stderr_tail": proc.stderr[-4000:],
        }
    try:
        result = json.loads(output_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"status": "INVALID_RESULT", "reason": type(exc).__name__}
    result["status"] = "OK"
    return result


def run_parity_acceptance(
    *,
    protocol: P7Protocol | None = None,
    workspace: str | Path | None = None,
) -> dict[str, Any]:
    p = protocol or load_p7_protocol()
    verify = verify_isolated_engine(p)
    if verify["status"] != "VERIFIED":
        return {
            "status": "ENGINE_NOT_READY",
            "engine": verify,
            "PARITY_PASS": False,
        }
    cfg = p.raw["parity"]
    root = Path(workspace) if workspace is not None else data_root() / "lab" / "accuracy_v2_p7"
    root.mkdir(parents=True, exist_ok=True)
    spec = {
        "schema_version": "AV2P7.NAUTILUS.INPUT.1",
        "engine_version": p.raw["engine"]["release"],
        "bar_count": int(cfg["bar_count"]),
        "seed": int(cfg["seed"]),
        "starting_price": float(cfg["starting_price"]),
        "network_market_data_allowed": False,
        "live_adapter_allowed": False,
        "external_order_action_allowed": False,
    }
    input_path = root / "parity_input.json"
    input_path.write_text(json.dumps(spec, sort_keys=True, indent=2), encoding="utf-8")
    results = []
    for i in range(int(cfg["deterministic_repeats"])):
        out = root / f"parity_result_{i + 1}.json"
        results.append(_run_isolated_once(protocol=p, input_path=input_path, output_path=out))
    required = cfg["required"]
    first = results[0] if results else {}
    digests = [r.get("result_digest") for r in results]
    checks = {
        "exact_engine_version": all(r.get("engine_version") == p.raw["engine"]["release"] for r in results),
        "monotonic_event_time": all(
            (
                all(int(fill["ts_init"]) <= int(fill["ts_last"]) for fill in r.get("fills", []))
                and [int(fill["ts_init"]) for fill in r.get("fills", [])]
                == sorted(int(fill["ts_init"]) for fill in r.get("fills", []))
            )
            for r in results
        ),
        "processed_bar_count_equals_input": all(
            int(r.get("bars_seen", -1)) == int(cfg["bar_count"]) for r in results
        ),
        "minimum_fill_count": all(
            int(r.get("fill_count", 0)) >= int(required["minimum_fill_count"]) for r in results
        ),
        "ending_position_flat": all(int(r.get("positions_open", -1)) == 0 for r in results),
        "repeated_result_digest_equal": (
            len(digests) == int(cfg["deterministic_repeats"])
            and all(bool(x) for x in digests)
            and len(set(digests)) == 1
        ),
        "finite_account_values": all(
            _finite_money((r.get("account") or {}).get("total")) for r in results
        ),
        "no_network_market_data": all(r.get("no_network_market_data") is True for r in results),
        "no_live_adapter": all(r.get("no_live_adapter") is True for r in results),
        "no_external_order_action": all(r.get("no_external_order_action") is True for r in results),
    }
    passed = all(bool(v) for v in checks.values()) and all(r.get("status") == "OK" for r in results)
    return {
        "status": "PARITY_PASS" if passed else "PARITY_FAIL",
        "protocol_hash": p.hash,
        "prereg_commit": P7_PREREG_COMMIT,
        "engine": verify,
        "input": spec,
        "checks": checks,
        "result_digest": first.get("result_digest"),
        "fill_count": first.get("fill_count"),
        "positions_open": first.get("positions_open"),
        "positions_closed": first.get("positions_closed"),
        "account": first.get("account"),
        "PARITY_PASS": passed,
        "predictive_performance_claim": False,
        "trading_edge_claim": False,
    }


def _finite_money(value: Any) -> bool:
    try:
        return math.isfinite(float(str(value)))
    except Exception:
        return False


def cost_diagnostic(protocol: P7Protocol | None = None) -> dict[str, Any]:
    p = protocol or load_p7_protocol()
    rows = {}
    for name in p.raw["cost_diagnostic"]["presets"]:
        model = CostModel.preset(str(name))
        per_side = model.fee + model.spread_proxy + model.slippage
        round_trip = model.per_trade()
        rows[str(name)] = {
            "fee_fraction": float(model.fee),
            "spread_proxy_fraction": float(model.spread_proxy),
            "slippage_fraction": float(model.slippage),
            "per_side_cost_fraction": float(per_side),
            "round_trip_cost_fraction": float(round_trip),
            "round_trip_cost_bps": float(round_trip * 10_000.0),
        }
    monotonic = (
        rows["ZERO_COST"]["round_trip_cost_fraction"]
        <= rows["BASE_COST"]["round_trip_cost_fraction"]
        <= rows["STRESS_COST"]["round_trip_cost_fraction"]
    )
    return {
        "status": "COST_DIAGNOSTIC_PASS" if monotonic else "COST_DIAGNOSTIC_FAIL",
        "presets": rows,
        "monotonic_cost_severity": monotonic,
        "actual_execution_cost_claim": False,
        "trading_edge_claim": False,
    }


def migration_acceptance(protocol: P7Protocol | None = None) -> dict[str, Any]:
    p = protocol or load_p7_protocol()
    root = project_root().resolve()
    data = data_root().resolve()
    core_python = (root / ".venv" / "Scripts" / "python.exe").resolve()
    paths = {
        "project_root": root,
        "data_root": data,
        "core_python": core_python,
        "p5_forward_runner": root / "scripts" / "run_accuracy_v2_p5_forward_cycle.py",
        "p5_task_plan": root / "scripts" / "register_accuracy_v2_p5_task.ps1",
        "open_source_manifest": root / "config" / "open_source_research_adapters.yaml",
        "p7_protocol": root / "config" / "accuracy_v2_p7_protocol.yaml",
    }
    path_checks = {k: v.exists() for k, v in paths.items()}
    engine_python = canonical_nautilus_python(p).resolve()
    engine_outside_core = core_python.parent.parent.resolve() not in engine_python.parents

    if root in data.parents or data == root:
        try:
            rel = data.relative_to(root)
            probe = root / rel / "lab"
            check = subprocess.run(
                ["git", "check-ignore", "-q", str(probe)],
                cwd=str(root),
                capture_output=True,
                timeout=10,
                check=False,
            )
            data_not_versioned = check.returncode == 0
        except Exception:
            data_not_versioned = False
    else:
        data_not_versioned = True

    recipe = {
        "core_env": "recreate .venv from tracked project dependencies; do not copy the existing venv",
        "data_root": "set MARKET_AI_DATA_ROOT or preserve canonical data_root; local data is not committed",
        "p7_engine": "run scripts/provision_accuracy_v2_p7_engine.py --apply to recreate the isolated pinned engine",
        "credentials": "recreate authorized SDK/WinCred configuration separately; never copy secrets into Git",
        "recorder": "runtime handover/restart requires separate explicit authorization",
        "tasks": "register task plans only after validating local paths/timezone; P7 does not auto-register them",
    }
    passed = (
        all(path_checks.values())
        and data_not_versioned
        and engine_outside_core
        and engine_python.exists()
    )
    return {
        "status": "MIGRATION_ACCEPTANCE_PASS" if passed else "MIGRATION_ACCEPTANCE_FAIL",
        "paths": {k: {"path": str(v), "exists": path_checks[k]} for k, v in paths.items()},
        "data_root_not_versioned": data_not_versioned,
        "isolated_engine_python": str(engine_python),
        "isolated_engine_outside_core_venv": engine_outside_core,
        "runtime_rebuild_recipe": recipe,
        "copy_secrets_allowed": False,
        "runtime_handover_performed": False,
        "recorder_restart_performed": False,
    }


def run_p7_acceptance(protocol: P7Protocol | None = None) -> dict[str, Any]:
    p = protocol or load_p7_protocol()
    parity = run_parity_acceptance(protocol=p)
    cost = cost_diagnostic(protocol=p)
    migration = migration_acceptance(protocol=p)
    paper_pass = bool(
        parity.get("PARITY_PASS")
        and parity.get("engine", {}).get("status") == "VERIFIED"
        and parity.get("checks", {}).get("no_live_adapter")
        and parity.get("checks", {}).get("no_external_order_action")
    )
    complete = (
        parity.get("PARITY_PASS") is True
        and cost.get("status") == "COST_DIAGNOSTIC_PASS"
        and migration.get("status") == "MIGRATION_ACCEPTANCE_PASS"
        and paper_pass
    )
    return {
        "schema_version": P7_ENGINE_SCHEMA_VERSION,
        "protocol_id": p.protocol_id,
        "protocol_hash": p.hash,
        "prereg_commit": P7_PREREG_COMMIT,
        "parity": parity,
        "cost_diagnostic": cost,
        "paper_acceptance": {
            "status": "PAPER_ACCEPTANCE_PASS" if paper_pass else "PAPER_ACCEPTANCE_FAIL",
            "simulated_venue_only": True,
            "broker_credentials_used": False,
            "live_execution": False,
        },
        "migration_acceptance": migration,
        "engineering_status": "P7_ENGINEERING_PASS" if complete else "P7_ENGINEERING_INCOMPLETE",
        "PREDICTIVE_GAIN": False,
        "CALIBRATED": False,
        "TRADING_EDGE": False,
        "P6_CONDITIONAL_COMPLETE": False,
    }
