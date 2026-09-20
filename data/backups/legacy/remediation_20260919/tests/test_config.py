from market_ai_hub.config.settings import load_symbols, project_root


def test_symbols_loaded():
    syms = load_symbols()
    assert len(syms) >= 8
    n225 = next(s for s in syms if s["symbol"] == "^N225")
    assert n225["data_grade"] == "RESEARCH_PROXY"
    # 禁止把 ^N225 標成 OSE micro futures
    assert "OSE_MICRO_FUTURES" not in str(n225)


def test_all_symbols_have_required_fields():
    for s in load_symbols():
        for field in ("name", "provider", "timezone", "asset_type", "realtime_grade", "enabled"):
            assert field in s, f"{s['symbol']} missing {field}"


def test_project_root():
    assert (project_root() / "src" / "market_ai_hub").exists()
