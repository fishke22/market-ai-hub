"""Fail-closed operator for the Accuracy v2 P5 external EventBridge dispatch stack."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.validate_accuracy_v2_p5_external_dispatch import validate_files
TEMPLATE = ROOT / "infra" / "aws" / "p5-eventbridge-dispatch.yaml"
DEFAULT_STACK_NAME = "market-ai-hub-p5-external-dispatch"
SECRET_ENV = "P5_GITHUB_AUTH_SECRET_ARN"
SCHEMA = "AV2.P5.EXTERNAL_DISPATCH.OPERATOR.1"
EXPECTED_RULES = {
    "prewarm": {
        "output": "PrewarmRuleArn",
        "schedule": "cron(40 23 ? * SUN-THU *)",
        "target_id": "P5GitHubPrewarmDispatch",
    },
    "backup": {
        "output": "BackupRuleArn",
        "schedule": "cron(15 0 ? * MON-FRI *)",
        "target_id": "P5GitHubBackupDispatch",
    },
}
EXPECTED_INPUT = {"ref": "main", "inputs": {"mode": "scheduled"}}
ALLOWED_STACK_STATUSES = {"CREATE_COMPLETE", "UPDATE_COMPLETE"}


class AwsCommandError(RuntimeError):
    """Bounded AWS command failure without leaking command output."""

    def __init__(self, reason: str, returncode: int):
        super().__init__(reason)
        self.reason = reason
        self.returncode = returncode


def _detect_aws() -> str | None:
    return shutil.which("aws")


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _aws_json(aws: str, args: list[str], *, reason: str) -> dict[str, Any]:
    proc = _run([aws, *args, "--output", "json", "--no-cli-pager"])
    if proc.returncode != 0:
        raise AwsCommandError(reason, proc.returncode)
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise AwsCommandError(f"{reason}_INVALID_JSON", proc.returncode) from exc
    if not isinstance(payload, dict):
        raise AwsCommandError(f"{reason}_INVALID_SHAPE", proc.returncode)
    return payload


def _region_from_secret_arn(secret_arn: str | None) -> str | None:
    if not secret_arn:
        return None
    parts = secret_arn.split(":")
    if len(parts) >= 6 and parts[2] == "secretsmanager" and parts[3]:
        return parts[3]
    return None


def _resolve_region(
    explicit_region: str | None,
    secret_arn: str | None,
    aws: str | None,
) -> str | None:
    region = (
        explicit_region
        or os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or _region_from_secret_arn(secret_arn)
    )
    if region or not aws:
        return region
    proc = _run([aws, "configure", "get", "region"])
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()
    return None


def preflight(
    *,
    secret_arn: str | None = None,
    region: str | None = None,
    aws_executable: str | None = None,
) -> dict[str, Any]:
    """Read-only readiness probe. Never retrieves a secret value."""
    secret_arn = secret_arn or os.environ.get(SECRET_ENV)
    offline = validate_files()
    aws = aws_executable or _detect_aws()
    region = _resolve_region(region, secret_arn, aws)
    reasons: list[str] = []

    result: dict[str, Any] = {
        "schema": SCHEMA,
        "action": "preflight",
        "status": "BLOCKED",
        "offline_contract_pass": offline["status"] == "PASS",
        "aws_cli_present": bool(aws),
        "aws_identity_ok": False,
        "aws_region_resolved": bool(region),
        "secret_arn_supplied": bool(secret_arn),
        "secret_metadata_ok": False,
        "secret_value_read": False,
        "deployment_performed": False,
        "schedule_enable_supported": False,
        "reasons": reasons,
    }

    if offline["status"] != "PASS":
        reasons.append("OFFLINE_CONTRACT_FAILED")
    if not aws:
        reasons.append("AWS_CLI_MISSING")
    if not region:
        reasons.append("AWS_REGION_UNRESOLVED")
    if not secret_arn:
        reasons.append("GITHUB_AUTHORIZATION_SECRET_ARN_MISSING")
    if reasons:
        return result

    try:
        _aws_json(
            aws,
            ["sts", "get-caller-identity"],
            reason="AWS_IDENTITY_UNAVAILABLE",
        )
        result["aws_identity_ok"] = True
    except AwsCommandError:
        reasons.append("AWS_IDENTITY_UNAVAILABLE")
        return result

    try:
        _aws_json(
            aws,
            [
                "secretsmanager",
                "describe-secret",
                "--secret-id",
                secret_arn,
                "--region",
                region,
            ],
            reason="SECRET_METADATA_UNAVAILABLE",
        )
        result["secret_metadata_ok"] = True
    except AwsCommandError:
        reasons.append("SECRET_METADATA_UNAVAILABLE")
        return result

    result["status"] = "READY_FOR_DISABLED_DEPLOY"
    return result


def _rule_name_from_arn(rule_arn: str) -> str | None:
    marker = ":rule/"
    if marker not in rule_arn:
        return None
    name = rule_arn.split(marker, 1)[1]
    return name or None


def inspect_disabled_stack(
    *,
    stack_name: str = DEFAULT_STACK_NAME,
    region: str | None = None,
    aws_executable: str | None = None,
) -> dict[str, Any]:
    """Inspect deployed resources without reading connection secret values."""
    aws = aws_executable or _detect_aws()
    region = _resolve_region(region, None, aws)
    errors: list[str] = []
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "action": "inspect",
        "status": "FAIL",
        "stack_observed": False,
        "stack_status_allowed": False,
        "schedule_state_disabled": False,
        "rules_verified": 0,
        "secret_value_read": False,
        "deployment_performed": False,
        "schedule_enable_supported": False,
        "errors": errors,
    }
    if not aws:
        errors.append("AWS_CLI_MISSING")
        return result
    if not region:
        errors.append("AWS_REGION_UNRESOLVED")
        return result

    try:
        _aws_json(aws, ["sts", "get-caller-identity"], reason="AWS_IDENTITY_UNAVAILABLE")
        stack_payload = _aws_json(
            aws,
            [
                "cloudformation",
                "describe-stacks",
                "--stack-name",
                stack_name,
                "--region",
                region,
            ],
            reason="STACK_UNAVAILABLE",
        )
    except AwsCommandError as exc:
        errors.append(exc.reason)
        return result

    stacks = stack_payload.get("Stacks") or []
    if len(stacks) != 1 or not isinstance(stacks[0], dict):
        errors.append("STACK_SHAPE_INVALID")
        return result
    result["stack_observed"] = True
    stack = stacks[0]
    stack_status = stack.get("StackStatus")
    result["stack_status_allowed"] = stack_status in ALLOWED_STACK_STATUSES
    if not result["stack_status_allowed"]:
        errors.append("STACK_STATUS_NOT_COMPLETE")

    outputs = {
        item.get("OutputKey"): item.get("OutputValue")
        for item in stack.get("Outputs") or []
        if isinstance(item, dict)
    }
    result["schedule_state_disabled"] = outputs.get("ScheduleState") == "DISABLED"
    if not result["schedule_state_disabled"]:
        errors.append("SCHEDULE_STATE_NOT_DISABLED")

    api_destination_arn = outputs.get("ApiDestinationArn")
    if not api_destination_arn:
        errors.append("API_DESTINATION_OUTPUT_MISSING")

    for slot, expected in EXPECTED_RULES.items():
        rule_arn = outputs.get(expected["output"])
        rule_name = _rule_name_from_arn(rule_arn) if isinstance(rule_arn, str) else None
        if not rule_name:
            errors.append(f"{slot.upper()}_RULE_OUTPUT_INVALID")
            continue
        try:
            rule = _aws_json(
                aws,
                ["events", "describe-rule", "--name", rule_name, "--region", region],
                reason=f"{slot.upper()}_RULE_UNAVAILABLE",
            )
            targets_payload = _aws_json(
                aws,
                [
                    "events",
                    "list-targets-by-rule",
                    "--rule",
                    rule_name,
                    "--region",
                    region,
                ],
                reason=f"{slot.upper()}_TARGETS_UNAVAILABLE",
            )
        except AwsCommandError as exc:
            errors.append(exc.reason)
            continue

        slot_errors: list[str] = []
        if rule.get("State") != "DISABLED":
            slot_errors.append("STATE_NOT_DISABLED")
        if rule.get("ScheduleExpression") != expected["schedule"]:
            slot_errors.append("SCHEDULE_MISMATCH")
        targets = targets_payload.get("Targets") or []
        if len(targets) != 1 or not isinstance(targets[0], dict):
            slot_errors.append("TARGET_COUNT_MISMATCH")
        else:
            target = targets[0]
            if target.get("Id") != expected["target_id"]:
                slot_errors.append("TARGET_ID_MISMATCH")
            if target.get("Arn") != api_destination_arn:
                slot_errors.append("TARGET_DESTINATION_MISMATCH")
            try:
                target_input = json.loads(target.get("Input") or "")
            except json.JSONDecodeError:
                target_input = None
            if target_input != EXPECTED_INPUT:
                slot_errors.append("TARGET_INPUT_MISMATCH")
            if target.get("RetryPolicy") != {
                "MaximumRetryAttempts": 3,
                "MaximumEventAgeInSeconds": 300,
            }:
                slot_errors.append("RETRY_POLICY_MISMATCH")
            if not (target.get("DeadLetterConfig") or {}).get("Arn"):
                slot_errors.append("DLQ_MISSING")
            if not target.get("RoleArn"):
                slot_errors.append("ROLE_ARN_MISSING")

        if slot_errors:
            errors.extend(f"{slot.upper()}_{item}" for item in slot_errors)
        else:
            result["rules_verified"] += 1

    if (
        not errors
        and result["stack_observed"]
        and result["stack_status_allowed"]
        and result["schedule_state_disabled"]
        and result["rules_verified"] == len(EXPECTED_RULES)
    ):
        result["status"] = "DEPLOYED_DISABLED_VERIFIED"
    return result


def deploy_disabled(
    *,
    secret_arn: str | None = None,
    region: str | None = None,
    stack_name: str = DEFAULT_STACK_NAME,
    confirm_disabled_deploy: bool = False,
    aws_executable: str | None = None,
) -> dict[str, Any]:
    """Deploy only the disabled stack, then verify it remains disabled."""
    if not confirm_disabled_deploy:
        return {
            "schema": SCHEMA,
            "action": "deploy-disabled",
            "status": "BLOCKED",
            "deployment_performed": False,
            "secret_value_read": False,
            "schedule_enable_supported": False,
            "reasons": ["EXPLICIT_DISABLED_DEPLOY_CONFIRMATION_REQUIRED"],
        }

    secret_arn = secret_arn or os.environ.get(SECRET_ENV)
    aws = aws_executable or _detect_aws()
    resolved_region = _resolve_region(region, secret_arn, aws)
    readiness = preflight(
        secret_arn=secret_arn,
        region=resolved_region,
        aws_executable=aws,
    )
    if readiness["status"] != "READY_FOR_DISABLED_DEPLOY":
        readiness = dict(readiness)
        readiness["action"] = "deploy-disabled"
        return readiness

    assert aws is not None
    assert resolved_region is not None
    assert secret_arn is not None
    command = [
        aws,
        "cloudformation",
        "deploy",
        "--template-file",
        str(TEMPLATE),
        "--stack-name",
        stack_name,
        "--region",
        resolved_region,
        "--capabilities",
        "CAPABILITY_IAM",
        "--parameter-overrides",
        f"GitHubAuthorizationSecretArn={secret_arn}",
        "ScheduleState=DISABLED",
        "--no-fail-on-empty-changeset",
        "--no-cli-pager",
    ]
    proc = _run(command)
    if proc.returncode != 0:
        return {
            "schema": SCHEMA,
            "action": "deploy-disabled",
            "status": "DEPLOY_FAILED",
            "deployment_performed": False,
            "secret_value_read": False,
            "schedule_enable_supported": False,
            "reasons": ["CLOUDFORMATION_DEPLOY_FAILED"],
        }

    inspection = inspect_disabled_stack(
        stack_name=stack_name,
        region=resolved_region,
        aws_executable=aws,
    )
    inspection = dict(inspection)
    inspection["action"] = "deploy-disabled"
    inspection["deployment_performed"] = True
    if inspection["status"] != "DEPLOYED_DISABLED_VERIFIED":
        inspection["status"] = "DEPLOYED_INSPECTION_FAILED"
    return inspection


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fail-closed operator for the P5 external EventBridge dispatch stack."
    )
    sub = parser.add_subparsers(dest="action", required=True)

    pre = sub.add_parser("preflight")
    pre.add_argument("--secret-arn")
    pre.add_argument("--region")

    inspect = sub.add_parser("inspect")
    inspect.add_argument("--region")
    inspect.add_argument("--stack-name", default=DEFAULT_STACK_NAME)

    deploy = sub.add_parser("deploy-disabled")
    deploy.add_argument("--secret-arn")
    deploy.add_argument("--region")
    deploy.add_argument("--stack-name", default=DEFAULT_STACK_NAME)
    deploy.add_argument("--confirm-disabled-deploy", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.action == "preflight":
        result = preflight(secret_arn=args.secret_arn, region=args.region)
    elif args.action == "inspect":
        result = inspect_disabled_stack(stack_name=args.stack_name, region=args.region)
    else:
        result = deploy_disabled(
            secret_arn=args.secret_arn,
            region=args.region,
            stack_name=args.stack_name,
            confirm_disabled_deploy=args.confirm_disabled_deploy,
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] in {
        "READY_FOR_DISABLED_DEPLOY",
        "DEPLOYED_DISABLED_VERIFIED",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
