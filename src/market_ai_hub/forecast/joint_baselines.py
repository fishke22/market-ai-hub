"""Phase 2G — Joint baselines（D）：VAR / Dynamic Factor / State-Space(Kalman)。

先建立可解釋模型。不硬把 univariate model 包成 joint model。
未來可建 Joint Challenger Adapter 給真正支援 multivariate/covariates 的 TSFM。
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import numpy as np
import pandas as pd

from market_ai_hub.forecast.contract import JointForecastResult


def _log_returns(panel: pd.DataFrame) -> pd.DataFrame:
    return np.log(panel).diff().dropna()


def _quantiles(samples: list[float]) -> dict:
    a = np.asarray(samples, dtype=float)
    return {
        "p10": float(np.quantile(a, 0.10)), "p25": float(np.quantile(a, 0.25)),
        "p50": float(np.quantile(a, 0.50)), "p75": float(np.quantile(a, 0.75)),
        "p90": float(np.quantile(a, 0.90)),
    }


def _simulate(mean: np.ndarray, cov: np.ndarray, last_levels: np.ndarray,
              target_idx: int, horizon: int, n_paths: int, seed: int) -> tuple[list[dict], list[float]]:
    rng = np.random.default_rng(seed)
    n_assets = len(mean)
    paths: list[dict] = []
    terminals: list[float] = []
    for _ in range(n_paths):
        rets = rng.multivariate_normal(mean, cov, size=horizon)
        cum = rets.sum(axis=0)
        terminal_levels = last_levels * np.exp(cum)
        paths.append({
            "cross_asset_terminal_returns": {f"a{i}": float(cum[i]) for i in range(n_assets)},
            "nikkei_terminal": float(terminal_levels[target_idx]),
        })
        terminals.append(float(terminal_levels[target_idx]))
    return paths, terminals


def _build(panel: pd.DataFrame, target: str, horizon: int, n_paths: int, seed: int,
           model_name: str, paths: list[dict], terminals: list[float],
           cutoff: datetime | None = None) -> JointForecastResult:
    q = _quantiles(terminals)
    symbols = list(panel.columns)
    return JointForecastResult(
        joint_forecast_id=str(uuid4()),
        information_cutoff=cutoff or panel.index[-1].to_pydatetime(),
        target=target, horizon=f"{horizon}d",
        input_panel_version="panel_v1", feature_version="v1", regime_version="v1",
        model_name=model_name, model_revision="baseline-1",
        future_paths=paths,
        factor_distributions={},
        target_distribution=[float(t) for t in terminals],
        p10=q["p10"], p25=q["p25"], p50=q["p50"], p75=q["p75"], p90=q["p90"],
        sampling_method="monte_carlo", sample_count=n_paths, seed=seed,
        calibration_status="UNVALIDATED", data_quality="RESEARCH_PROXY",
        model_status="OK",
    )


def var_baseline(panel: pd.DataFrame, target: str = "^N225", horizon: int = 5,
                 n_paths: int = 200, seed: int = 0, cutoff: datetime | None = None) -> JointForecastResult:
    """VAR(1)：多變量最小平方法估係數 + residual cov → Monte Carlo。"""
    r = _log_returns(panel)
    X = r.shift(1).dropna().values      # lag-1
    Y = r.iloc[1:].values               # current
    B = np.linalg.lstsq(X, Y, rcond=None)[0].T   # (n_assets x n_assets)
    resid = Y - X @ B.T
    cov = np.cov(resid, rowvar=False, ddof=1)
    last_rets = r.iloc[-1].values
    mean = B @ last_rets
    last_levels = panel.iloc[-1].values
    ti = list(panel.columns).index(target)
    paths, terminals = _simulate(mean, cov, last_levels, ti, horizon, n_paths, seed)
    return _build(panel, target, horizon, n_paths, seed, "var", paths, terminals, cutoff)


def factor_baseline(panel: pd.DataFrame, target: str = "^N225", horizon: int = 5,
                    n_paths: int = 200, seed: int = 0, cutoff: datetime | None = None) -> JointForecastResult:
    """Dynamic Factor：PCA 第一主成分當 common factor，AR(1) factor + idio noise。"""
    r = _log_returns(panel)
    X = r.values
    Xc = X - X.mean(axis=0)
    u, s, vt = np.linalg.svd(Xc, full_matrices=False)
    factor = u[:, 0] * s[0]             # common factor scores（未正規化亦可）
    loading = vt[0]                      # factor loadings
    # AR(1) on factor
    f_t = factor[1:]
    f_tm1 = factor[:-1]
    phi = float(np.dot(f_t, f_tm1) / (np.dot(f_tm1, f_tm1) + 1e-12))
    resid_f = f_t - phi * f_tm1
    sigma_f = float(np.std(resid_f, ddof=1)) if len(resid_f) > 1 else 0.01
    # idio
    recon = np.outer(factor, loading)
    idio = Xc - recon
    idio_std = idio.std(axis=0)
    # simulate factor path
    rng = np.random.default_rng(seed)
    last_levels = panel.iloc[-1].values
    ti = list(panel.columns).index(target)
    last_f = factor[-1]
    paths, terminals = [], []
    for _ in range(n_paths):
        f = last_f
        cum = np.zeros(len(loading))
        for _h in range(horizon):
            f = phi * f + rng.normal(0, sigma_f)
            cum += loading * f + rng.normal(0, idio_std)
        term = last_levels * np.exp(cum)
        paths.append({"cross_asset_terminal_returns": {f"a{i}": float(cum[i]) for i in range(len(cum))},
                      "nikkei_terminal": float(term[ti])})
        terminals.append(float(term[ti]))
    return _build(panel, target, horizon, n_paths, seed, "factor", paths, terminals, cutoff)


def kalman_baseline(panel: pd.DataFrame, target: str = "^N225", horizon: int = 5,
                    n_paths: int = 200, seed: int = 0, cutoff: datetime | None = None) -> JointForecastResult:
    """State-Space local-level：各資產 random walk，per-asset 波動（diagonal cov）。"""
    r = _log_returns(panel)
    std = r.std(ddof=1).values
    cov = np.diag(std ** 2)
    mean = np.zeros(len(std))
    last_levels = panel.iloc[-1].values
    ti = list(panel.columns).index(target)
    paths, terminals = _simulate(mean, cov, last_levels, ti, horizon, n_paths, seed)
    return _build(panel, target, horizon, n_paths, seed, "kalman", paths, terminals, cutoff)


JOINT_BASELINES = {"var": var_baseline, "factor": factor_baseline, "kalman": kalman_baseline}
