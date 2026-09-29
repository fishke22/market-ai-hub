# Accuracy v2 P5 external punctual dispatch

## Scope

This package is an **external trigger only** for the already-merged public-source P5 GitHub workflow. It does not change the P5 model, target, origin gate, evidence ledger, broker policy, or cloud-state merge semantics.

The source-controlled state is `ENGINEERING_READY_NOT_DEPLOYED`. Deployment is intentionally separate from engineering validation.

## Why EventBridge scheduled rules

GitHub native scheduled workflows are retained as a fallback, but GitHub does not provide a start-time guarantee suitable for the frozen P5 canonical window. The external candidate uses Amazon EventBridge scheduled rules because AWS documents one-minute schedule resolution and guaranteed delivery of each expected scheduled event. This improves dispatch punctuality; it does **not** guarantee when a GitHub-hosted runner will start.

Architecture:

`EventBridge scheduled rule -> API Destination -> GitHub workflow_dispatch(mode=scheduled)`

The existing GitHub workflow remains responsible for the public-source-only cycle and all frozen P5 gates.

## Schedules

Taipei has no daylight-saving transition, so the source-controlled UTC mapping is deterministic:

| Slot | Asia/Taipei | EventBridge UTC cron |
| --- | --- | --- |
| prewarm | 07:40 Mon-Fri | `cron(40 23 ? * SUN-THU *)` |
| backup | 08:15 Mon-Fri | `cron(15 0 ? * MON-FRI *)` |

The canonical P5 origin remains **08:05 Asia/Taipei** and the existing `<=15m` lateness gate remains authoritative. EventBridge retries are bounded to 300 seconds; late GitHub execution still fails closed inside P5.

## Credentials

No GitHub token is committed or accepted as a CloudFormation plaintext parameter.

Before deployment, an operator must create an AWS Secrets Manager JSON secret outside the repository:

`{"authorization":"Bearer <fine-grained-token>"}`

The fine-grained GitHub token should be restricted to this repository with repository permission **Actions: write**. CloudFormation receives only the secret ARN. `AWS::Events::Connection` resolves the secret dynamically and stores the EventBridge service-linked credential.

## Fail-closed deployment

`ScheduleState` defaults to `DISABLED`.

A safe deployment sequence is:

1. Create the restricted GitHub authorization secret out-of-band.
2. Deploy `infra/aws/p5-eventbridge-dispatch.yaml` with `ScheduleState=DISABLED`.
3. Run `python scripts/validate_accuracy_v2_p5_external_dispatch.py`.
4. Inspect the API Destination, scoped IAM role, SQS dead-letter queue, and both rule cron expressions.
5. Explicitly enable schedules only after a noncanonical external-dispatch smoke confirms the correct GitHub workflow/ref and no credential leakage.
6. Observe at least one real scheduled dispatch before changing `P5_CLOUD_PUNCTUAL_TRIGGER` from unresolved.

This repository does not deploy the stack automatically and contains no AWS credential bootstrap.

## Safety invariants

The external scheduler cannot relax these existing P5 rules:

- canonical origin `08:05 Asia/Taipei`
- maximum canonical lateness `15m`
- no historical backfill
- public sources only
- append-only audit/state handling
- no broker/account/order path
- no recorder action
- no automatic model promotion

`PREDICTIVE_GAIN=false`, `CALIBRATED=false`, and `TRADING_EDGE=false` remain unchanged.

## Evidence boundary

Offline CloudFormation/config validation proves only that the source-controlled package is internally consistent and disabled by default. It does not prove:

- an AWS account has deployed the stack;
- the secret/token is valid;
- EventBridge reached GitHub;
- GitHub created a workflow run;
- a GitHub-hosted runner started before the canonical deadline.

Those require future external runtime evidence.

Engineering acceptance on the isolated worktree: offline validator `PASS`, new package tests `6 passed`, affected P5/build cross-regression `34 passed`, workflow YAML parse `PASS`. Runtime source/config build remains `426583a3e6f2f27e`; no full suite was repeated.
