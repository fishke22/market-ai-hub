"""Phase 2Y-G.3 — Legacy EASYWIN quote-symbol resolver（read-only）。

**三個 namespace 不得互換**：
- `SPARK`                ：SPARK StkCode（FunctionList / SPARK quote），由 `resolver.py` 負責
- `LEGACY_EASYWIN`       ：EasyWin/YesWin 報價商品代碼（本模組）
- `TRADING_ORDER`        ：下單代碼（e.g. TMF / JNU / FITM 202610），非報價碼

來源（唯讀，cp950 CSV）：
  <yeswin>\\AGENT\\YSTrader\\Data\\List\\M.<MARKET>.TXT
  實際內容含 `TMFJ6 / TMFJ6PM / TXFJ6 / TXFJ6PM / MXFJ6 / MXFJ6PM`。

本模組不登入、不訂閱、不寫檔；只管 legacy 商品碼的解析與 day/PM 分離。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, asdict
from datetime import date, datetime
from pathlib import Path

NAMESPACE_SPARK = "SPARK"
NAMESPACE_LEGACY_EASYWIN = "LEGACY_EASYWIN"
NAMESPACE_TRADING_ORDER = "TRADING_ORDER"

DEFAULT_LIST_DIR = Path(os.environ.get(
    "YUANTA_EASWIN_LIST_DIR", r"C:\Yuanta\yeswin\AGENT\YSTrader\Data\List"))
MARKET_FILES = {"TAIFEX": "M.TFX.TXT"}

# 國內指數期貨：TMF/TXF/MXF + 月字母(A-L) + 年末位，可帶尾端 PM 後綴（TMFJ6PM）
_INDEX_FUTURE_RE = re.compile(r"^(?P<root>TXF|MXF|TMF)(?P<mon>[A-L])(?P<yr>\d)(?P<pm>PM)?$")
_ALIAS_RE = re.compile(r"^(?P<root>TXF|MXF|TMF)(?P<pm>PM)?1$")

# 下單代碼（≠ 報價碼；由 primary_targets / yuanta_product_codes 為準）→ legacy 商品根
TRADING_ORDER_CODES = {"TX": "TXF", "MTX": "MXF", "TMF": "TMF"}


@dataclass
class EasyWinQuoteSymbol:
    symbol: str = ""
    name: str = ""
    market: str = ""
    expiry: str = ""              # YYYYMMDD（來源檔提供）
    is_pm: bool = False
    underlying_day_symbol: str = ""
    alias_of: str = ""
    namespace: str = NAMESPACE_LEGACY_EASYWIN

    def model_dump(self) -> dict:
        return asdict(self)


class LegacyEasyWinResolver:
    """讀本機 EasyWin 商品清單，解析 legacy 報價商品代碼（day / PM 分離）。"""

    def __init__(self, list_dir: Path | str | None = None) -> None:
        self.list_dir = Path(list_dir) if list_dir else DEFAULT_LIST_DIR
        self._cache: dict[str, list[EasyWinQuoteSymbol]] = {}

    # ── source ──
    def source_path(self, market: str = "TAIFEX") -> Path | None:
        fname = MARKET_FILES.get(market.upper())
        if not fname:
            return None
        p = self.list_dir / fname
        return p if p.exists() else None

    def available(self, market: str = "TAIFEX") -> bool:
        return self.source_path(market) is not None

    def _read_text(self, path: Path) -> str:
        raw = path.read_bytes()
        for enc in ("cp950", "big5", "utf-8"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace")

    def load_market(self, market: str = "TAIFEX") -> list[EasyWinQuoteSymbol]:
        key = market.upper()
        if key in self._cache:
            return self._cache[key]
        p = self.source_path(key)
        if p is None:
            self._cache[key] = []
            return []
        out: list[EasyWinQuoteSymbol] = []
        for line in self._read_text(p).splitlines():
            fields = [f.strip() for f in line.split(",")]
            if len(fields) < 3:
                continue
            sym = fields[0]
            m = _INDEX_FUTURE_RE.fullmatch(sym)
            alias = _ALIAS_RE.fullmatch(sym)
            if m:
                is_pm = bool(m.group("pm"))
                underlying = ""
                if is_pm:
                    cand = fields[7] if len(fields) > 7 else ""
                    underlying = cand if _INDEX_FUTURE_RE.fullmatch(cand) else sym[:-2]
                out.append(EasyWinQuoteSymbol(
                    symbol=sym, name=fields[1], market=key,
                    expiry=fields[5] if len(fields) > 5 and fields[5].isdigit() else "",
                    is_pm=is_pm, underlying_day_symbol=underlying,
                ))
            elif alias:
                out.append(EasyWinQuoteSymbol(
                    symbol=sym, name=fields[1], market=key,
                    is_pm=bool(alias.group("pm")), alias_of=fields[2],
                ))
        self._cache[key] = out
        return out

    # ── queries ──
    def is_legacy_symbol(self, symbol: str, market: str = "TAIFEX") -> bool:
        return any(s.symbol == (symbol or "") for s in self.load_market(market))

    def day_symbols(self, market: str = "TAIFEX") -> list[str]:
        return sorted({s.symbol for s in self.load_market(market) if not s.is_pm and not s.alias_of})

    def pm_symbols(self, market: str = "TAIFEX") -> list[str]:
        return sorted({s.symbol for s in self.load_market(market) if s.is_pm and not s.alias_of})

    def resolve_quote_symbol(self, order_code: str, session: str = "T",
                             asof: date | None = None, market: str = "TAIFEX") -> str | None:
        """下單商品根（TX/MTX/TMF）+ session → legacy 報價商品代碼。

        session `T` → day 合約；`T+1` / `PM` → 盤後（PM）合約。
        以來源檔的 expiry 欄挑「目前有效且最近」合約；不 hardcode 月份。
        """
        root = (order_code or "").upper().strip()
        if root not in TRADING_ORDER_CODES:
            return None
        want_pm = session.upper() in ("T+1", "TPLUS1", "PM", "AFTER_HOURS")
        asof = asof or date.today()
        best: tuple[int, str] | None = None
        for s in self.load_market(market):
            if s.is_pm or s.alias_of:
                continue
            m = _INDEX_FUTURE_RE.fullmatch(s.symbol)
            if not m or m.group("root") != TRADING_ORDER_CODES[root]:
                continue
            if s.expiry:
                try:
                    exp = datetime.strptime(s.expiry, "%Y%m%d").date()
                except ValueError:
                    continue
                if exp < asof:
                    continue
                key = (int(s.expiry), s.symbol)
            else:
                key = (0, s.symbol)
            if best is None or key < best:
                best = key
        if best is None:
            return None
        return best[1] + "PM" if want_pm else best[1]

    def namespaces(self) -> dict:
        return {"SPARK": NAMESPACE_SPARK, "LEGACY_EASYWIN": NAMESPACE_LEGACY_EASYWIN,
                "TRADING_ORDER": NAMESPACE_TRADING_ORDER}
