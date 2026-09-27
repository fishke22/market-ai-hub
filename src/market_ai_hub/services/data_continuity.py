"""Accuracy v2 data-continuity mode for JNU.

The continuity layer keeps the system useful when the exact JNU target stream is
missing, stale, or internally inconsistent. It never fabricates a target, never
backfills a missed forward prediction, and never promotes context/proxy data into
target evidence.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from typing import Any

import pandas as pd

from market_ai_hub.research.accuracy_v2_p1 import jpx_report_publication_for_session
from market_ai_hub.services.jnu_direct import (
    load_current_micro_settlement_receipts,
    load_direct_micro_settlements,
    next_published_settlement_observation_dates,
)
from market_ai_hub.targets.coverage import (
    LiveCoverageAuditor,
    MISSING,
    NEEDS_CONFIG,
    PROXY,
    REFERENCE_AVAILABLE,
    SOURCE_VERIFIED,
)
from market_ai_hub.targets.jpx_daily import JPXOSEDailyReportProvider


CONTINUITY_SCHEMA_VERSION = "AV2.CONTINUITY.1"
NORMAL_MODE = "NORMAL_TARGET_DATA"
CONTINUITY_MODE = "DATA_CONTINUITY_MODE"
PUBLICATION_GRACE_MINUTES = 30


def _aware_utc(value: datetime | None) -> datetime:
    out = value or datetime.now(timezone.utc)
    if out.tzinfo is None or out.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return out.astimezone(timezone.utc)


def _daily_channel() -> pd.DataFrame:
    frame = JPXOSEDailyReportProvider().load("Nikkei 225 Micro")
    return frame.copy() if frame is not None else pd.DataFrame()


def _channel_values(frame: pd.DataFrame, *, contract_month: str, date_text: str) -> tuple[list[float], list[str]]:
    if frame is None or frame.empty:
        return [], []
    work = frame.copy()
    if "contract_month" not in work or "date" not in work or "settlement" not in work:
        return [], []
    work["contract_month"] = work["contract_month"].astype(str)
    work["date"] = work["date"].astype(str)
    work["settlement"] = pd.to_numeric(work["settlement"], errors="coerce")
    work = work[
        work["contract_month"].eq(str(contract_month))
        & work["date"].eq(str(date_text))
    ]
    values = sorted({
        float(v)
        for v in work["settlement"].dropna().tolist()
        if math.isfinite(float(v)) and float(v) > 0
    })
    hashes = sorted({
        str(v).strip()
        for v in work.get("source_hash", pd.Series(dtype=str)).tolist()
        if str(v).strip()
    })
    return values, hashes


def _context_channels() -> list[dict[str, Any]]:
    overrides = {
        "Micro settlement": {
            "status": REFERENCE_AVAILABLE,
            "source": "JPX official settlement / Daily Report",
        },
        "VIX": {
            "status": PROXY,
            "source": "yfinance ^VIX runtime observation",
        },
        "CPI": {
            "status": SOURCE_VERIFIED,
            "source": "BLS API v2 official source",
        },
        "NFP": {
            "status": SOURCE_VERIFIED,
            "source": "BLS API v2 official source",
        },
    }
    rows = LiveCoverageAuditor().audit_osaka(overrides)
    return [
        {
            "factor": r.factor,
            "source": r.source,
            "status": r.status,
            "role": (
                "DIRECT_TARGET_REFERENCE"
                if r.factor == "Micro settlement"
                else "CONTEXT_ONLY"
            ),
        }
        for r in rows
        if r.status not in {MISSING, NEEDS_CONFIG}
    ]


def jnu_data_continuity_status(
    *,
    now: datetime | None = None,
    contract_month: str = "",
    publication_grace_minutes: int = PUBLICATION_GRACE_MINUTES,
) -> dict[str, Any]:
    """Return a fail-closed JNU target continuity snapshot.

    NORMAL_TARGET_DATA means the last exact-contract official observation is still
    valid as the current reference. DATA_CONTINUITY_MODE means only context/risk
    analysis is allowed until exact target data is restored.
    """
    as_of = _aware_utc(now)
    series, meta = load_direct_micro_settlements(contract_month)
    base: dict[str, Any] = {
        "schema_version": CONTINUITY_SCHEMA_VERSION,
        "as_of": as_of.isoformat(),
        "mode": CONTINUITY_MODE,
        "context_only": True,
        "target_reference_available": False,
        "target_prediction_allowed": False,
        "new_forward_precommit_allowed": False,
        "forward_evidence_update_allowed": False,
        "proxy_can_replace_target": False,
        "calibrated_probability_available": False,
        "trading_edge_available": False,
        "context_confidence_not_probability": True,
        "context_channels": _context_channels(),
    }
    if meta.get("status") != "OK" or series.empty:
        return {
            **base,
            "reason": str(meta.get("status") or "NO_EXACT_TARGET_REFERENCE"),
            "freshness_status": "TARGET_REFERENCE_UNAVAILABLE",
            "context_confidence_grade": "VERY_LOW",
            "data": meta,
            "source_redundancy": {
                "status": "NO_EXACT_TARGET_REFERENCE",
                "source_channel_count": 0,
                "matching_channel_count": 0,
                "independent_publisher_count": 0,
                "hash_verified": False,
                "revision_conflict": False,
            },
        }

    month = str(meta["contract_month"])
    latest_date = str(meta["latest_date"])
    anchor = float(meta["latest_settlement"])
    next_dates = next_published_settlement_observation_dates(latest_date, 1)
    next_observation = next_dates[0] if next_dates else None
    expected_publication = (
        jpx_report_publication_for_session(next_observation).astimezone(timezone.utc)
        if next_observation
        else None
    )
    deadline = (
        expected_publication + timedelta(minutes=int(publication_grace_minutes))
        if expected_publication
        else None
    )

    daily_values, daily_hashes = _channel_values(
        _daily_channel(),
        contract_month=month,
        date_text=latest_date,
    )
    receipts = load_current_micro_settlement_receipts(month)
    receipt_values, receipt_hashes = _channel_values(
        receipts,
        contract_month=month,
        date_text=latest_date,
    )
    channels = [
        {
            "channel": "JPX_OSE_DAILY_REPORT",
            "available": bool(daily_values),
            "values": daily_values,
            "matches_anchor": bool(daily_values) and all(math.isclose(v, anchor, rel_tol=0.0, abs_tol=1e-12) for v in daily_values),
            "source_hashes": daily_hashes,
        },
        {
            "channel": "JPX_SETTLEMENT_RECEIPT",
            "available": bool(receipt_values),
            "values": receipt_values,
            "matches_anchor": bool(receipt_values) and all(math.isclose(v, anchor, rel_tol=0.0, abs_tol=1e-12) for v in receipt_values),
            "source_hashes": receipt_hashes,
        },
    ]
    available = [c for c in channels if c["available"]]
    revision_conflict = (
        len(daily_values) > 1
        or len(receipt_values) > 1
        or any(not c["matches_anchor"] for c in available)
    )
    matching = sum(1 for c in available if c["matches_anchor"])
    all_hashes = daily_hashes + receipt_hashes
    hash_verified = bool(available) and all(bool(c["source_hashes"]) for c in available)

    if revision_conflict:
        redundancy_status = "SOURCE_CONFLICT"
    elif matching >= 2:
        redundancy_status = "DUAL_CHANNEL_MATCH"
    elif matching == 1:
        redundancy_status = "SINGLE_CHANNEL_ONLY"
    else:
        redundancy_status = "NO_CHANNEL_MATCH"

    stale = deadline is None or as_of > deadline
    if revision_conflict:
        mode = CONTINUITY_MODE
        reason = "EXACT_TARGET_SOURCE_CONFLICT"
        freshness = "SOURCE_CONFLICT"
        context_grade = "VERY_LOW"
    elif stale:
        mode = CONTINUITY_MODE
        reason = "EXPECTED_PUBLISHED_OBSERVATION_OVERDUE"
        freshness = "STALE_EXPECTED_OBSERVATION_MISSING"
        context_grade = "LOW"
    else:
        mode = NORMAL_MODE
        reason = ""
        freshness = "FRESH_UNTIL_NEXT_EXPECTED_PUBLICATION"
        context_grade = "HIGH" if matching >= 2 else "MEDIUM"

    normal = mode == NORMAL_MODE
    return {
        **base,
        "mode": mode,
        "reason": reason,
        "context_only": not normal,
        "target_reference_available": True,
        "target_prediction_allowed": normal,
        "new_forward_precommit_allowed": normal,
        "forward_evidence_update_allowed": False,
        "freshness_status": freshness,
        "context_confidence_grade": context_grade,
        "latest_reference": {
            "contract_month": month,
            "exact_contract": str(meta.get("quote_code") or ""),
            "date": latest_date,
            "settlement": anchor,
            "received_at": meta.get("latest_received_at"),
            "source_hash": meta.get("latest_source_hash"),
        },
        "next_expected_published_observation_date": next_observation,
        "next_expected_publication_at": (
            expected_publication.isoformat() if expected_publication else None
        ),
        "stale_after": deadline.isoformat() if deadline else None,
        "source_redundancy": {
            "status": redundancy_status,
            "channels": channels,
            "source_channel_count": len(available),
            "matching_channel_count": matching,
            "independent_publisher_count": 1 if available else 0,
            "independent_publisher_note": "Both channels are JPX/OSE; channel redundancy is not publisher independence.",
            "hash_verified": hash_verified,
            "source_hash_count": len(set(all_hashes)),
            "revision_conflict": revision_conflict,
        },
        "data": meta,
        "p5_precommit_gate": (
            "DELEGATE_TO_P5_ORIGIN_GATE"
            if normal
            else "BLOCKED_DATA_CONTINUITY_MODE"
        ),
    }


def jnu_continuity_user_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Plain-language context-only user output."""
    ref = snapshot.get("latest_reference") or {}
    point = None
    volatility = None
    interval = None
    if snapshot.get("target_reference_available"):
        try:
            from market_ai_hub.research.accuracy_v2_p4_engine import analyze_no_new_forward_outcome

            robust = analyze_no_new_forward_outcome()
            if robust.get("status") == "OK":
                point = (robust.get("point_reference") or {}).get("price")
                volatility = (robust.get("volatility") or {}).get("ewma_return_volatility")
                empirical = robust.get("empirical_interval") or {}
                if empirical.get("lower_price") is not None and empirical.get("upper_price") is not None:
                    interval = [float(empirical["lower_price"]), float(empirical["upper_price"])]
        except Exception:
            pass

    return {
        "商品": "大阪日經225微型期貨（JNU）",
        "模式": "資料連續性模式（只做情境與風險分析）",
        "原因": snapshot.get("reason") or "exact JNU target stream is not currently usable",
        "最新可信官方資料": (
            f"{ref.get('date')} {ref.get('exact_contract')} 清算價 {float(ref.get('settlement')):,.0f} 點"
            if ref.get("settlement") is not None
            else "目前沒有可用的 exact JNU 官方價格錨"
        ),
        "資料新鮮度": snapshot.get("freshness_status"),
        "下一筆預期官方觀測": snapshot.get("next_expected_published_observation_date"),
        "下一個預期發布時間": snapshot.get("next_expected_publication_at"),
        "來源交叉驗證": snapshot.get("source_redundancy"),
        "情境參考": {
            "最後官方價格錨": point,
            "EWMA日報酬波動": volatility,
            "開發期經驗區間": interval,
            "區間不是機率": True,
        },
        "目前允許": [
            "使用最後可信 official JNU settlement 作價格錨",
            "使用波動、事件與其他市場資料作 context / risk assessment",
            "資料恢復後重新執行 exact-target 分析",
        ],
        "目前暫停": [
            "新的 exact JNU target prediction",
            "補寫錯過的 forward prediction",
            "用 proxy 代替 JNU target outcome",
            "新增 predictive-gain evidence",
            "公開 calibrated probability",
            "宣稱 trading edge",
        ],
        "具體建議": (
            "先等待 exact JNU 官方資料恢復；期間只用 context 判斷風險與可能情境。"
            "若來源互相衝突，先解決 revision/source conflict，再恢復 target prediction。"
        ),
        "PREDICTIVE_GAIN": False,
        "CALIBRATED": False,
        "TRADING_EDGE": False,
    }
