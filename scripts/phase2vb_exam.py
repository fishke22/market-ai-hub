"""Phase 2V-B — Historical OOS walk-forward exam (point-in-time, no leakage).

Runs a formal historical exam per research/phase2/protocols/HISTORICAL_OOS_PROTOCOL.yaml v1.
- DIRECT target (OSE Micro settlement): data coverage audited → INSUFFICIENT_EVIDENCE (1 day only).
- PROXY target (^N225): full walk-forward with baselines + models + stats.

No live trading / no parameter mining / no champion promotion / no leakage.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

# ── reproducible config ──
SEED = 42
HISTORY_LEN = 128
HORIZONS = [1, 3, 5]
N_BOOT = 500
BLOCK_LEN = 5

RESULTS: dict = {}


def _rec(section, key, value):
    RESULTS.setdefault(section, {})[key] = value


# ──────────────────────────────────────────────── price baselines
def _price_baseline(name, closes, pos, h):
    hist = closes.iloc[: pos + 1]
    last = float(hist.iloc[-1])
    if name == "LAST_VALUE":
        return last
    if name == "DRIFT":
        rets = hist.pct_change().dropna()
        drift = float(rets.mean()) if len(rets) else 0.0
        return last * (1 + drift) ** h
    if name == "MOVING_AVERAGE":
        ma = hist.rolling(20).mean().iloc[-1]
        return float(ma) if pd.notna(ma) else last
    if name == "SEASONAL_NAIVE":
        # 用 h 天前（若可用）當預測，否則 last
        if pos + 1 - h >= 0:
            return float(closes.iloc[pos + 1 - h])
        return last
    raise ValueError(name)


def _ridge_forecast(closes, pos, h):
    """簡易 ridge：lag1..lag5 迴歸預測下一步，再迭代 h 步。"""
    hist = closes.iloc[: pos + 1].astype(float)
    if len(hist) < 30:
        return float(hist.iloc[-1])
    y = hist.diff().dropna()
    X = pd.DataFrame({"l1": y.shift(1), "l2": y.shift(2), "l3": y.shift(3)}).dropna()
    yy = y.loc[X.index]
    if len(X) < 10:
        return float(hist.iloc[-1])
    X = X.values
    yy = yy.values
    # closed-form ridge (lambda=1)
    lam = 1.0
    A = X.T @ X + lam * np.eye(X.shape[1])
    w = np.linalg.solve(A, X.T @ yy)
    last = float(hist.iloc[-1])
    diffs = list(y.iloc[-3:].values) if len(y) >= 3 else [0.0]
    pred = last
    for _ in range(h):
        d = float(np.dot(w, diffs[-3:]))
        pred = pred + d
        diffs.append(d)
    return pred


def _kalman_forecast(closes, pos, h):
    """local-level Kalman（簡單隨機漫步平滑），預測 = 最後 level。"""
    hist = closes.iloc[: pos + 1].astype(float).values
    level = float(hist[0])
    for x in hist[1:]:
        level = level + 0.1 * (x - level)  # 固定 gain 的簡化 local-level
    return level


def _var_forecast(closes, pos, h):
    """AR(1)（單變量 VAR(1) 退化）迭代 h 步。"""
    hist = closes.iloc[: pos + 1].astype(float)
    if len(hist) < 5:
        return float(hist.iloc[-1])
    rets = hist.pct_change().dropna()
    if len(rets) < 3:
        return float(hist.iloc[-1])
    # AR(1): r_t = a + b r_{t-1}
    x = rets.shift(1).dropna().values
    y = rets.iloc[1:].values
    b = float(np.corrcoef(x, y)[0, 1]) if len(x) > 2 else 0.0
    a = float(y.mean() - b * x.mean())
    last = float(hist.iloc[-1])
    r = float(rets.iloc[-1])
    pred = last
    for _ in range(h):
        r = a + b * r
        pred = pred * (1 + r)
    return pred


PRICE_MODELS = {
    "LAST_VALUE": lambda c, p, h: _price_baseline("LAST_VALUE", c, p, h),
    "SEASONAL_NAIVE": lambda c, p, h: _price_baseline("SEASONAL_NAIVE", c, p, h),
    "DRIFT": lambda c, p, h: _price_baseline("DRIFT", c, p, h),
    "MOVING_AVERAGE": lambda c, p, h: _price_baseline("MOVING_AVERAGE", c, p, h),
    "RIDGE": _ridge_forecast,
    "VAR": _var_forecast,
    "KALMAN": _kalman_forecast,
}


def _direction_baseline(name, closes, pos, h):
    hist = closes.iloc[: pos + 1]
    if name == "ALWAYS_UP":
        return 1
    if name == "ALWAYS_DOWN":
        return -1
    if name == "PREVIOUS_DIRECTION":
        d = float(hist.iloc[-1] - hist.iloc[-2]) if len(hist) >= 2 else 0.0
        return 1 if d >= 0 else -1
    if name == "MA_TREND":
        if len(hist) < 20:
            return 1
        ma_fast = float(hist.rolling(5).mean().iloc[-1])
        ma_slow = float(hist.rolling(20).mean().iloc[-1])
        return 1 if ma_fast >= ma_slow else -1
    return 1


DIRECTION_MODELS = {
    "ALWAYS_UP": lambda c, p, h: _direction_baseline("ALWAYS_UP", c, p, h),
    "ALWAYS_DOWN": lambda c, p, h: _direction_baseline("ALWAYS_DOWN", c, p, h),
    "PREVIOUS_DIRECTION": lambda c, p, h: _direction_baseline("PREVIOUS_DIRECTION", c, p, h),
    "MA_TREND": lambda c, p, h: _direction_baseline("MA_TREND", c, p, h),
}


# ──────────────────────────────────────────────── metrics
def _price_metrics(actual_ret, pred_ret):
    actual_ret = np.asarray(actual_ret, float)
    pred_ret = np.asarray(pred_ret, float)
    err = pred_ret - actual_ret
    ae = np.abs(err)
    mae = float(ae.mean())
    rmse = float(np.sqrt((err ** 2).mean()))
    medae = float(np.median(ae))
    smape = float((2 * ae / (np.abs(actual_ret) + np.abs(pred_ret) + 1e-9)).mean() * 100)
    bias = float(err.mean())
    # MASE vs LAST_VALUE（naive=預測 0 return → |0-actual|）
    naive_ae = np.abs(actual_ret)
    mase = float(ae.mean() / (naive_ae.mean() + 1e-12))
    return {"MAE_RETURN": mae, "RMSE": rmse, "MedianAE": medae, "sMAPE": smape,
            "forecast_bias": bias, "MASE": mase}


def _direction_metrics(actual_dir, pred_dir):
    actual_dir = np.asarray(actual_dir, int)
    pred_dir = np.asarray(pred_dir, int)
    n = len(actual_dir)
    tp = int(((pred_dir == 1) & (actual_dir == 1)).sum())
    tn = int(((pred_dir == -1) & (actual_dir == -1)).sum())
    fp = int(((pred_dir == 1) & (actual_dir == -1)).sum())
    fn = int(((pred_dir == -1) & (actual_dir == 1)).sum())
    acc = float((tp + tn) / n) if n else 0.0
    # balanced accuracy = (TPR + TNR)/2
    tpr = tp / (tp + fn) if (tp + fn) else 0.0
    tnr = tn / (tn + fp) if (tn + fp) else 0.0
    bal = float((tpr + tnr) / 2)
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tpr
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    # MCC
    denom = np.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    mcc = float(((tp * tn) - (fp * fn)) / denom) if denom > 0 else 0.0
    return {"accuracy": acc, "balanced_accuracy": bal, "precision": prec,
            "recall": rec, "F1": f1, "MCC": mcc}


def _moving_block_bootstrap(errors, n_boot=N_BOOT, block=BLOCK_LEN, stat=np.mean):
    errors = np.asarray(errors, float)
    n = len(errors)
    if n < block:
        block = max(1, n)
    n_blocks = int(np.ceil(n / block))
    rng = np.random.default_rng(SEED)
    stats = []
    for _ in range(n_boot):
        idx = rng.integers(0, n - block + 1, size=n_blocks)
        sample = np.concatenate([errors[i:i + block] for i in idx])[:n]
        stats.append(stat(sample))
    lo, hi = np.percentile(stats, [2.5, 97.5])
    return float(lo), float(hi)


def _dm_hac_pvalue(e1, e2):
    """Diebold-Mariano（等 loss）with Newey-West HAC variance correction."""
    d = np.asarray(e1, float) ** 2 - np.asarray(e2, float) ** 2
    n = len(d)
    if n < 3:
        return float("nan")
    dbar = d.mean()
    # Newey-West with L = horizon-ish lag (use min(5, n//4))
    L = min(5, n // 4)
    gamma0 = np.sum((d - dbar) ** 2) / n
    cov = gamma0
    for l in range(1, L + 1):
        w = 1 - l / (L + 1)
        cov += 2 * w * np.sum((d[l:] - dbar) * (d[:-l] - dbar)) / n
    var = cov / n
    if var <= 0:
        return float("nan")
    stat = dbar / np.sqrt(var)
    # normal approx p-value
    from math import erf, sqrt
    p = 2 * (1 - 0.5 * (1 + erf(abs(stat) / sqrt(2))))
    return float(p)


def _bh_fdr(pvals):
    p = [v for v in pvals if v == v]  # drop nan
    if not p:
        return []
    m = len(p)
    order = np.argsort(p)
    adj = np.ones(m)
    for rank, i in enumerate(order):
        adj[i] = min(1.0, p[i] * m / (rank + 1))
    # monotonic
    for i in range(m - 2, -1, -1):
        adj[order[i]] = min(adj[order[i]], adj[order[i + 1]])
    return adj.tolist()


# ──────────────────────────────────────────────── regime
def _regime(closes, pos):
    hist = closes.iloc[: pos + 1]
    ret = hist.pct_change().dropna()
    last20 = ret.iloc[-20:]
    vol = float(last20.std()) if len(last20) else 0.0
    trend = float(hist.iloc[-1] - hist.iloc[-20]) if len(hist) >= 20 else 0.0
    vol_med = float(ret.rolling(60).std().median()) if len(ret) >= 60 else vol
    if pd.isna(vol_med) or vol_med == 0:
        vol_regime = "LOW_VOL"
    else:
        vol_regime = "HIGH_VOL" if vol > vol_med else "LOW_VOL"
    trend_regime = "TREND_UP" if trend >= 0 else "TREND_DOWN"
    return f"{vol_regime}|{trend_regime}"


# ──────────────────────────────────────────────── main exam
def load_proxy():
    from market_ai_hub.providers.yfinance_provider import YFinanceProvider
    yf = YFinanceProvider()
    df = yf.fetch("^N225", period="5y", interval="1d")
    closes = df.sort_values("timestamp_utc").set_index("timestamp_utc")["close"].dropna()
    return closes


def run_proxy_exam(closes):
    closes = closes.astype(float)
    n = len(closes)
    horizon_results = {}
    # best simple baseline (per horizon) = lowest MAE among LAST_VALUE/DRIFT/MA/SEASONAL_NAIVE
    for h in HORIZONS:
        origins = list(range(HISTORY_LEN, n - h))
        if not origins:
            horizon_results[h] = {"n_origins": 0, "status": "INSUFFICIENT_DATA"}
            continue
        # collect model forecasts + actuals (point-in-time)
        actuals = {}
        forecasts = {m: [] for m in PRICE_MODELS}
        dir_actuals = []
        dir_forecasts = {m: [] for m in DIRECTION_MODELS}
        regimes = []
        for pos in origins:
            # point-in-time: only data up to pos
            p_now = float(closes.iloc[pos])
            p_fut = float(closes.iloc[pos + h])
            r = (p_fut - p_now) / p_now if p_now else 0.0
            actuals.setdefault("return", []).append(r)
            actuals.setdefault("prev", []).append(p_now)
            d = 1 if r >= 0 else -1
            dir_actuals.append(d)
            regimes.append(_regime(closes, pos))
            for m, fn in PRICE_MODELS.items():
                pred_p = fn(closes, pos, h)
                pred_r = (pred_p - p_now) / p_now if p_now else 0.0
                forecasts[m].append(pred_r)
            for m, fn in DIRECTION_MODELS.items():
                dir_forecasts[m].append(fn(closes, pos, h))

        actual_ret = np.asarray(actuals["return"])
        prev = np.asarray(actuals["prev"])
        dir_act = np.asarray(dir_actuals)

        rows = []
        for m in PRICE_MODELS:
            pred_r = np.asarray(forecasts[m])
            pm = _price_metrics(actual_ret, pred_r)
            dm = _direction_metrics(dir_act, np.where(pred_r >= 0, 1, -1))
            ci_lo, ci_hi = _moving_block_bootstrap(pred_r - actual_ret, stat=np.mean)
            rows.append({"model": m, "kind": "PRICE", **pm, "direction": dm,
                         "mae_ci95": [ci_lo, ci_hi]})
        for m in DIRECTION_MODELS:
            pred_d = np.asarray(dir_forecasts[m])
            dm = _direction_metrics(dir_act, pred_d)
            rows.append({"model": m, "kind": "DIRECTION", "direction": dm})

        # best simple baseline MAE
        simple = [r for r in rows if r["model"] in ("LAST_VALUE", "SEASONAL_NAIVE", "DRIFT", "MOVING_AVERAGE")]
        best_base = min(simple, key=lambda r: r["MAE_RETURN"])["model"]
        best_mae = min(simple, key=lambda r: r["MAE_RETURN"])["MAE_RETURN"]

        # DM test each model vs best baseline + FDR
        pvals = {}
        for r in rows:
            if r["kind"] == "PRICE" and r["model"] not in ("LAST_VALUE", "SEASONAL_NAIVE", "DRIFT", "MOVING_AVERAGE"):
                e1 = np.asarray(forecasts[r["model"]]) - actual_ret
                e2 = np.asarray(forecasts[best_base]) - actual_ret
                pvals[r["model"]] = _dm_hac_pvalue(e1, e2)
        adj = _bh_fdr(list(pvals.values()))
        adj_map = dict(zip(pvals.keys(), adj)) if adj else {}

        for r in rows:
            r["horizon"] = h
            r["N"] = len(origins)
            r["best_baseline"] = best_base
            if r["kind"] == "PRICE":
                r["delta_vs_baseline_mae"] = r["MAE_RETURN"] - best_mae
                if r["model"] in pvals:
                    r["dm_p"] = pvals[r["model"]]
                    r["fdr_adj_p"] = adj_map.get(r["model"])
                else:
                    r["dm_p"] = None
                    r["fdr_adj_p"] = None
        horizon_results[h] = {"n_origins": len(origins), "best_baseline": best_base,
                              "rows": rows}
    return horizon_results


def main():
    print("=== Phase 2V-B Historical OOS exam ===")
    # DIRECT target
    import json as _j
    cov = _j.load(open("DIRECT_TARGET_COVERAGE.json", encoding="utf-8"))
    _rec("DIRECT", "coverage", cov)
    _rec("DIRECT", "status", "INSUFFICIENT_EVIDENCE")
    _rec("DIRECT", "n_origins", 0)
    _rec("DIRECT", "reason", "OSE Micro settlement history 僅 1 交易日（20260918）；JPX 公開源僅當日，歷史 404")

    # PROXY target
    closes = load_proxy()
    _rec("PROXY", "symbol", "^N225")
    _rec("PROXY", "n_bars", int(len(closes)))
    _rec("PROXY", "first_date", str(closes.index[0].date()))
    _rec("PROXY", "last_date", str(closes.index[-1].date()))
    hr = run_proxy_exam(closes)
    _rec("PROXY", "horizons", hr)

    # flatten rows for CSV
    flat = []
    for h, hr_ in hr.items():
        for r in hr_.get("rows", []):
            d = {"target": "^N225", "kind": r.get("kind"), "horizon": h, "model": r["model"],
                 "N": r.get("N")}
            if r["kind"] == "PRICE":
                d.update({k: r.get(k) for k in ("MAE_RETURN", "RMSE", "MASE", "MedianAE", "sMAPE", "forecast_bias")})
                d["direction_accuracy"] = r.get("direction", {}).get("accuracy")
                d["direction_balanced_accuracy"] = r.get("direction", {}).get("balanced_accuracy")
                d["best_baseline"] = r.get("best_baseline")
                d["delta_vs_baseline_mae"] = r.get("delta_vs_baseline_mae")
                d["mae_ci95_lo"] = r.get("mae_ci95", [None, None])[0]
                d["mae_ci95_hi"] = r.get("mae_ci95", [None, None])[1]
                d["dm_p"] = r.get("dm_p")
                d["fdr_adj_p"] = r.get("fdr_adj_p")
            else:
                d.update(r.get("direction", {}))
            flat.append(d)

    df = pd.DataFrame(flat)
    df.to_csv("PROXY_REFERENCE_OOS_RESULTS.csv", index=False)

    # DIRECT results CSV (empty / insufficient)
    pd.DataFrame([{"target": "OSE_NIKKEI225_MICRO_FUTURES", "status": "INSUFFICIENT_EVIDENCE",
                   "N": 0, "reason": "settlement history 1 day only"}]).to_csv(
        "DIRECT_OSE_MICRO_OOS_RESULTS.csv", index=False)

    # manifest
    import platform
    import torch
    from market_ai_hub.services.build_info import build_fingerprint
    fp = build_fingerprint()
    dataset_hash = hashlib.sha256(str(closes.values.tolist()[:100]).encode()).hexdigest()[:16]
    exam_hash = hashlib.sha256(("^N225|1,3,5|wf|v1|" + dataset_hash).encode()).hexdigest()[:16]
    manifest = {
        "protocol_version": 1, "exam_hash": exam_hash, "dataset_hash": dataset_hash,
        "target": "^N225 (REFERENCE_PROXY)", "horizons": HORIZONS,
        "history_len": HISTORY_LEN, "seed": SEED, "block_bootstrap": {"n": N_BOOT, "block": BLOCK_LEN},
        "python": platform.python_version(), "torch": str(torch.__version__),
        "cuda": torch.cuda.is_available(), "build_id": fp["build_id"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    import yaml
    with open("research/phase2/manifests/OOS_EXAM_MANIFEST.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(manifest, f, allow_unicode=True, sort_keys=False)

    with open("data/phase2vb_results.json", "w", encoding="utf-8") as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=2, default=str)

    # print summary
    print(f"PROXY ^N225: {len(closes)} bars")
    for h, hr_ in hr.items():
        print(f"  horizon={h}: n_origins={hr_['n_origins']}, best_baseline={hr_['best_baseline']}")
        for r in hr_["rows"]:
            if r["kind"] == "PRICE":
                print(f"    {r['model']:16s} MAE={r['MAE_RETURN']:.6f} MASE={r['MASE']:.3f} "
                      f"dir_acc={r['direction']['accuracy']:.3f} dm_p={r.get('dm_p')}")
    print("Wrote PROXY_REFERENCE_OOS_RESULTS.csv + DIRECT_OSE_MICRO_OOS_RESULTS.csv + research/phase2/manifests/OOS_EXAM_MANIFEST.yaml")


if __name__ == "__main__":
    main()
