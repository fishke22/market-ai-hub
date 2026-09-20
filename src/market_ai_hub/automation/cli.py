"""Phase 2E — automation CLI（status / tick / catchup / run-job）。

python -m market_ai_hub.automation status
python -m market_ai_hub.automation tick
python -m market_ai_hub.automation catchup
python -m market_ai_hub.automation run-job JOB
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from market_ai_hub.automation.scheduler import JOBS, SchedulerState  # noqa: E402


def cmd_status(args) -> int:
    sched = SchedulerState()
    st = sched.status()
    print("=== MARKET_AI_HUB 研究循環狀態 ===")
    for job in JOBS:
        s = st.get(job, {})
        last = s.get("last_success")
        print(f"  {job:<22} last_success={last if last else '（尚未執行）'}  "
              f"status={s.get('status', '-')}")
    print()
    print("  資料最後更新：", st.get("sync_market_data", {}).get("last_success") or "（尚未執行）")
    print("  尚未結算預測：", st.get("settle_predictions", {}).get("status") or "-")
    print("  尚未結算分析：", st.get("settle_analysis", {}).get("status") or "-")
    print("  最近一次模型重訓：", st.get("training_due_check", {}).get("last_success") or "（尚未執行）")
    print("  Drift：", "NORMAL" if st.get("river_shadow", {}).get("status") != "error" else "ERROR")
    print("  Background scheduler：ACTIVE" if st else "  Background scheduler：NOT_REGISTERED")
    return 0


def cmd_tick(args) -> int:
    from market_ai_hub.automation.loop import run_tick

    r = run_tick()
    print("tick done:", r["results"])
    return 0


def cmd_catchup(args) -> int:
    from market_ai_hub.automation.loop import run_catchup

    r = run_catchup()
    print("catchup last_success:", r["last_success"])
    return 0


def cmd_run_job(args) -> int:
    from market_ai_hub.automation.loop import LoopContext, run_tick

    job = args.job
    if job not in JOBS:
        print(f"unknown job '{job}'. available: {JOBS}")
        return 1
    # 簡化：跑完整 tick（輕量，無工作快速結束）
    r = run_tick()
    print(f"job {job} (via tick):", r["results"].get(job))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="market_ai_hub.automation")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("tick").set_defaults(fn=cmd_tick)
    sub.add_parser("catchup").set_defaults(fn=cmd_catchup)
    p = sub.add_parser("run-job"); p.add_argument("job"); p.set_defaults(fn=cmd_run_job)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
