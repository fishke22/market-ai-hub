"""Phase 2H.2 — durable agent handoff contract + legacy canonical API symbol tests."""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, "src")

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "AGENTS.md"
HANDOFF = ROOT / "docs" / "development" / "AGENT_HANDOFF.md"
BOOTSTRAP = ROOT / "scripts" / "agent_bootstrap.ps1"


def _resolve_or_skip():
    from market_ai_hub.integrations.yuanta.easwin_resolver import LegacyEasyWinResolver

    r = LegacyEasyWinResolver()
    if not r.available():
        pytest.skip("EasyWin M.TFX.TXT not present on this machine")
    return r


# ── AGENTS.md / handoff / bootstrap ──
def test_agents_md_exists_and_is_short():
    assert AGENTS.is_file()
    text = AGENTS.read_text(encoding="utf-8")
    assert len(text.splitlines()) <= 40          # stays short
    for rule in ("agent_bootstrap.ps1", "AGENT_HANDOFF.md", "project-status.md",
                 "CLOSED/PASS", "provider", "ENGINE PASS"):
        assert rule in text, rule


def test_agent_handoff_exists_and_covers_required_facts():
    assert HANDOFF.is_file()
    text = HANDOFF.read_text(encoding="utf-8")
    assert "SECURITIES API" in text
    assert "FUTURES QUOTE API" in text
    assert "FUTURES TRADING API" in text
    assert "YuantaOrd" in text and "YuantaQuote" in text
    assert "Yuanta futures unavailable != system blocked" in text
    assert "cash and futures identities stay separate forever" in text
    assert "V2-I" in text and "NOT STARTED" in text
    assert "CALIBRATED is FORBIDDEN" in text or "CALIBRATED" in text


def test_handoff_three_api_families_are_distinct():
    text = HANDOFF.read_text(encoding="utf-8")
    # SPARK must not be presented as the futures quote provider
    assert "Never re-promote SPARK as the official futures quote provider" in text
    assert "NOT connected to runtime" in text and "NO ORDER" in text


def test_bootstrap_is_read_only_and_prints_actual_state():
    assert BOOTSTRAP.is_file()
    text = BOOTSTRAP.read_text(encoding="utf-8")
    # no mutating git / fs verbs
    for forbidden in ("git checkout", "git reset", "git clean", "git pull", "git fetch",
                      "Set-Content", "Remove-Item", "Out-File", "New-Item"):
        assert forbidden not in text, forbidden
    for must in ("rev-parse HEAD", "origin/main", "git status --short", "build_id",
                 "v2_schema_versions", "PROVIDER_STATUS"):
        assert must in text, must


def test_bootstrap_never_reads_secrets():
    text = BOOTSTRAP.read_text(encoding="utf-8")
    for token in ("win32cred", "CredRead", "CredentialBlob", "getpass", "credential_store",
                  "api_key", "API_KEY", "PASSWORD"):
        assert token not in text, token
    # the only env var it may set is PYTHONPATH for the read-only python probe
    env_sets = re.findall(r"\$env:([A-Za-z_]+)\s*=", text)
    assert env_sets == ["PYTHONPATH"]


# ── legacy canonical API symbol ──
def test_legacy_quote_tplus1_canonical_symbol_is_base_symbol():
    r = _resolve_or_skip()
    base = r.resolve_quote_symbol("TMF", "T", asof=date(2026, 9, 24))
    t1 = r.resolve_quote_symbol("TMF", "T+1", asof=date(2026, 9, 24))
    assert t1 == base
    assert not t1.endswith("PM")
    assert r.resolve_api_symbol("TMF", "T+1", asof=date(2026, 9, 24)) == (base, 2)


def test_pm_alias_not_used_in_addmktreg_canonical_path():
    r = _resolve_or_skip()
    for session in ("T", "T+1", "TPLUS1"):
        api = r.resolve_api_symbol("TMF", session, asof=date(2026, 9, 24))
        assert api is not None
        symbol, req_type = api
        assert not symbol.endswith("PM"), (session, symbol)
        assert req_type in (1, 2)


def test_legacy_req_type_and_update_mode_are_official_defaults():
    from market_ai_hub.integrations.yuanta.easwin_resolver import (
        LEGACY_REQ_TYPES, LEGACY_SET_MAP_DEFAULT, LEGACY_UPDATE_MODE_DEFAULT,
    )

    assert LEGACY_REQ_TYPES["T"] == 1 and LEGACY_REQ_TYPES["TPLUS1"] == 2
    assert LEGACY_UPDATE_MODE_DEFAULT == "4"      # 4-SnapshotUpd (official sample)
    assert LEGACY_SET_MAP_DEFAULT == 0


def test_legacy_quote_probe_uses_session_reqtype_and_official_update_mode():
    src = (ROOT / "src" / "market_ai_hub" / "integrations" / "yuanta"
           / "futures_quote_probe.py").read_text(encoding="utf-8")
    assert "LEGACY_UPDATE_MODE_DEFAULT" in src
    assert "LEGACY_SET_MAP_DEFAULT" in src
    assert "register_quote_symbol(args.symbol, update_mode, req_type)" in src
    assert not re.search(r"register_quote_symbol\(args\.symbol, \"1\"", src)
