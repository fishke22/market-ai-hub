"""Phase 2C — MarketRegimeEngine（程式化，非 LLM 主觀）。

7 個 regime：trend / volatility / risk / rates / fx / event / liquidity。
全部 deterministic（閾值寫死在 code），輸出 label + evidence + sample_size + status。
樣本不足 → REGIME_EVIDENCE=INSUFFICIENT（不調權重）。

輸入 panel：DataFrame，columns = symbols，index = tz-aware datetime，值 = close。
可選事件排程（events）用於 event_regime。
"""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from market_ai_hub.regime.events import event_phase
from market_ai_hub.regime.protection import RegimeProtection


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


class MarketRegimeEngine:
    def __init__(self, minimum_sample_size: int = 20, shrink_k: float = 20.0,
                 vol_thresholds: dict | None = None) -> None:
        self.protection = RegimeProtection(minimum_sample_size, shrink_k)
        self.vol_thresholds = vol_thresholds or {"low": 0.10, "normal": 0.25, "high": 0.40}
        self.trend_threshold = 0.02
        self.fx_threshold = 0.02

    def compute(self, panel: pd.DataFrame, as_of: datetime | None = None,
                events: list | None = None) -> dict:
        """計算全部 regime（no look-ahead：只用 as_of 之前的資料）。"""
        panel = panel.copy()
        if as_of is not None:
            panel = panel[panel.index <= pd.Timestamp(_aware(as_of))]
        return {
            "trend_regime": self._trend(panel),
            "volatility_regime": self._volatility(panel),
            "risk_regime": self._risk(panel),
            "rates_regime": self._rates(panel),
            "fx_regime": self._fx(panel),
            "event_regime": self._event(panel, as_of, events),
            "liquidity_regime": self._liquidity(panel),
        }

    def _series(self, panel: pd.DataFrame, col: str) -> pd.Series | None:
        return panel[col].dropna() if col in panel.columns else None

    def _result(self, regime: str, label: str, n: int, evidence: dict, extra: dict | None = None) -> dict:
        r = {
            "regime": regime, "label": label, "status": "OK",
            "sample_size": int(n), "evidence": evidence,
        }
        if extra:
            r.update(extra)
        return r

    def _trend(self, panel) -> dict:
        s = self._series(panel, "^N225")
        if s is None or len(s) < 200:
            n = len(s) if s is not None else 0
            return self.protection.insufficient_result("trend_regime", n)
        ma20 = s.rolling(20).mean().iloc[-1]
        ma200 = s.rolling(200).mean().iloc[-1]
        ratio = ma20 / ma200 - 1.0
        label = "bull" if ratio > self.trend_threshold else ("bear" if ratio < -self.trend_threshold else "sideways")
        return self._result("trend_regime", label, 200,
                            {"ma20": float(ma20), "ma200": float(ma200), "ratio": float(ratio)},
                            {"confidence_interval": None, "confidence_status": "NOT_ESTIMATED"})

    def _volatility(self, panel) -> dict:
        s = self._series(panel, "^N225")
        if s is None or len(s) < 21:
            n = len(s) if s is not None else 0
            return self.protection.insufficient_result("volatility_regime", n)
        rets = s.pct_change().dropna()
        vol = float(rets.tail(20).std() * np.sqrt(252))
        t = self.vol_thresholds
        label = "low" if vol < t["low"] else ("normal" if vol < t["normal"] else ("high" if vol < t["high"] else "crisis"))
        return self._result("volatility_regime", label, len(rets),
                            {"realized_vol_20d_annualized": vol})

    def _risk(self, panel) -> dict:
        vix = self._series(panel, "VIX")
        if vix is None or len(vix) == 0:
            return self.protection.insufficient_result("risk_regime", 0)
        v = float(vix.iloc[-1])
        label = "risk_on" if v < 15 else ("neutral" if v <= 25 else "risk_off")
        return self._result("risk_regime", label, len(vix), {"vix": v})

    def _rates(self, panel) -> dict:
        us10 = self._series(panel, "US10Y")
        us5 = self._series(panel, "US5Y")
        if us10 is None or us5 is None:
            return self.protection.insufficient_result("rates_regime", 0)
        curve = pd.concat([us10.rename("US10Y"), us5.rename("US5Y")], axis=1).dropna()
        if len(curve) < 21:
            return self.protection.insufficient_result("rates_regime", len(curve))
        slope = float(curve["US10Y"].iloc[-1] - curve["US5Y"].iloc[-1])
        if slope < -0.1:
            shape = "inverted"
        elif slope < 0.3:
            shape = "flat"
        else:
            shape = "normal"
        change_20 = float(curve["US10Y"].iloc[-1] - curve["US10Y"].iloc[-21])
        direction = "rising" if change_20 > 0 else "falling"
        return self._result("rates_regime", f"{shape}_{direction}", len(curve),
                            {"us10y": float(curve["US10Y"].iloc[-1]),
                             "us5y": float(curve["US5Y"].iloc[-1]),
                             "slope": slope, "curve": "10Y-5Y",
                             "lookback_sessions": 20, "us10y_change_20": change_20})

    def _fx(self, panel) -> dict:
        s = self._series(panel, "USDJPY=X")
        if s is None or len(s) < 21:
            n = len(s) if s is not None else 0
            return self.protection.insufficient_result("fx_regime", n)
        r = float(s.iloc[-1] / s.iloc[-21] - 1.0)
        label = "usd_strength" if r > self.fx_threshold else ("jpy_strength" if r < -self.fx_threshold else "range")
        return self._result("fx_regime", label, 21, {"usdjpy_20d_return": r})

    def _event(self, panel, as_of, events) -> dict:
        if not events:
            return {"regime": "event_regime", "label": "none", "status": "OK",
                    "sample_size": 0, "evidence": {"note": "no schedule provided"}}
        phase = event_phase(events, as_of or datetime.now(timezone.utc))
        return {"regime": "event_regime", "label": phase.lower(), "status": "OK",
                "sample_size": 0, "evidence": {"phase": phase, "n_events": len(events)}}

    def _liquidity(self, panel) -> dict:
        vol_cols = [c for c in panel.columns if c.endswith("_volume")]
        if not vol_cols:
            return {"regime": "liquidity_regime", "label": "unknown", "status": "OK",
                    "sample_size": 0, "evidence": {"note": "no volume data"}}
        vol = panel[vol_cols].sum(axis=1)
        if len(vol) < 21:
            return self.protection.insufficient_result("liquidity_regime", len(vol))
        recent = vol.tail(20).mean()
        hist = vol.rolling(20).mean().dropna()
        pct = float((hist < recent).mean())
        label = "liquid" if pct > 0.66 else ("illiquid" if pct < 0.33 else "normal")
        return self._result("liquidity_regime", label, len(hist), {"volume_percentile": pct})
