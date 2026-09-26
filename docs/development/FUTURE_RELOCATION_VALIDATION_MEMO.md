# Future Relocation Validation Memo

Status: DESIGN_RESERVED / NOT_A_CURRENT_OPERATIONAL_BLOCKER
Recorded: 2026-09-26

The user is not relocating MARKET_AI_HUB now. Current financial analysis and the live quote runtime must not be blocked by relocation-only acceptance cells.

Keep the existing relocation-safe design: project_root/runtime_paths, MARKET_AI_DATA_ROOT, regenerated venv, generated MCP client config, task/startup rebinding, and no plaintext credentials.

When an actual move is authorized, re-run these external cells on the destination machine:
- clean new Windows bootstrap and full fresh dependency install;
- Windows Credential Manager recreation without copying plaintext secrets;
- Yuanta certificate import and signature verification;
- proprietary Yuanta OCX/COM registration and quote-only smoke;
- CherryStudio market-ai MCP path regeneration and health_check;
- Scheduled Task/startup rebinding;
- backup restore verification for DuckDB/SQLite/Parquet;
- path tests from arbitrary cwd and paths containing spaces/CJK.

Do not copy .venv, WinCred, COM registration, or certificates and call that portable.
Do not weaken TLS, gates, quote-only rules, or secret handling to make relocation pass.
Until relocation is actually requested, report these cells as UNVERIFIED_EXTERNAL_GATE / DEFERRED_BY_USER and continue normal research with the current verified machine.
