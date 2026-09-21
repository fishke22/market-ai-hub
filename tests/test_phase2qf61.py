"""Phase 2Q-F.6.1 — credential UX closure + WinCred resolver tests（fake backend，無真實 credential）。"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, "src")
ROOT = Path(__file__).resolve().parents[1]


def _load_setup():
    spec = importlib.util.spec_from_file_location(
        "setup_api_credentials", ROOT / "scripts" / "setup_api_credentials.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeBackend:
    def __init__(self, configured=()):
        self.store = {k: "FAKE" for k in configured}
        self.set_calls = []
        self.delete_calls = []

    def secret_status(self, name):
        if name in self.store:
            return {"name": name, "configured": True, "source": "WINCRED"}
        return {"name": name, "configured": False, "source": "NONE"}

    def set_secret(self, name, value):
        self.set_calls.append(name)
        self.store[name] = value
        return True

    def delete_secret(self, name):
        self.delete_calls.append(name)
        self.store.pop(name, None)
        return True

    def has_wincred(self):
        return True


def _run(monkeypatch, backend, argv, inputs=()):
    import market_ai_hub.services.secret_store as ss

    mod = _load_setup()
    for fn in ("secret_status", "set_secret", "delete_secret", "has_wincred"):
        monkeypatch.setattr(ss, fn, getattr(backend, fn))
    prompts = []

    def _fake_getpass(prompt=""):
        prompts.append(prompt)
        return inputs[len(prompts) - 1] if len(prompts) <= len(inputs) else ""

    monkeypatch.setattr(mod.getpass, "getpass", _fake_getpass)
    monkeypatch.setattr(sys, "argv", ["setup_api_credentials.py", *argv])
    rc = mod.main()
    return rc, prompts, backend


# ── §3：default UX Case A/B/C/D ──

def test_setup_both_missing_prompts_both(monkeypatch, capsys):
    rc, prompts, b = _run(monkeypatch, FakeBackend(), [], inputs=("fredkey", "fmtoken"))
    out = capsys.readouterr().out
    assert len(prompts) == 2
    assert prompts[0].startswith("FRED API key")
    assert prompts[1].startswith("FinMind API token")
    assert "FRED_API_KEY = CONFIGURED" in out
    assert "FINMIND_API_TOKEN = CONFIGURED" in out


def test_setup_fred_exists_prompts_finmind_only(monkeypatch, capsys):
    rc, prompts, b = _run(monkeypatch, FakeBackend(("FRED_API_KEY",)), [], inputs=("fmtoken",))
    out = capsys.readouterr().out
    assert len(prompts) == 1
    assert prompts[0].startswith("FinMind API token")
    assert "FRED_API_KEY = ALREADY_CONFIGURED" in out
    assert "FINMIND_API_TOKEN = CONFIGURED" in out


def test_setup_finmind_exists_prompts_fred_only(monkeypatch, capsys):
    rc, prompts, b = _run(monkeypatch, FakeBackend(("FINMIND_API_TOKEN",)), [], inputs=("fredkey",))
    out = capsys.readouterr().out
    assert len(prompts) == 1
    assert prompts[0].startswith("FRED API key")
    assert "FINMIND_API_TOKEN = ALREADY_CONFIGURED" in out
    assert "FRED_API_KEY = CONFIGURED" in out


def test_setup_both_exist_prompts_none(monkeypatch, capsys):
    rc, prompts, b = _run(monkeypatch, FakeBackend(("FRED_API_KEY", "FINMIND_API_TOKEN")), [])
    out = capsys.readouterr().out
    assert prompts == []
    assert "FRED_API_KEY = ALREADY_CONFIGURED" in out
    assert "FINMIND_API_TOKEN = ALREADY_CONFIGURED" in out


# ── §4：--status no secret ──

def test_status_no_secret_output(monkeypatch, capsys):
    rc, prompts, b = _run(monkeypatch, FakeBackend(("FRED_API_KEY",)), ["--status"])
    out = capsys.readouterr().out
    assert "FRED_API_KEY = CONFIGURED" in out
    assert "FINMIND_API_TOKEN = NOT_CONFIGURED" in out
    assert "FAKE" not in out  # 不得輸出 value
    assert prompts == []


# ── §5：--replace ──

def test_replace_fred(monkeypatch, capsys):
    rc, prompts, b = _run(monkeypatch, FakeBackend(("FRED_API_KEY", "FINMIND_API_TOKEN")), ["--replace", "fred"], inputs=("newfred",))
    assert len(prompts) == 1
    assert prompts[0].startswith("FRED API key")
    assert "FRED_API_KEY = CONFIGURED" in capsys.readouterr().out
    assert b.set_calls == ["FRED_API_KEY"]


def test_replace_finmind(monkeypatch, capsys):
    rc, prompts, b = _run(monkeypatch, FakeBackend(("FRED_API_KEY", "FINMIND_API_TOKEN")), ["--replace", "finmind"], inputs=("newfm",))
    assert len(prompts) == 1
    assert prompts[0].startswith("FinMind API token")
    assert b.set_calls == ["FINMIND_API_TOKEN"]


# ── §6：delete only MARKET_AI_HUB targets ──

def test_delete_only_market_ai_targets(monkeypatch, capsys):
    rc, prompts, b = _run(monkeypatch, FakeBackend(("FRED_API_KEY", "FINMIND_API_TOKEN")), ["--delete", "fred"])
    assert b.delete_calls == ["FRED_API_KEY"]
    assert "FRED_API_KEY = DELETED" in capsys.readouterr().out


def test_does_not_touch_qros_credentials(monkeypatch):
    rc, prompts, b = _run(monkeypatch, FakeBackend(("FRED_API_KEY", "FINMIND_API_TOKEN")), ["--delete", "finmind"])
    # 只允許 canonical targets；不得出現任何 QROS/*
    for name in b.delete_calls:
        assert name in ("FRED_API_KEY", "FINMIND_API_TOKEN")
        assert "QROS" not in name


def test_does_not_touch_yuanta_credentials(monkeypatch):
    rc, prompts, b = _run(monkeypatch, FakeBackend(("FRED_API_KEY",)), [])
    for name in b.set_calls:
        assert "YUANTA" not in name
        assert name in ("FRED_API_KEY", "FINMIND_API_TOKEN")


# ── §7：central resolver ──

def test_secret_resolver_wincred_preferred(monkeypatch):
    import market_ai_hub.services.secret_store as ss

    monkeypatch.setattr(ss, "_wincred_get", lambda n: "wincredval")
    monkeypatch.setenv("FRED_API_KEY", "envval")
    assert ss.get_secret("FRED_API_KEY") == "wincredval"  # WinCred 優先


def test_secret_resolver_canonical_targets(monkeypatch):
    import market_ai_hub.services.secret_store as ss

    seen = []
    monkeypatch.setattr(ss, "_wincred_get", lambda n: seen.append(n) or None)
    ss.get_secret("FRED_API_KEY")
    ss.get_secret("FINMIND_TOKEN")  # legacy alias
    assert "FRED_API_KEY" in seen
    assert "FINMIND_API_TOKEN" in seen  # alias resolve 到 canonical


# ── §10：provider shallow configured ──

def test_provider_shallow_configured(monkeypatch):
    import market_ai_hub.providers.fred as fred
    import market_ai_hub.providers.finmind as finmind

    monkeypatch.setattr(fred, "get_secret", lambda n: "x")
    monkeypatch.setattr(finmind, "get_secret", lambda n: "x")
    assert fred.FredProvider().status().status.value == "ok"
    assert finmind.FinMindProvider().status().status.value == "ok"


# ── §14：no secret in logs ──

def test_no_secret_in_logs(monkeypatch, caplog):
    import logging

    import market_ai_hub.services.secret_store as ss

    monkeypatch.setattr(ss, "_wincred_get", lambda n: "TOPSECRET123")
    with caplog.at_level(logging.DEBUG):
        ss.get_secret("FRED_API_KEY")
        ss.secret_status("FRED_API_KEY")
    assert "TOPSECRET123" not in caplog.text
