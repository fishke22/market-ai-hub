# MARKET_AI_HUB — Agent Working Agreement

Read this before doing anything. Do not trust stale chat memory (old HEAD / test counts / build_id).

1. **Verify the actual repo first** — never trust HEAD, test counts, or build_id quoted in chat.
2. **Run `scripts/agent_bootstrap.ps1`** (read-only) to print branch / HEAD / origin · status /
   build_id / V2 schema versions / current phase / provider statuses.
3. **Read `docs/development/AGENT_HANDOFF.md`** — the durable handoff (facts survive an agent swap).
4. **Read the current architecture contract + `docs/development/project-status.md`** before coding.
5. **Do not redo a CLOSED/PASS phase.** V2-A.2, V2-B.1, V2-C.2, V2-D.4, V2-E.3, V2-F.3, V2-G.2,
   V2-H 2H.2 are closed; Yuanta rounds are provider hardening, not a redesign.
6. **A provider being unavailable must not block core architecture.** Record it as truthful status
   (e.g. `NOT_AVAILABLE`, `EXTERNAL_ENTITLEMENT_RETEST_REQUIRED`) and continue.
7. **Never conflate** `ENGINE PASS` / `DATA READY` / `CALIBRATED` / `EDGE`. They are different claims.

Also: quote-only for Yuanta (NO ORDER / NO TRADING), never persist secrets, keep reports honest
(cutoff/leakage gates machine-enforced, no fabricated values).
