"""FinCast adapter（spec §7 / P13 optional）。

FinCast 依賴（tensorflow/jax 舊版 pinned）與主 venv 衝突 → 隔離 .venv-fincast。
本 adapter 透過 subprocess bridge 呼叫（主 venv 零污染）。

狀態機：ready（隔離 venv + checkpoint 就緒）/ unavailable / not-installed。
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from market_ai_hub.config.settings import project_root
from market_ai_hub.schemas.market_data import DataGrade, ForecastOutput

log = logging.getLogger(__name__)

FACAST_VENV_PY = project_root() / ".venv-fincast" / "Scripts" / "python.exe"
WORKER = project_root() / "external" / "fincast_worker.py"


def _resolve_checkpoint() -> Path:
    """解析 FinCast checkpoint 路徑（可攜，不含任何個人絕對路徑）。

    優先序：環境變數 FINCAST_CHECKPOINT → 使用者 HF cache 內 Vincent05R/FinCast 的 snapshot。
    """
    env = os.environ.get("FINCAST_CHECKPOINT")
    if env:
        return Path(env)
    hf_cache = os.environ.get("HF_HUB_CACHE") or os.environ.get("HF_HOME") or str(Path.home() / ".cache" / "huggingface")
    snap_root = Path(hf_cache) / "hub" / "models--Vincent05R--FinCast" / "snapshots"
    if snap_root.exists():
        for snap in sorted(snap_root.iterdir(), reverse=True):
            p = snap / "v1.pth"
            if p.exists():
                return p
    return snap_root / "v1.pth"  # 不存在 → status()=unavailable


CHECKPOINT = _resolve_checkpoint()


class FinCastAdapter:
    """隔離環境 FinCast。僅 research/education 用途。"""

    name = "fincast"

    def status(self) -> str:
        if not FACAST_VENV_PY.exists():
            return "not-installed"
        if not CHECKPOINT.exists():
            return "unavailable"
        return "ready"

    def predict(self, series: pd.Series | np.ndarray | list, horizon: int = 7) -> dict:
        if self.status() != "ready":
            raise RuntimeError(f"fincast status={self.status()}")
        if isinstance(series, pd.Series):
            series = series.to_numpy(dtype=float)
        arr = [float(v) for v in np.asarray(series, dtype=float)]
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            f.write(json.dumps({"series": arr, "horizon": horizon}))
            in_path = Path(f.name)
        out_path = in_path.with_suffix(".out.json")
        try:
            proc = subprocess.run(
                [str(FACAST_VENV_PY), str(WORKER), "--input", str(in_path), "--output", str(out_path)],
                capture_output=True, text=True, timeout=900,
            )
            if proc.returncode != 0 or not out_path.exists():
                raise RuntimeError(f"fincast worker failed: {proc.stderr[:500]}")
            result = json.loads(out_path.read_text(encoding="utf-8"))
            if "error" in result:
                raise RuntimeError(result["error"])
            return {"point": result["forecast"]}
        finally:
            in_path.unlink(missing_ok=True)
            out_path.unlink(missing_ok=True)


def fincast_forecast(
    adapter: FinCastAdapter,
    symbol: str,
    closes: pd.Series,
    horizon: str = "1d",
    horizon_steps: int = 7,
    data_grade: str = "RESEARCH_PROXY",
) -> ForecastOutput:
    r = adapter.predict(closes, horizon=horizon_steps)
    point = float(np.mean(r["point"]))
    last = float(closes.iloc[-1])
    exp_ret = (point - last) / last
    direction = "up" if exp_ret > 0 else ("down" if exp_ret < 0 else "flat")
    return ForecastOutput(
        model="fincast",
        symbol=symbol,
        as_of=datetime.now(timezone.utc),
        horizon=horizon,
        point_forecast=point,
        expected_return=exp_ret,
        quantiles={"p10": point, "p50": point, "p90": point},
        direction=direction,
        confidence=0.5,
        data_grade=DataGrade(data_grade),
        warnings=["FinCast: research/education use only; no quantiles in subprocess bridge v1"],
    )
