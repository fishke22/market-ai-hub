# Contributing

Thanks for your interest in MARKET_AI_HUB.

## Environment setup

```powershell
scripts\setup_windows.ps1
python -m pip install -e .
```

## Tests

```powershell
pytest tests/
```

Run the full suite before opening a PR. Do not delete or weaken existing tests.

## Research safety

- This is a **research-only** system. Do not add live-trading, order, cancel/modify, or broker-login
  capabilities without an explicit architecture decision.
- Historical evidence, causal evidence, economic edge, and forward evidence are separate layers.
  Never present one as another.
- Never reintroduce look-ahead leakage: time-series validation is chronological; train / validation /
  final-holdout are time-isolated; tuning must not touch the final holdout.

## Data licensing

- Licensed or private data (e.g. 225LABO) is `LOCAL_ONLY` and must never be committed.
- Keep `PUBLICATION_EXCLUDE_MANIFEST.txt` (under `research/phase2/publication/`) in sync with new
  excluded artifacts.

## No secrets

- Never commit credentials, tokens, certificates, or `.env` files.
- Run `python scripts/secret_scan.py` before opening a PR.

## Documentation

- Primary docs live under `docs/` and use professional, plain-language Traditional Chinese.
- Historical research artifacts live under `research/` and are not rewritten for style.
- Keep `docs/README.md` (the documentation index) and root-level links in sync.

## Pull requests

- Target `main`; open a normal PR; do not force-push.
- Include the relevant test command and result in the PR description.
- Verify `python scripts/check_docs_links.py` passes if you moved or renamed files.
