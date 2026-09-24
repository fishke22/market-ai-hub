"""Phase 2Z — release acceptance tests（provider metrics / skill contract / OSE semantics）。"""
import sys
from pathlib import Path

sys.path.insert(0, "src")

ROOT = Path(__file__).resolve().parents[1]


# --- provider metrics（item 14/15）---
def test_provider_metrics_records_logical_request():
    from market_ai_hub.services.provider_metrics import ProviderMetrics

    m = ProviderMetrics()
    m.record("yfinance", "regime_panel", cache_hit=False, success=True, duration_ms=100)
    m.record("yfinance", "regime_panel", cache_hit=True, success=True, duration_ms=1)
    s = m.summary("yfinance")
    assert s["logical_calls"] == 2
    assert s["cache_misses"] == 1
    assert s["cache_hits"] == 1


def test_provider_metrics_no_socket_monkeypatch():
    from market_ai_hub.services.provider_metrics import get_provider_metrics

    # 不靠 monkey patch；provider wrapper 記錄 logical request
    m = get_provider_metrics()
    m.reset()
    m.record("test", "op", cache_hit=False, success=True, duration_ms=0)
    assert m.logical_calls("test") == 1


def test_request_dedup_validation(tmp_path, monkeypatch):
    # cold vs warm：settlement 載入 cache hit 記錄
    import pandas as pd
    from market_ai_hub.automation.incremental import atomic_write
    from market_ai_hub.packet import builder as b
    from market_ai_hub.services.provider_metrics import get_provider_metrics

    root = tmp_path / "data"
    dest = root / "raw" / "jpx" / "settlement" / "OSE" / "all" / "2026" / "09"
    dest.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([{"product": "Nikkei 225 Micro Futures", "contract": "202612",
                        "settlement_price": 65100.0, "date": "20260918"}])
    atomic_write(dest / "rb20260918.parquet", df.to_parquet(index=False))
    monkeypatch.setenv("MARKET_AI_DATA_ROOT", str(root))

    get_provider_metrics().reset()
    b.clear_caches()
    a = b._load_latest_micro_settlement()   # cold → cache_miss
    c = b._load_latest_micro_settlement()   # warm → cache_hit
    assert a == c
    s = get_provider_metrics().summary("jpx_settlement")
    assert s["cache_misses"] == 1
    assert s["cache_hits"] == 1


# --- OSE target semantics（item 9）---
def test_n225_not_primary_target():
    from market_ai_hub.targets.contract import EXECUTION_TARGET, role_of

    assert EXECUTION_TARGET == "OSE_NIKKEI225_MICRO_FUTURES"
    assert role_of("^N225") != "TARGET"


def test_settlement_not_realtime_close():
    # 全 repo 不得把 settlement 說成 realtime close（不查 docs 文字，只查 code 語義）
    from market_ai_hub.targets.jpx_settlement import parse_settlement_csv
    rows = parse_settlement_csv(
        "銘柄コード,銘柄名称,PUT/CAL,限月,権利行使価格,清算価格,理論価格,原資産価格,ボラティリティ,金利,残日数,原資産名称\n"
        "1,FUT_225MC_261210,,202612,,65055,65055,65018.95,,1.6,84,日経225\n".encode("shift_jis"))
    assert rows[0].settlement_price == 65055.0


# --- skills（item 8）---
def test_skill_runtime_contract():
    import asyncio
    from market_ai_hub.mcp.server import mcp

    tools = {t.name for t in asyncio.run(mcp.list_tools())}
    for name in ("osaka-micro-analysis", "taiwan-stock-v28", "model-validation-audit"):
        txt = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        # 每個提到的 get_*/analyze_* 工具必須存在
        import re
        mentioned = set(re.findall(r"`(get_\w+|analyze_\w+|predict_\w+|health_\w+)`", txt))
        for m in mentioned:
            assert m in tools, f"{name} references missing MCP tool {m}"


def test_skill_no_credential_reference():
    for name in ("osaka-micro-analysis", "taiwan-stock-v28", "model-validation-audit"):
        txt = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        for kw in ("password", "密碼", "credential", "token", "API key"):
            assert kw not in txt, f"{name} references credential"


# --- MCP security（item 7）---
def test_mcp_no_order_or_credential_tools():
    import asyncio
    from market_ai_hub.mcp.server import mcp

    tools = [t.name for t in asyncio.run(mcp.list_tools())]
    for t in tools:
        tl = t.lower()
        assert not any(k in tl for k in ("order", "cancel", "modify", "login", "credential", "broker")), t


def test_mcp_tool_count_is_21():
    import asyncio
    from market_ai_hub.mcp.server import mcp

    assert len(asyncio.run(mcp.list_tools())) == 21
