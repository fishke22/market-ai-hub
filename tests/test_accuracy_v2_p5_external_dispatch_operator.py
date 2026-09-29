"""Offline tests for the fail-closed P5 external-dispatch operator."""
from __future__ import annotations

import json
import subprocess

import scripts.operate_accuracy_v2_p5_external_dispatch as operator


def _cp(argv, payload=None, *, returncode=0, stdout=None):
    if stdout is None:
        stdout = json.dumps(payload or {})
    return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr="")


def _ready_fake_run(recorded):
    stack_outputs = [
        {"OutputKey": "ScheduleState", "OutputValue": "DISABLED"},
        {
            "OutputKey": "ApiDestinationArn",
            "OutputValue": "arn:aws:events:ap-northeast-1:111122223333:api-destination/p5/x",
        },
        {
            "OutputKey": "PrewarmRuleArn",
            "OutputValue": "arn:aws:events:ap-northeast-1:111122223333:rule/p5-prewarm",
        },
        {
            "OutputKey": "BackupRuleArn",
            "OutputValue": "arn:aws:events:ap-northeast-1:111122223333:rule/p5-backup",
        },
    ]

    def fake(argv):
        recorded.append(argv)
        joined = " ".join(argv)
        if "sts get-caller-identity" in joined:
            return _cp(argv, {"Account": "111122223333", "Arn": "arn:aws:iam::111122223333:user/test"})
        if "secretsmanager describe-secret" in joined:
            return _cp(argv, {"Name": "p5-github"})
        if "cloudformation deploy" in joined:
            return _cp(argv, stdout="")
        if "cloudformation describe-stacks" in joined:
            return _cp(
                argv,
                {
                    "Stacks": [
                        {
                            "StackStatus": "CREATE_COMPLETE",
                            "Outputs": stack_outputs,
                        }
                    ]
                },
            )
        if "events describe-rule" in joined:
            schedule = (
                "cron(40 23 ? * SUN-THU *)"
                if "p5-prewarm" in joined
                else "cron(15 0 ? * MON-FRI *)"
            )
            return _cp(argv, {"State": "DISABLED", "ScheduleExpression": schedule})
        if "events list-targets-by-rule" in joined:
            prewarm = "p5-prewarm" in joined
            return _cp(
                argv,
                {
                    "Targets": [
                        {
                            "Id": "P5GitHubPrewarmDispatch" if prewarm else "P5GitHubBackupDispatch",
                            "Arn": "arn:aws:events:ap-northeast-1:111122223333:api-destination/p5/x",
                            "RoleArn": "arn:aws:iam::111122223333:role/p5",
                            "Input": json.dumps(operator.EXPECTED_INPUT, separators=(",", ":")),
                            "RetryPolicy": {
                                "MaximumRetryAttempts": 3,
                                "MaximumEventAgeInSeconds": 300,
                            },
                            "DeadLetterConfig": {
                                "Arn": "arn:aws:sqs:ap-northeast-1:111122223333:p5-dlq"
                            },
                        }
                    ]
                },
            )
        raise AssertionError(f"unexpected command: {argv}")

    return fake


def test_preflight_blocks_without_aws(monkeypatch):
    monkeypatch.setattr(operator, "_detect_aws", lambda: None)
    result = operator.preflight(secret_arn=None, region=None)
    assert result["status"] == "BLOCKED"
    assert "AWS_CLI_MISSING" in result["reasons"]
    assert result["deployment_performed"] is False
    assert result["secret_value_read"] is False


def test_preflight_ready_uses_metadata_only(monkeypatch):
    recorded = []
    monkeypatch.setattr(operator, "_detect_aws", lambda: "aws")
    monkeypatch.setattr(operator, "_run", _ready_fake_run(recorded))
    result = operator.preflight(
        secret_arn="arn:aws:secretsmanager:ap-northeast-1:111122223333:secret:p5",
        region=None,
    )
    assert result["status"] == "READY_FOR_DISABLED_DEPLOY"
    assert result["aws_identity_ok"] is True
    assert result["secret_metadata_ok"] is True
    assert result["secret_value_read"] is False
    assert all("get-secret-value" not in " ".join(cmd) for cmd in recorded)


def test_inspect_requires_both_rules_disabled(monkeypatch):
    recorded = []
    monkeypatch.setattr(operator, "_detect_aws", lambda: "aws")
    monkeypatch.setattr(operator, "_run", _ready_fake_run(recorded))
    result = operator.inspect_disabled_stack(region="ap-northeast-1")
    assert result["status"] == "DEPLOYED_DISABLED_VERIFIED"
    assert result["rules_verified"] == 2
    assert result["schedule_state_disabled"] is True
    assert result["secret_value_read"] is False


def test_deploy_is_disabled_only_and_uses_capability_iam(monkeypatch):
    recorded = []
    monkeypatch.setattr(operator, "_detect_aws", lambda: "aws")
    monkeypatch.setattr(operator, "_run", _ready_fake_run(recorded))
    result = operator.deploy_disabled(
        secret_arn="arn:aws:secretsmanager:ap-northeast-1:111122223333:secret:p5",
        region="ap-northeast-1",
        confirm_disabled_deploy=True,
    )
    assert result["status"] == "DEPLOYED_DISABLED_VERIFIED"
    assert result["deployment_performed"] is True
    deploy_cmd = next(cmd for cmd in recorded if "cloudformation" in cmd and "deploy" in cmd)
    joined = " ".join(deploy_cmd)
    assert "CAPABILITY_IAM" in deploy_cmd
    assert "ScheduleState=DISABLED" in deploy_cmd
    assert "ScheduleState=ENABLED" not in joined
    assert "get-secret-value" not in joined


def test_deploy_requires_explicit_confirmation_and_parser_has_no_enable():
    result = operator.deploy_disabled(
        secret_arn="arn:aws:secretsmanager:ap-northeast-1:111122223333:secret:p5",
        region="ap-northeast-1",
        confirm_disabled_deploy=False,
        aws_executable="aws",
    )
    assert result["status"] == "BLOCKED"
    assert result["reasons"] == ["EXPLICIT_DISABLED_DEPLOY_CONFIRMATION_REQUIRED"]
    parser = operator.build_parser()
    choices = parser._subparsers._group_actions[0].choices
    assert set(choices) == {"preflight", "inspect", "deploy-disabled"}
