"""Phase 2G.1 — Official Event Providers（6）。

BLS / BEA / Fed / BOJ / e-Stat / Cabinet Office / MOF / EIA / SEC EDGAR / EDINET / Cboe。
事件一律記錄 event_name / scheduled_at / released_at / source / importance_class / available_at。
遵守 information_cutoff（未 released 的事件不得對 past cutoff 可見）。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd
from pydantic import BaseModel, Field

from market_ai_hub.config.runtime_paths import data_root


class OfficialEvent(BaseModel):
    event_name: str
    scheduled_at: datetime
    released_at: datetime | None = None     # None = 尚未 release（對任何 cutoff 皆不可見）
    source: str = ""
    importance_class: str = ""              # HIGH / MEDIUM / LOW
    available_at: datetime | None = None    # = released_at（release 後才可用）


class OfficialEventProvider(BaseModel):
    name: str
    source: str
    series: list[str] = Field(default_factory=list)
    status: str = "ACTIVE"                  # ACTIVE / CONFIG_ONLY
    note: str = ""


def official_event_providers() -> dict[str, OfficialEventProvider]:
    return {
        "BLS": OfficialEventProvider(name="BLS", source="https://www.bls.gov/",
                                     series=["CPI", "NFP", "Employment Situation", "Payrolls"]),
        "BEA": OfficialEventProvider(name="BEA", source="https://www.bea.gov/",
                                     series=["PCE", "GDP"]),
        "FED": OfficialEventProvider(name="Federal Reserve", source="https://www.federalreserve.gov/",
                                     series=["FOMC calendar", "statements", "minutes"]),
        "BOJ": OfficialEventProvider(name="BOJ", source="https://www.boj.or.jp/",
                                     series=["Release Schedule", "MPM schedule"]),
        "ESTAT": OfficialEventProvider(name="Japan e-Stat", source="https://www.e-stat.go.jp/",
                                       series=["CPI", "employment/labor"]),
        "CABINET": OfficialEventProvider(name="Japan Cabinet Office", source="https://www.cao.go.jp/",
                                         series=["GDP release calendar"]),
        "MOF": OfficialEventProvider(name="Japan MOF", source="https://www.mof.go.jp/",
                                     series=["FX intervention", "weekly/monthly schedules"]),
        "EIA": OfficialEventProvider(name="EIA", source="https://www.eia.gov/",
                                     series=["energy/oil"]),
        "EDGAR": OfficialEventProvider(name="SEC EDGAR", source="https://www.sec.gov/edgar/",
                                       series=["US major-company filings/events"]),
        "EDINET": OfficialEventProvider(name="EDINET", source="https://disclosure.edinet-fsa.go.jp/",
                                        series=["Japan filings"], status="CONFIG_ONLY",
                                        note="config-only until API key exists"),
        "CBOE": OfficialEventProvider(name="Cboe", source="https://www.cboe.com/",
                                      series=["VIX official daily history"]),
    }


def event_available(e: OfficialEvent) -> bool:
    """release 後才可用；未 released 不得視為已發生。"""
    return e.released_at is not None


def event_visible(events: list[OfficialEvent], information_cutoff: datetime) -> list[OfficialEvent]:
    """遵守 information_cutoff：只回 released_at <= cutoff 的事件。"""
    c = information_cutoff if information_cutoff.tzinfo is not None else information_cutoff.replace(tzinfo=timezone.utc)
    out = []
    for e in events:
        if e.released_at is None:
            continue
        r = e.released_at if e.released_at.tzinfo is not None else e.released_at.replace(tzinfo=timezone.utc)
        if r <= c:
            out.append(e)
    return out


class EventStore:
    def __init__(self, root: Path | None = None) -> None:
        # data_root 是 runtime 可覆寫的資料根；固定 project_root 會與
        # capability_registry 的 dated_event_store_ready 檢查不一致。
        self.root = root or data_root()
        self.dir = self.root / "events"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.dir / "events.duckdb"

    def _conn(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self.db_path))

    def init(self) -> None:
        with self._conn() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    event_name VARCHAR, scheduled_at TIMESTAMP, released_at TIMESTAMP,
                    source VARCHAR, importance_class VARCHAR, available_at TIMESTAMP
                )
                """
            )

    def save(self, e: OfficialEvent) -> None:
        self.init()
        avail = e.available_at or e.released_at
        with self._conn() as con:
            con.execute(
                "INSERT INTO events VALUES (?,?,?,?,?,?)",
                [e.event_name, _naive(e.scheduled_at), _naive(e.released_at) if e.released_at else None,
                 e.source, e.importance_class, _naive(avail) if avail else None],
            )

    def replace_scheduled(self, events: list[OfficialEvent]) -> int:
        """以新的未發布(scheduled)事件取代舊的 scheduled 列；已發布(released)歷史保留。"""
        self.init()
        with self._conn() as con:
            con.execute("DELETE FROM events WHERE released_at IS NULL")
        count = 0
        for e in events:
            if e.released_at is None:
                self.save(e)
                count += 1
        return count

    def replace_scheduled_for(self, source: str, events: list[OfficialEvent]) -> int:
        """只取代單一來源的 scheduled 列。

        來源階層 fail-honest：某來源本次抓取失敗時，其他來源的最後已知列
        不會被連帶清除（calendar 資料寧可舊、不可無）。
        """
        self.init()
        with self._conn() as con:
            con.execute("DELETE FROM events WHERE released_at IS NULL AND source = ?", [source])
        count = 0
        for e in events:
            if e.released_at is None and (e.source or "") == source:
                self.save(e)
                count += 1
        return count

    def upcoming(self, top_n: int = 10) -> list[OfficialEvent]:
        """最接近現在、尚未發布的事件；store 不可用時回空清單（fail-soft）。"""
        try:
            with self._conn() as con:
                rows = con.execute(
                    "SELECT event_name, scheduled_at, source, importance_class"
                    " FROM events WHERE released_at IS NULL"
                    " ORDER BY scheduled_at LIMIT ?",
                    [top_n],
                ).fetchall()
        except Exception:
            return []
        out = []
        for r in rows:
            try:
                out.append(
                    OfficialEvent(
                        event_name=str(r[0]),
                        scheduled_at=_utc(r[1]),
                        source=str(r[2] or ""),
                        importance_class=str(r[3] or ""),
                    )
                )
            except Exception:
                continue
        return out


def _naive(dt: datetime) -> datetime:
    t = pd.Timestamp(dt)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    else:
        t = t.tz_convert("UTC")
    return t.tz_localize(None).to_pydatetime()


def _utc(dt: datetime | None) -> datetime:
    """已存值為 naive-UTC（見 _naive）；還原為 tz-aware UTC。"""
    return pd.Timestamp(dt).tz_localize("UTC").to_pydatetime()
