"""Offline validator for the P5 external EventBridge dispatch package."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "infra" / "aws" / "p5-eventbridge-dispatch.contract.yaml"
DEFAULT_TEMPLATE = ROOT / "infra" / "aws" / "p5-eventbridge-dispatch.yaml"
DEFAULT_WORKFLOW = ROOT / ".github" / "workflows" / "p5-cloud-public-forward.yml"

EXPECTED_SCHEDULES = {
    "prewarm": {
        "asia_taipei": "07:40",
        "eventbridge_cron": "cron(40 23 ? * SUN-THU *)",
        "resource": "P5PrewarmDispatchRule",
    },
    "backup": {
        "asia_taipei": "08:15",
        "eventbridge_cron": "cron(15 0 ? * MON-FRI *)",
        "resource": "P5BackupDispatchRule",
    },
}
REQUIRED_WORKFLOW_PATHS = {
    "infra/aws/p5-eventbridge-dispatch.contract.yaml",
    "infra/aws/p5-eventbridge-dispatch.yaml",
    "scripts/validate_accuracy_v2_p5_external_dispatch.py",
    "tests/test_accuracy_v2_p5_external_dispatch.py",
}
FORBIDDEN_SECRET_MARKERS = (
    "github_" + "pat_",
    "gh" + "p_",
    "gh" + "o_",
    "gh" + "u_",
    "gh" + "s_",
    "gh" + "r_",
    "aws_access_" + "key_id",
    "aws_secret_" + "access_key",
)


def _fn_sub(value: Any) -> str:
    if isinstance(value, dict) and isinstance(value.get("Fn::Sub"), str):
        return value["Fn::Sub"]
    return ""


def _getatt(value: Any) -> tuple[str, str] | None:
    if not isinstance(value, dict):
        return None
    raw = value.get("Fn::GetAtt")
    if isinstance(raw, list) and len(raw) == 2 and all(isinstance(x, str) for x in raw):
        return raw[0], raw[1]
    return None


def _ref(value: Any) -> str | None:
    if isinstance(value, dict) and isinstance(value.get("Ref"), str):
        return value["Ref"]
    return None


def _resources_of_type(template: dict[str, Any], resource_type: str) -> dict[str, dict[str, Any]]:
    resources = template.get("Resources") or {}
    if not isinstance(resources, dict):
        return {}
    return {
        name: body
        for name, body in resources.items()
        if isinstance(body, dict) and body.get("Type") == resource_type
    }


def validate_documents(
    contract: dict[str, Any],
    template: dict[str, Any],
    workflow_text: str,
    *,
    raw_contract: str = "",
    raw_template: str = "",
) -> list[str]:
    errors: list[str] = []

    if contract.get("schema") != "AV2.P5.EXTERNAL_DISPATCH.1":
        errors.append("contract.schema must be AV2.P5.EXTERNAL_DISPATCH.1")
    if contract.get("status") != "ENGINEERING_READY_NOT_DEPLOYED":
        errors.append("contract.status must remain ENGINEERING_READY_NOT_DEPLOYED")
    if contract.get("provider") != "AWS_EVENTBRIDGE_SCHEDULED_RULE_API_DESTINATION":
        errors.append("contract.provider mismatch")

    deployment = contract.get("deployment") or {}
    if deployment.get("deployed") is not False:
        errors.append("deployment.deployed must be false in source-controlled contract")
    if deployment.get("requires_explicit_schedule_enable") is not True:
        errors.append("deployment must require explicit schedule enable")
    if deployment.get("end_to_end_github_runner_start_guaranteed") is not False:
        errors.append("end-to-end GitHub runner start must not be claimed guaranteed")

    frozen = contract.get("p5_frozen_invariants") or {}
    expected_frozen = {
        "canonical_origin_asia_taipei": "08:05",
        "max_lateness_minutes": 15,
        "no_backfill": True,
        "public_sources_only": True,
        "append_only_state": True,
        "broker_used": False,
        "recorder_touched": False,
        "order_action": False,
    }
    for key, expected in expected_frozen.items():
        if frozen.get(key) != expected:
            errors.append(f"p5_frozen_invariants.{key} must be {expected!r}")

    claims = contract.get("claims") or {}
    for key in ("predictive_gain", "calibrated", "trading_edge"):
        if claims.get(key) is not False:
            errors.append(f"claims.{key} must remain false")

    schedules = contract.get("schedules") or {}
    for slot, expected in EXPECTED_SCHEDULES.items():
        actual = schedules.get(slot) or {}
        for key in ("asia_taipei", "eventbridge_cron"):
            if actual.get(key) != expected[key]:
                errors.append(f"schedules.{slot}.{key} mismatch")

    params = template.get("Parameters") or {}
    schedule_state = params.get("ScheduleState") or {}
    if schedule_state.get("Default") != "DISABLED":
        errors.append("CloudFormation ScheduleState must default to DISABLED")
    if schedule_state.get("AllowedValues") != ["DISABLED", "ENABLED"]:
        errors.append("ScheduleState allowed values must be DISABLED/ENABLED")
    secret_param = params.get("GitHubAuthorizationSecretArn") or {}
    if "Default" in secret_param:
        errors.append("GitHubAuthorizationSecretArn must not have a default")

    connections = _resources_of_type(template, "AWS::Events::Connection")
    if set(connections) != {"P5GitHubConnection"}:
        errors.append("template must contain exactly P5GitHubConnection")
    else:
        props = connections["P5GitHubConnection"].get("Properties") or {}
        if props.get("AuthorizationType") != "API_KEY":
            errors.append("P5GitHubConnection must use API_KEY authorization")
        api_key = ((props.get("AuthParameters") or {}).get("ApiKeyAuthParameters") or {})
        if api_key.get("ApiKeyName") != "Authorization":
            errors.append("connection API key header must be Authorization")
        secret_ref = _fn_sub(api_key.get("ApiKeyValue"))
        expected_ref = (
            "{{resolve:secretsmanager:${GitHubAuthorizationSecretArn}:"
            "SecretString:authorization}}"
        )
        if secret_ref != expected_ref:
            errors.append("connection must resolve authorization from Secrets Manager")

    destinations = _resources_of_type(template, "AWS::Events::ApiDestination")
    if set(destinations) != {"P5GitHubDispatchDestination"}:
        errors.append("template must contain exactly P5GitHubDispatchDestination")
    else:
        props = destinations["P5GitHubDispatchDestination"].get("Properties") or {}
        if props.get("HttpMethod") != "POST":
            errors.append("API Destination must use POST")
        endpoint = _fn_sub(props.get("InvocationEndpoint"))
        required_endpoint = (
            "https://api.github.com/repos/${GitHubOwner}/${GitHubRepository}/"
            "actions/workflows/${GitHubWorkflowFile}/dispatches"
        )
        if endpoint != required_endpoint:
            errors.append("API Destination endpoint mismatch")
        if props.get("InvocationRateLimitPerSecond") != 1:
            errors.append("API Destination rate limit must be 1 request/second")

    roles = _resources_of_type(template, "AWS::IAM::Role")
    role = roles.get("P5EventBridgeInvokeRole") or {}
    policies = (role.get("Properties") or {}).get("Policies") or []
    statements = (
        ((policies[0].get("PolicyDocument") or {}).get("Statement") or [])
        if policies
        else []
    )
    if len(statements) != 1:
        errors.append("EventBridge invocation role must have one policy statement")
    elif statements[0].get("Action") != "events:InvokeApiDestination":
        errors.append("invocation role may only call events:InvokeApiDestination")
    elif _getatt(statements[0].get("Resource")) != ("P5GitHubDispatchDestination", "Arn"):
        errors.append("invocation role must scope Resource to the P5 API Destination")

    queues = _resources_of_type(template, "AWS::SQS::Queue")
    if set(queues) != {"P5DispatchDeadLetterQueue"}:
        errors.append("template must include the dedicated P5 dead-letter queue")

    resources = template.get("Resources") or {}
    for slot, expected in EXPECTED_SCHEDULES.items():
        body = resources.get(expected["resource"]) or {}
        if body.get("Type") != "AWS::Events::Rule":
            errors.append(f"{expected['resource']} must be AWS::Events::Rule")
            continue
        props = body.get("Properties") or {}
        if props.get("ScheduleExpression") != expected["eventbridge_cron"]:
            errors.append(f"{expected['resource']} schedule mismatch")
        if _ref(props.get("State")) != "ScheduleState":
            errors.append(f"{expected['resource']} must use ScheduleState")
        targets = props.get("Targets") or []
        if len(targets) != 1:
            errors.append(f"{expected['resource']} must have one target")
            continue
        target = targets[0]
        if _getatt(target.get("Arn")) != ("P5GitHubDispatchDestination", "Arn"):
            errors.append(f"{expected['resource']} target must be P5 API Destination")
        if _getatt(target.get("RoleArn")) != ("P5EventBridgeInvokeRole", "Arn"):
            errors.append(f"{expected['resource']} must use the scoped invocation role")
        input_payload = _fn_sub(target.get("Input"))
        if input_payload != '{"ref":"${GitHubRef}","inputs":{"mode":"scheduled"}}':
            errors.append(f"{expected['resource']} workflow dispatch body mismatch")
        retry = target.get("RetryPolicy") or {}
        if retry.get("MaximumEventAgeInSeconds") != 300:
            errors.append(f"{expected['resource']} max event age must be 300 seconds")
        if retry.get("MaximumRetryAttempts") != 3:
            errors.append(f"{expected['resource']} retry attempts must be 3")
        if _getatt((target.get("DeadLetterConfig") or {}).get("Arn")) != (
            "P5DispatchDeadLetterQueue",
            "Arn",
        ):
            errors.append(f"{expected['resource']} must use the P5 DLQ")

    lower_source = (raw_contract + "\n" + raw_template).lower()
    for marker in FORBIDDEN_SECRET_MARKERS:
        if marker in lower_source:
            errors.append(f"forbidden secret marker found in source: {marker}")

    if "workflow_dispatch:" not in workflow_text:
        errors.append("P5 workflow must keep workflow_dispatch")
    if "- scheduled" not in workflow_text:
        errors.append("P5 workflow must keep scheduled dispatch mode")
    if 'cron: "40 7 * * 1-5"' not in workflow_text:
        errors.append("native prewarm schedule must remain unchanged")
    if 'cron: "15 8 * * 1-5"' not in workflow_text:
        errors.append("native backup schedule must remain unchanged")
    for rel in REQUIRED_WORKFLOW_PATHS:
        if f'"{rel}"' not in workflow_text:
            errors.append(f"P5 workflow PR paths missing {rel}")

    return errors


def validate_files(
    contract_path: Path = DEFAULT_CONTRACT,
    template_path: Path = DEFAULT_TEMPLATE,
    workflow_path: Path = DEFAULT_WORKFLOW,
) -> dict[str, Any]:
    raw_contract = contract_path.read_text(encoding="utf-8")
    raw_template = template_path.read_text(encoding="utf-8")
    workflow_text = workflow_path.read_text(encoding="utf-8")
    errors = validate_documents(
        yaml.safe_load(raw_contract),
        yaml.safe_load(raw_template),
        workflow_text,
        raw_contract=raw_contract,
        raw_template=raw_template,
    )
    return {
        "schema": "AV2.P5.EXTERNAL_DISPATCH.VALIDATION.1",
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "deployment_performed": False,
        "secret_value_in_repo": False,
        "end_to_end_runner_start_guaranteed": False,
        "contract": str(contract_path),
        "template": str(template_path),
        "workflow": str(workflow_path),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    ap.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    ap.add_argument("--workflow", type=Path, default=DEFAULT_WORKFLOW)
    args = ap.parse_args()
    result = validate_files(args.contract, args.template, args.workflow)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
