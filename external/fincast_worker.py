"""FinCast 隔離 worker：在 .venv-fincast 內執行（主 venv 不裝 FinCast 依賴）。

用法：
  python fincast_worker.py --input <json_file> --output <json_file>
input JSON: {"series": [...], "horizon": int}
output JSON: {"forecast": [...], "quantiles": null} 或 {"error": "..."}
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_SRC = Path(__file__).parent / "fincast" / "src"
sys.path.insert(0, str(REPO_SRC))


def _resolve_checkpoint() -> str:
    env = os.environ.get("FINCAST_CHECKPOINT")
    if env:
        return env
    hf_cache = os.environ.get("HF_HUB_CACHE") or os.environ.get("HF_HOME") or str(Path.home() / ".cache" / "huggingface")
    snap_root = Path(hf_cache) / "hub" / "models--Vincent05R--FinCast" / "snapshots"
    if snap_root.exists():
        for snap in sorted(snap_root.iterdir(), reverse=True):
            p = snap / "v1.pth"
            if p.exists():
                return str(p)
    return str(snap_root / "v1.pth")


CHECKPOINT = _resolve_checkpoint()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    series = payload["series"]
    horizon = int(payload.get("horizon", 128))

    try:
        import numpy as np
        from ffm.ffm_base import FFmHparams
        from ffm.ffm_torch_moe import FFmTorch

        hp = FFmHparams(backend="cpu", load_from_compile=True, num_experts=4, horizon_len=horizon)
        model = FFmTorch(hparams=hp, checkpoint=CHECKPOINT)
        arr = np.asarray(series, dtype=float)
        fc, _q = model.forecast([arr], freq=[0])
        result = {"forecast": [float(v) for v in np.asarray(fc)[0, :horizon]]}
    except Exception as e:
        result = {"error": f"{type(e).__name__}: {e}"}

    Path(args.output).write_text(json.dumps(result), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
