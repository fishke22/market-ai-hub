"""Config loader: .env (secrets) + config/symbols.yaml (symbols) + 路徑。"""
from __future__ import annotations

from pathlib import Path

import yaml
from dotenv import load_dotenv
import os


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def load_env() -> None:
    load_dotenv(project_root() / ".env")


def get_secret(name: str) -> str:
    load_env()
    return os.environ.get(name, "") or ""


def load_symbols() -> list[dict]:
    p = project_root() / "config" / "symbols.yaml"
    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return [s for s in data["symbols"] if s.get("enabled", True)]
