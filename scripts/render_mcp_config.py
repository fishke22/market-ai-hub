from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TEMPLATES = {
    "generic": ROOT / "examples" / "mcp" / "generic-stdio.json",
    "cherry": ROOT / "examples" / "mcp" / "cherry-studio.json",
}


def render(client: str, project_root: Path) -> dict:
    template = TEMPLATES[client]
    payload = json.loads(template.read_text(encoding="utf-8"))
    server = payload["mcpServers"]["market-ai"]
    exe = "market-ai-mcp.exe" if os.name == "nt" else "market-ai-mcp"
    server["command"] = str(project_root / ".venv" / ("Scripts" if os.name == "nt" else "bin") / exe)
    server["args"] = []
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Render relocation-safe MARKET_AI_HUB MCP client config")
    parser.add_argument("--client", choices=sorted(TEMPLATES), default="generic")
    parser.add_argument("--project-root", default=str(ROOT))
    parser.add_argument("--output")
    parser.add_argument("--require-command", action="store_true")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    payload = render(args.client, project_root)
    command = Path(payload["mcpServers"]["market-ai"]["command"])
    if args.require_command and not command.is_file():
        raise SystemExit(f"MCP command not found: {command}")

    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        print(f"MCP_CONFIG_WRITTEN={output}")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
