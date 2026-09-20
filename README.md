# MARKET_AI_HUB

A local, research-only financial market analysis backend for AI clients. It exposes market data,
forecasting, validation, and research evidence through a standard [MCP](https://modelcontextprotocol.io)
stdio server, so an AI client or agent can run a local Python research pipeline instead of guessing.

**This is a research system, not an automated trading system.** It does not log into brokers, place
orders, or hold positions. See [DISCLAIMER.md](DISCLAIMER.md) and [SECURITY.md](SECURITY.md).

Release: `v2.0.0-rc1` (research release candidate). See [CHANGELOG.md](CHANGELOG.md).

---

## Scope

MARKET_AI_HUB treats three markets as first-class research targets:

| Target family | Primary target | Execution instrument | Maturity |
|---------------|----------------|----------------------|----------|
| `OSAKA_MICRO` | OSE Nikkei 225 Micro Futures (`OSE_NIKKEI225_MICRO_FUTURES`) | the Micro futures itself | most complete historical pipeline |
| `TAIWAN_STOCK` | individual Taiwan equities (e.g. `3706.TW`) | the equity itself | runtime analysis available; historical OOS `NOT_YET_VALIDATED` |
| `TAIWAN_INDEX` | TAIEX cash index (forecast/reference) | TX / MTX / TMF | semantics + registry exist; direct pipeline `PARTIAL` |

Forecast target and execution instrument are deliberately separated. TAIEX index points are not
executable futures prices. See [config/primary_market_mission.yaml](config/primary_market_mission.yaml)
and [config/primary_targets.yaml](config/primary_targets.yaml).

## Current research status

| Layer | Conclusion |
|-------|-----------|
| Proxy (`^N225`) OOS | `NO_EVIDENCE` |
| Direct Micro historical OOS | `STATISTICAL_FORECAST_EVIDENCE` (VAR(1), non-executable) |
| Causal / executability | `NON_EXECUTABLE_FORECAST_EDGE` |
| Economic (cost-aware) | `NO_ECONOMIC_EDGE` |
| Forward evidence | `NONE_YET` (accumulating) |
| Strategy / production candidate | `NONE` |
| Trading readiness | `RESEARCH_ONLY` |

Historical statistical signal is **not** trading edge. The authoritative frozen conclusion lives in
[research/phase2/freeze/PHASE2_RESEARCH_FREEZE.yaml](research/phase2/freeze/PHASE2_RESEARCH_FREEZE.yaml).
Live status: [docs/reference/current-status.md](docs/reference/current-status.md).

## What it provides

- **Market data** — official and proxy sources with provenance and data-grade labels.
- **Forecasting** — price (Chronos-2, TimesFM) and direction (XGBoost, LightGBM) models, with a
  research ensemble.
- **Validation** — chronological walk-forward, out-of-sample holdout, leakage guards, baselines,
  and honest metric semantics.
- **MCP** — 21 tools (`health_check`, `get_analysis_packet`, `analyze_osaka_nikkei`,
  `analyze_taiwan_stock`, `get_forward_test_status`, …).
- **Skills** — 3 packaged agent skills (`osaka-micro-analysis`, `taiwan-stock-v28`,
  `model-validation-audit`).

## Quick start

```powershell
# 1. Create the environment
scripts\setup_windows.ps1

# 2. Download required model weights (manual, licensed)
python scripts\download_models.py --required

# 3. Verify
pytest tests/

# 4. Start the MCP server
.venv\Scripts\market-ai-mcp.exe
```

Configure your MCP client to launch that executable over stdio. Cherry Studio is one supported
example — see [docs/getting-started/cherry-studio.md](docs/getting-started/cherry-studio.md).

## Validation philosophy

Evidence is layered and never mixed across layers or markets:

```
DATA → HISTORICAL → CAUSAL → ECONOMIC → FORWARD → RISK → PRODUCTION
```

Passing one layer does not imply the next. Historical statistical evidence is never presented as a
trading signal. See [docs/concepts/validation.md](docs/concepts/validation.md) and
[research/phase2/protocols/OUT_OF_SAMPLE_VALIDATION_STANDARD.md](research/phase2/protocols/OUT_OF_SAMPLE_VALIDATION_STANDARD.md).

## Documentation

Start here: [docs/README.md](docs/README.md) (documentation index).

Key entry points:

- [Quick start](docs/getting-started/quickstart.md)
- [Architecture](docs/ARCHITECTURE.md)
- [MCP tools reference](docs/MCP_TOOL_REFERENCE.md)
- [System prompt (recommended)](docs/prompts/SYSTEM_PROMPT_V4_1_COMPACT.md)
- [Known limitations](docs/reference/known-limitations.md)

## Safety and limitations

- `RESEARCH_ONLY`. No live trading, no order tool, no broker credentials.
- Compute is governed by a resource governor (default `DESKTOP_SAFE`); `AUTO_TRAIN`,
  `AUTO_FINE_TUNE`, and `AUTO_PROMOTE` are all `false`.
- 225LABO and other licensed raw data are `LOCAL_ONLY` and never committed to this repository.

## License

See [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
