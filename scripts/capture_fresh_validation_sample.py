"""Phase 2Q-F.7 — fresh official market sample validation（engineering runtime validation only）。

標記：sample_role=ENGINEERING_RUNTIME_VALIDATION_ONLY, not_training_data=true,
not_model_selection_data=true, not_predictive_evidence=true。

輸出 local-only：<MARKET_AI_DATA_ROOT>/validation_samples/YYYY-MM-DD/。
Raw external data GIT_EXCLUDED。Repo report 只記 metadata / hash / comparison outcome。
不得用 fresh sample 升級 model evidence。

用法：python scripts/capture_fresh_validation_sample.py [--date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SAMPLE_META = {
    "sample_role": "ENGINEERING_RUNTIME_VALIDATION_ONLY",
    "not_training_data": True,
    "not_model_selection_data": True,
    "not_predictive_evidence": True,
}


def _twse_taiex(date_yyyymmdd: str) -> float | None:
    import httpx

    r = httpx.get(
        "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX",
        params={"date": date_yyyymmdd, "type": "IND", "response": "json"}, timeout=25.0,
    )
    d = r.json()
    for t in d.get("tables", []):
        for row in t.get("data", []):
            if "發行量加權股價指數" in str(row[0]):
                return float(str(row[1]).replace(",", ""))
    return None


def _twse_stock_day(stock: str, date_yyyymmdd: str) -> dict | None:
    import httpx

    ym = date_yyyymmdd[:6]
    r = httpx.get(
        "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY",
        params={"date": ym + "01", "stockNo": stock, "response": "json"}, timeout=25.0,
    )
    d = r.json()
    want = f"{date_yyyymmdd[4:6]}/{date_yyyymmdd[6:8]}"  # MM/DD
    for row in d.get("data", []):
        if want in str(row[0]):
            return {"open": float(str(row[3]).replace(",", "")), "high": float(str(row[4]).replace(",", "")),
                    "low": float(str(row[5]).replace(",", "")), "close": float(str(row[6]).replace(",", "")),
                    "volume": int(str(row[1]).replace(",", ""))}
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    args = ap.parse_args()
    date_compact = args.date.replace("-", "")

    from market_ai_hub.config.runtime_paths import data_root
    from market_ai_hub.packet.builder import build_analysis_packet

    out_dir = data_root() / "validation_samples" / args.date
    out_dir.mkdir(parents=True, exist_ok=True)

    report = {"date": args.date, "retrieved_at": datetime.now(timezone.utc).isoformat(), **SAMPLE_META, "checks": []}

    # TAIEX
    off_taiex = _twse_taiex(date_compact)
    rt_taiex = build_analysis_packet(market="taiwan_index", target="TAIEX", detail_level="compact", save_analysis=False).get("reference_price")
    report["checks"].append({
        "market": "TAIWAN_INDEX", "instrument": "TAIEX", "trading_date": args.date,
        "source": "TWSE official MI_INDEX",
        "official": off_taiex, "runtime": round(rt_taiex, 2) if rt_taiex else None,
        "match": (off_taiex is not None and rt_taiex is not None and abs(off_taiex - rt_taiex) < 0.01),
    })

    # 3706 / 2330
    for stock in ("3706", "2330"):
        off = _twse_stock_day(stock, date_compact)
        rt = build_analysis_packet(market="taiwan", target=f"{stock}.TW", detail_level="compact", save_analysis=False).get("reference_price")
        report["checks"].append({
            "market": "TAIWAN_STOCK", "instrument": f"{stock}.TW", "trading_date": args.date,
            "source": "TWSE official STOCK_DAY",
            "official_close": off["close"] if off else None,
            "runtime": round(rt, 2) if rt else None,
            "match": (off is not None and rt is not None and abs(off["close"] - rt) < 0.01),
        })

    # hash of report (metadata only; raw external data not persisted to repo)
    report["report_hash"] = hashlib.sha256(json.dumps(report, sort_keys=True, default=str).encode()).hexdigest()[:16]
    (out_dir / "fresh_validation_sample.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    print(f"written -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
