"""Phase 2Y-A / 2Y-G.2 — YuantaInstrumentResolver（只從 FunctionList/vendor docs 解析，不猜 ticker）。

禁止假設 TradingView ticker / JPX product code / SPARK StkCode 三者相同。

權威來源：最新版 `vendor/yuanta_spark/*/YuantaSparkAPI_win-x64_Python/IO_Doc/FunctionList.xlsx`
「股票代碼總表」（欄位：市場別 | 市場代碼 | 商品代碼(報價StkCode) | 商品名稱 | 下單代碼），
輔以 `config/yuanta_product_codes.yaml`。

已實證（FunctionList, OSE=207）：
- OSE Micro 報價碼 = `JNU<YYMM>`（如 JNU2612）；下單代碼 = JNU（**兩者不同**）
- OSE Mini  報價碼 = `19<YYMM>`；Large = `18<YYMM>`
- TAIFEX（市場代碼 3）TX/MTX/TMF 報價碼 = `TXF<M><Y>` / `MXF<M><Y>` / `TMF<M><Y>`（M=A-L 月、Y=年末位）

合約選擇：不 hardcode 已到期月份；由 as-of 日期以各市場到期規則挑「目前有效且最近」合約。
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

from market_ai_hub.integrations.yuanta.contracts import MARKET_TYPE, OSE_MARKET_TYPE, YuantaInstrument

# 從 FunctionList.xlsx「股票代碼總表」實測確認的海外期貨 code（非猜測）
VERIFIED_FROM_FUNCTIONLIST = {
    # SGX (202) 日經相關
    "SGX_NIKKEI_225": YuantaInstrument(logical_instrument="SGX_NIKKEI_225", market_type=202,
                                       spark_code="NKN", display_name="日經225期貨(SGX)",
                                       source="FunctionList.xlsx", verified=True, verified_at="2026-09-19"),
    "SGX_NIKKEI_MINI": YuantaInstrument(logical_instrument="SGX_NIKKEI_MINI", market_type=202,
                                        spark_code="SNS", display_name="微型日經(SGX)",
                                        source="FunctionList.xlsx", verified=True, verified_at="2026-09-19"),
    # CME (203) 日經相關
    "CME_NIKKEI_MICRO": YuantaInstrument(logical_instrument="CME_NIKKEI_MICRO", market_type=203,
                                         spark_code="MNIK", display_name="微型日經(CME)",
                                         source="FunctionList.xlsx", verified=True, verified_at="2026-09-19"),
    "CME_NIKKEI_USD": YuantaInstrument(logical_instrument="CME_NIKKEI_USD", market_type=203,
                                       spark_code="NIY", display_name="日經225(CME USD)",
                                       source="FunctionList.xlsx", verified=True, verified_at="2026-09-19"),
    "CME_NIKKEI_JPY": YuantaInstrument(logical_instrument="CME_NIKKEI_JPY", market_type=203,
                                       spark_code="NK", display_name="日經225(CME JPY)",
                                       source="FunctionList.xlsx", verified=True, verified_at="2026-09-19"),
}

# contract-specific 報價碼 pattern（yyyy 為 YY、month 為 MM 或月字母）
OSE_QUOTE_CODE_PATTERNS = {
    "OSE_NIKKEI225_MICRO_FUTURES": r"^JNU(\d{2})(\d{2})$",
    "OSE_NIKKEI225_MINI_FUTURES": r"^19(\d{2})(\d{2})$",
    "OSE_NIKKEI225_LARGE_FUTURES": r"^18(\d{2})(\d{2})$",
}
OSE_ORDER_CODES = {
    "OSE_NIKKEI225_MICRO_FUTURES": "JNU",
    "OSE_NIKKEI225_MINI_FUTURES": "JNM",
    "OSE_NIKKEI225_LARGE_FUTURES": "JNI",
}
OSE_DISPLAY_NAMES = {
    "OSE_NIKKEI225_MICRO_FUTURES": "大阪微日經期貨",
    "OSE_NIKKEI225_MINI_FUTURES": "大阪小日經期貨",
    "OSE_NIKKEI225_LARGE_FUTURES": "大阪日經期貨",
}

# TAIFEX (3) 國內指數期貨報價碼（月字母 A-L，年末位）
TAIFEX_QUOTE_CODE_PATTERNS = {
    "TAIFEX_TX": r"^TXF([A-L])(\d)$",
    "TAIFEX_MTX": r"^MXF([A-L])(\d)$",
    "TAIFEX_TMF": r"^TMF([A-L])(\d)$",
}
TAIFEX_ORDER_CODES = {"TAIFEX_TX": "TX", "TAIFEX_MTX": "MTX", "TAIFEX_TMF": "TMF"}
TAIFEX_DISPLAY_NAMES = {"TAIFEX_TX": "台指期", "TAIFEX_MTX": "小台指", "TAIFEX_TMF": "微台指"}
TAIFEX_MARKET_TYPE = 3

_MONTH_LETTERS = "ABCDEFGHIJKL"


# ── expiry rules (documented exchange rules, used only for contract selection) ──
def _business_day_on_or_before(d: date) -> date:
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def ose_last_trading_date(year: int, month: int) -> date:
    """OSE Nikkei 225 futures last trading day ≈ business day preceding the second Friday."""
    first = date(year, month, 1)
    first_friday = first + timedelta(days=(4 - first.weekday()) % 7)
    return _business_day_on_or_before(first_friday + timedelta(days=7) - timedelta(days=1))


def taifex_last_trading_date(year: int, month: int) -> date:
    """TAIFEX monthly index futures last trading day = third Wednesday of the contract month."""
    first = date(year, month, 1)
    first_wednesday = first + timedelta(days=(2 - first.weekday()) % 7)
    return first_wednesday + timedelta(days=14)


def select_nearest_valid(codes, pattern: str, last_trading_date_fn, asof: date | None = None) -> str | None:
    """Nearest contract whose last trading day >= asof. Never hardcodes an expired month."""
    asof = asof or date.today()
    best: tuple[int, int, str] | None = None
    for c in codes:
        m = re.fullmatch(pattern, c or "")
        if not m:
            continue
        g1, g2 = m.group(1), m.group(2)
        if g1.isdigit() and g2.isdigit():
            year, month = 2000 + int(g1), int(g2)
        else:  # TAIFEX letter-month + year digit
            month = _MONTH_LETTERS.index(g1.upper()) + 1
            year = 2020 + int(g2)
        if not (1 <= month <= 12):
            continue
        if last_trading_date_fn(year, month) >= asof:
            key = (year, month, c)
            if best is None or key < best:
                best = key
    return best[2] if best else None


# ── authoritative source loading ──
def function_list_path() -> Path | None:
    """Locate the newest vendor FunctionList.xlsx (read-only)."""
    root = Path(__file__).resolve().parents[4] / "vendor" / "yuanta_spark"
    if not root.exists():
        return None
    cands = sorted(root.glob("*/YuantaSparkAPI_*/IO_Doc/FunctionList.xlsx"))
    return cands[-1] if cands else None


def load_ose_quote_codes(xlsx_path: str | Path | None = None) -> list[str]:
    """OSE (207) 商品代碼（報價 StkCode）list；來源不可用時回 []（不猜）。"""
    from market_ai_hub.integrations.yuanta.function_list import load_stock_code_rows

    p = xlsx_path or function_list_path()
    if p is None:
        return []
    try:
        rows = load_stock_code_rows(p)
    except Exception:
        return []
    return sorted({r["code"] for r in rows if r["market_code"] == OSE_MARKET_TYPE and r["code"]})


def load_taifex_quote_codes(xlsx_path: str | Path | None = None) -> list[str]:
    from market_ai_hub.integrations.yuanta.function_list import load_stock_code_rows

    p = xlsx_path or function_list_path()
    if p is None:
        return []
    try:
        rows = load_stock_code_rows(p)
    except Exception:
        return []
    return sorted({r["code"] for r in rows if r["market_code"] == TAIFEX_MARKET_TYPE and r["code"]})


class YuantaInstrumentResolver:
    def resolve(self, logical_instrument: str, asof: date | None = None) -> YuantaInstrument:
        if logical_instrument in VERIFIED_FROM_FUNCTIONLIST:
            return VERIFIED_FROM_FUNCTIONLIST[logical_instrument]
        if logical_instrument in OSE_QUOTE_CODE_PATTERNS:
            return self._resolve_ose(logical_instrument, asof)
        if logical_instrument in TAIFEX_QUOTE_CODE_PATTERNS:
            return self._resolve_taifex(logical_instrument, asof)
        return YuantaInstrument(logical_instrument=logical_instrument, verified=False)

    def _resolve_ose(self, logical_instrument: str, asof: date | None) -> YuantaInstrument:
        p = function_list_path()
        codes = load_ose_quote_codes(p)
        code = select_nearest_valid(codes, OSE_QUOTE_CODE_PATTERNS[logical_instrument],
                                    ose_last_trading_date, asof)
        if not code:
            # FunctionList unavailable / no valid contract -> fail closed (never guess a month)
            return YuantaInstrument(
                logical_instrument=logical_instrument, market_type=OSE_MARKET_TYPE,
                spark_code="", display_name=OSE_DISPLAY_NAMES.get(logical_instrument, ""),
                source="FunctionList.xlsx (NO VALID CONTRACT FOUND)", verified=False,
            )
        return YuantaInstrument(
            logical_instrument=logical_instrument, market_type=OSE_MARKET_TYPE,
            spark_code=code, display_name=OSE_DISPLAY_NAMES.get(logical_instrument, ""),
            source=f"FunctionList.xlsx 股票代碼總表 (OSE 207) @ {p.parent.parent.name}" if p else "FunctionList.xlsx",
            verified=True, verified_at=date.today().isoformat(),
        )

    def _resolve_taifex(self, logical_instrument: str, asof: date | None) -> YuantaInstrument:
        p = function_list_path()
        codes = load_taifex_quote_codes(p)
        code = select_nearest_valid(codes, TAIFEX_QUOTE_CODE_PATTERNS[logical_instrument],
                                    taifex_last_trading_date, asof)
        if not code:
            return YuantaInstrument(
                logical_instrument=logical_instrument, market_type=TAIFEX_MARKET_TYPE,
                spark_code="", display_name=TAIFEX_DISPLAY_NAMES.get(logical_instrument, ""),
                source="FunctionList.xlsx (NO VALID CONTRACT FOUND)", verified=False,
            )
        return YuantaInstrument(
            logical_instrument=logical_instrument, market_type=TAIFEX_MARKET_TYPE,
            spark_code=code, display_name=TAIFEX_DISPLAY_NAMES.get(logical_instrument, ""),
            source="FunctionList.xlsx 股票代碼總表 (TAIFEX 3)", verified=True,
            verified_at=date.today().isoformat(),
        )

    def order_code(self, logical_instrument: str) -> str:
        """下單代碼（≠ 報價 StkCode）。"""
        return OSE_ORDER_CODES.get(logical_instrument) or TAIFEX_ORDER_CODES.get(logical_instrument, "")

    def ose_market_type(self) -> int:
        return OSE_MARKET_TYPE

    def market_enum(self) -> dict:
        return dict(MARKET_TYPE)
