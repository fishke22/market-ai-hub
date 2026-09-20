"""Phase 2Y-A — FunctionList.xlsx parser（唯讀，只解析市場 enum + 海外期貨 code）。"""
from __future__ import annotations

from pathlib import Path


def parse_market_enum(xlsx_path: str | Path) -> dict[str, int]:
    """讀 FunctionList 市場類 sheet → {market_name: code}（含 OSE=207）。"""
    import openpyxl

    wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)
    ws = None
    for sn in wb.sheetnames:
        cand = wb[sn]
        first = next(cand.iter_rows(values_only=True), None)
        cells = [str(c) for c in (first or []) if c is not None]
        joined = " ".join(cells)
        if "市場" in joined and "代碼" in joined:
            ws = cand
            break
    out: dict[str, int] = {}
    if ws is None:
        return out
    for row in ws.iter_rows(values_only=True):
        vals = ["" if c is None else str(c).strip() for c in row]
        if len(vals) < 2:
            continue
        code = vals[0]
        name = vals[1]
        if code.isdigit():
            out[name] = int(code)
    return out


def find_overseas_futures(xlsx_path: str | Path) -> list[dict]:
    """讀股票代碼總表，回海外期貨（SGX/CME/OSE）列。"""
    import openpyxl

    wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)
    ws = None
    for sn in wb.sheetnames:
        cand = wb[sn]
        first = next(cand.iter_rows(values_only=True), None)
        cells = [str(c) for c in (first or []) if c is not None]
        joined = " ".join(cells)
        if "商品代碼" in joined and "市場" in joined:
            ws = cand
            break
    out: list[dict] = []
    if ws is None:
        return out
    for row in ws.iter_rows(values_only=True):
        vals = ["" if c is None else str(c).strip() for c in row]
        if len(vals) < 3:
            continue
        mk, mc = vals[0], vals[1]
        if mc in ("202", "203", "207"):
            out.append({"market": mk, "market_code": int(mc), "code": vals[2], "name": vals[3]})
    return out
