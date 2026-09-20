"""Phase 2V-B — ML model additions (XGB/LGBM direction + Chronos/TimesFM price + ensembles).

Point-in-time walk-forward. Features precomputed once; foundation models subsampled origins.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

HISTORY_LEN = 128
HORIZONS = [1, 3, 5]
SEED = 42
ML_ORIGIN_STEP = 5        # XGB/LGBM 每 5 origin 取 1（~220 origins）
REFIT_EVERY = 20          # rolling refit 間隔
FOUNDATION_STEP = 10      # foundation 每 10 origin 取 1（~110 origins）


def _load_closes():
    from market_ai_hub.providers.yfinance_provider import YFinanceProvider
    yf = YFinanceProvider()
    df = yf.fetch("^N225", period="5y", interval="1d")
    return df.sort_values("timestamp_utc").set_index("timestamp_utc")["close"].dropna().astype(float)


def _precompute(closes):
    """一次算完 lagged-return features 與 forward return 矩陣。"""
    rets = closes.pct_change()
    n = len(closes)
    cols = [f"lag{i}" for i in (1, 2, 3, 5, 10, 20)] + ["vol5", "vol20", "mom10"]
    F = pd.DataFrame(np.nan, index=range(n), columns=cols)
    for k in range(1, n):
        h = rets.iloc[:k + 1]
        for lag in (1, 2, 3, 5, 10, 20):
            F.loc[k, f"lag{lag}"] = float(h.iloc[-lag]) if len(h) >= lag else 0.0
        F.loc[k, "vol5"] = float(h.iloc[-5:].std()) if len(h) >= 5 else 0.0
        F.loc[k, "vol20"] = float(h.iloc[-20:].std()) if len(h) >= 20 else 0.0
        F.loc[k, "mom10"] = float(h.iloc[-10:].sum()) if len(h) >= 10 else 0.0
    return F.fillna(0.0)


def _direction_metrics(actual_dir, pred_dir):
    a = np.asarray(actual_dir, int); p = np.asarray(pred_dir, int)
    n = len(a)
    tp = int(((p == 1) & (a == 1)).sum()); tn = int(((p == -1) & (a == -1)).sum())
    fp = int(((p == 1) & (a == -1)).sum()); fn = int(((p == -1) & (a == 1)).sum())
    acc = (tp + tn) / n if n else 0.0
    tpr = tp / (tp + fn) if (tp + fn) else 0.0; tnr = tn / (tn + fp) if (tn + fp) else 0.0
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    f1 = 2 * prec * tpr / (prec + tpr) if (prec + tpr) else 0.0
    denom = np.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    mcc = ((tp * tn) - (fp * fn)) / denom if denom > 0 else 0.0
    return {"accuracy": acc, "balanced_accuracy": (tpr + tnr) / 2, "precision": prec,
            "recall": tpr, "F1": f1, "MCC": mcc}


def _price_metrics(actual_ret, pred_ret):
    e = np.asarray(pred_ret) - np.asarray(actual_ret)
    ae = np.abs(e)
    naive_ae = np.abs(np.asarray(actual_ret))
    return {"MAE_RETURN": float(ae.mean()), "RMSE": float(np.sqrt((e ** 2).mean())),
            "MASE": float(ae.mean() / (naive_ae.mean() + 1e-12))}


def run_xgb_lgbm(closes, F):
    from market_ai_hub.models.baseline_ml import _new_model
    out = {}
    rets = closes.pct_change()
    MIN_TRAIN = 60
    for h in HORIZONS:
        origins = [p for p in range(HISTORY_LEN, len(closes) - h, ML_ORIGIN_STEP)
                   if p - HISTORY_LEN + 1 >= MIN_TRAIN]
        for name in ("xgboost", "lightgbm"):
            preds = []; actuals = []
            model = None
            for j, pos in enumerate(origins):
                if model is None or j % REFIT_EVERY == 0:
                    model = _new_model("xgb" if name == "xgboost" else "lgbm")
                    train_pos = list(range(HISTORY_LEN, pos + 1))
                    X = F.loc[train_pos].values
                    y_raw = np.array([1 if (closes.iloc[k + h] - closes.iloc[k]) >= 0 else -1 for k in train_pos])
                    model.fit(X, (y_raw + 1) // 2)
                cur = F.loc[pos].values.reshape(1, -1)
                pred_enc = int(model.predict(cur)[0])
                pred = 1 if pred_enc == 1 else -1
                actual = 1 if (closes.iloc[pos + h] - closes.iloc[pos]) >= 0 else -1
                preds.append(pred); actuals.append(actual)
            out[f"{name}_h{h}"] = {"model": name, "horizon": h, "kind": "DIRECTION",
                                   "N": len(origins), "direction": _direction_metrics(actuals, preds)}
    return out


def run_foundation(closes):
    from market_ai_hub.services.model_runtime import get_chronos, get_timesfm
    chronos = get_chronos()
    timesfm = get_timesfm()
    out = {}
    for h in HORIZONS:
        origins = list(range(HISTORY_LEN, len(closes) - h, FOUNDATION_STEP))
        for name, adapter in (("chronos-2", chronos), ("timesfm-3.0", timesfm)):
            preds = []; actuals = []
            for pos in origins:
                ctx = closes.iloc[pos - HISTORY_LEN:pos + 1]
                try:
                    r = adapter.predict(ctx, horizon=h)
                    p50 = r["path"]["p50"][h - 1]
                except Exception:
                    p50 = float(ctx.iloc[-1])
                p_now = float(closes.iloc[pos])
                pred_r = (p50 - p_now) / p_now if p_now else 0.0
                actual_r = (closes.iloc[pos + h] - p_now) / p_now if p_now else 0.0
                preds.append(pred_r); actuals.append(actual_r)
            out[f"{name}_h{h}"] = {"model": name, "horizon": h, "kind": "PRICE", "N": len(origins),
                                   **_price_metrics(actuals, preds),
                                   "direction": _direction_metrics(
                                       [1 if r >= 0 else -1 for r in actuals],
                                       [1 if r >= 0 else -1 for r in preds])}
    return out


def run_ensembles(closes):
    def _ridge_forecast(c, pos, h):
        hist = c.iloc[: pos + 1].astype(float)
        if len(hist) < 30:
            return float(hist.iloc[-1])
        y = hist.diff().dropna()
        X = pd.DataFrame({"l1": y.shift(1), "l2": y.shift(2), "l3": y.shift(3)}).dropna()
        yy = y.loc[X.index]
        if len(X) < 10:
            return float(hist.iloc[-1])
        lam = 1.0
        A = X.values.T @ X.values + lam * np.eye(X.shape[1])
        w = np.linalg.solve(A, X.values.T @ yy.values)
        last = float(hist.iloc[-1])
        diffs = list(y.iloc[-3:].values) if len(y) >= 3 else [0.0]
        pred = last
        for _ in range(h):
            d = float(np.dot(w, diffs[-3:]))
            pred = pred + d
            diffs.append(d)
        return pred

    def _var_forecast(c, pos, h):
        hist = c.iloc[: pos + 1].astype(float)
        rets = hist.pct_change().dropna()
        if len(rets) < 3:
            return float(hist.iloc[-1])
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

    def _kalman_forecast(c, pos, h):
        hist = c.iloc[: pos + 1].astype(float).values
        level = float(hist[0])
        for x in hist[1:]:
            level = level + 0.1 * (x - level)
        return level

    out = {}
    comps = {"RIDGE": _ridge_forecast, "VAR": _var_forecast, "KALMAN": _kalman_forecast}
    for h in HORIZONS:
        origins = list(range(HISTORY_LEN, len(closes) - h))
        model_preds = {m: [] for m in comps}
        actuals = []
        for pos in origins:
            p_now = float(closes.iloc[pos])
            actuals.append((closes.iloc[pos + h] - p_now) / p_now if p_now else 0.0)
            for m, fn in comps.items():
                model_preds[m].append((fn(closes, pos, h) - p_now) / p_now if p_now else 0.0)
        actuals = np.asarray(actuals)
        eq = np.mean([model_preds[m] for m in comps], axis=0)
        dyn = np.zeros(len(origins))
        for i in range(len(origins)):
            w = {}
            for m in comps:
                e = np.abs(np.asarray(model_preds[m][max(0, i - 20):i]) - actuals[max(0, i - 20):i])
                w[m] = 1.0 / (e.mean() + 1e-6) if len(e) else 1.0
            tw = sum(w.values())
            dyn[i] = sum(model_preds[m][i] * w[m] / tw for m in comps)
        for nm, arr in (("equal_weight", eq), ("dynamic", dyn)):
            out[f"{nm}_h{h}"] = {"model": nm, "horizon": h, "kind": "PRICE", "N": len(origins),
                                 **_price_metrics(actuals, arr),
                                 "direction": _direction_metrics(
                                     [1 if r >= 0 else -1 for r in actuals],
                                     [1 if r >= 0 else -1 for r in arr])}
    return out


def main():
    closes = _load_closes()
    F = _precompute(closes)
    all_out = {}
    print("xgb/lgbm direction...")
    all_out.update(run_xgb_lgbm(closes, F))
    print("foundation chronos/timesfm...")
    all_out.update(run_foundation(closes))
    print("ensembles...")
    all_out.update(run_ensembles(closes))

    flat = []
    for r in all_out.values():
        d = {"target": "^N225", "kind": r["kind"], "horizon": r["horizon"], "model": r["model"], "N": r["N"]}
        if r["kind"] == "PRICE":
            d.update({k: r.get(k) for k in ("MAE_RETURN", "RMSE", "MASE")})
            d["direction_accuracy"] = r["direction"]["accuracy"]
            d["direction_balanced_accuracy"] = r["direction"]["balanced_accuracy"]
        else:
            d.update(r["direction"])
        flat.append(d)
    df = pd.DataFrame(flat)
    try:
        merged = pd.concat([pd.read_csv("PROXY_REFERENCE_OOS_RESULTS.csv"), df], ignore_index=True)
    except FileNotFoundError:
        merged = df
    merged.to_csv("PROXY_REFERENCE_OOS_RESULTS.csv", index=False)

    try:
        res = json.load(open("data/phase2vb_results.json", encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        res = {}
    res.setdefault("PROXY_ML", {})["models"] = all_out
    res["PROXY_ML"]["ml_origin_step"] = ML_ORIGIN_STEP
    res["PROXY_ML"]["foundation_step"] = FOUNDATION_STEP
    res["PROXY_ML"]["generated_at"] = datetime.now(timezone.utc).isoformat()
    json.dump(res, open("data/phase2vb_results.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=str)

    for r in all_out.values():
        if r["kind"] == "PRICE":
            print(f"{r['model']:16s} h={r['horizon']} N={r['N']} MAE={r['MAE_RETURN']:.6f} "
                  f"MASE={r['MASE']:.3f} dir_acc={r['direction']['accuracy']:.3f}")
        else:
            print(f"{r['model']:16s} h={r['horizon']} N={r['N']} dir_acc={r['direction']['accuracy']:.3f} "
                  f"bal={r['direction']['balanced_accuracy']:.3f}")
    print("Merged into PROXY_REFERENCE_OOS_RESULTS.csv")


if __name__ == "__main__":
    main()
