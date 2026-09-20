# Research

Historical research evidence, protocols, manifests, results, and reports. This directory is an
archive of the engineering history; current runtime truth is derived from
`research/phase2/freeze/PHASE2_RESEARCH_FREEZE.yaml` and reported at
[`docs/reference/current-status.md`](../docs/reference/current-status.md).

## Layout

```
research/
  README.md
  phase2/
    status/        # runtime-generated forward status (git-ignored)
    freeze/        # authoritative frozen research conclusions
    protocols/     # research exam protocols
    manifests/     # historical research manifests / dataset provenance
    results/       # research result CSV/JSON
    reports/       # phase reports
    performance/   # performance benchmark snapshots
    publication/   # publication/remote reconciliation artifacts
    integrations/  # Yuanta / TradingView research
  releases/        # immutable release snapshots
  history/         # pre-v2 history (V1)
```

## Entry points

- [Phase 2 index](phase2/README.md)
- [Releases](releases/README.md)
- [History (V1)](history/v1/README.md)
