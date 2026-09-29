"""Guards for the disabled-by-default P5 EventBridge dispatch package."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import yaml

from scripts.validate_accuracy_v2_p5_external_dispatch import (
    EXPECTED_SCHEDULES,
    validate_documents,
    validate_files,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "infra" / "aws" / "p5-eventbridge-dispatch.contract.yaml"
TEMPLATE_PATH = ROOT / "infra" / "aws" / "p5-eventbridge-dispatch.yaml"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "p5-cloud-public-forward.yml"


def _docs():
    contract = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    template = yaml.safe_load(TEMPLATE_PATH.read_text(encoding="utf-8"))
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    return contract, template, workflow


def test_external_dispatch_package_validates_offline():
    result = validate_files()
    assert result["status"] == "PASS"
    assert result["deployment_performed"] is False
    assert result["secret_value_in_repo"] is False
    assert result["end_to_end_runner_start_guaranteed"] is False


def test_eventbridge_schedules_match_taipei_slots_and_default_disabled():
    contract, template, _ = _docs()
    assert contract["schedules"]["prewarm"]["asia_taipei"] == "07:40"
    assert contract["schedules"]["backup"]["asia_taipei"] == "08:15"
    resources = template["Resources"]
    for slot, expected in EXPECTED_SCHEDULES.items():
        assert contract["schedules"][slot]["eventbridge_cron"] == expected["eventbridge_cron"]
        assert resources[expected["resource"]]["Properties"]["ScheduleExpression"] == expected["eventbridge_cron"]
        assert resources[expected["resource"]]["Properties"]["State"] == {"Ref": "ScheduleState"}
    assert template["Parameters"]["ScheduleState"]["Default"] == "DISABLED"


def test_connection_uses_secret_reference_and_no_committed_token():
    contract, template, _ = _docs()
    connection = template["Resources"]["P5GitHubConnection"]["Properties"]
    api_key = connection["AuthParameters"]["ApiKeyAuthParameters"]
    assert api_key["ApiKeyName"] == "Authorization"
    assert api_key["ApiKeyValue"]["Fn::Sub"] == (
        "{{resolve:secretsmanager:${GitHubAuthorizationSecretArn}:"
        "SecretString:authorization}}"
    )
    assert "Default" not in template["Parameters"]["GitHubAuthorizationSecretArn"]
    assert contract["authentication"]["committed_secret_value"] is False
    text = (
        CONTRACT_PATH.read_text(encoding="utf-8")
        + TEMPLATE_PATH.read_text(encoding="utf-8")
    ).lower()
    for marker in (
        "github_" + "pat_",
        "gh" + "p_",
        "aws_access_" + "key_id",
        "aws_secret_" + "access_key",
    ):
        assert marker not in text


def test_targets_are_retry_bounded_dlq_backed_and_p5_gates_frozen():
    contract, template, workflow = _docs()
    for expected in EXPECTED_SCHEDULES.values():
        target = template["Resources"][expected["resource"]]["Properties"]["Targets"][0]
        assert target["Input"]["Fn::Sub"] == (
            '{"ref":"${GitHubRef}","inputs":{"mode":"scheduled"}}'
        )
        assert target["RetryPolicy"] == {
            "MaximumEventAgeInSeconds": 300,
            "MaximumRetryAttempts": 3,
        }
        assert target["DeadLetterConfig"]["Arn"]["Fn::GetAtt"] == [
            "P5DispatchDeadLetterQueue",
            "Arn",
        ]
    frozen = contract["p5_frozen_invariants"]
    assert frozen == {
        "canonical_origin_asia_taipei": "08:05",
        "max_lateness_minutes": 15,
        "no_backfill": True,
        "public_sources_only": True,
        "append_only_state": True,
        "broker_used": False,
        "recorder_touched": False,
        "order_action": False,
    }
    assert 'cron: "40 7 * * 1-5"' in workflow
    assert 'cron: "15 8 * * 1-5"' in workflow


def test_operator_contract_is_disabled_only_and_never_reads_secret_value():
    contract, _, workflow = _docs()
    operator = contract["operator"]
    assert operator == {
        "script": "scripts/operate_accuracy_v2_p5_external_dispatch.py",
        "preflight_read_only": True,
        "deployment_mode": "DISABLED_ONLY",
        "cloudformation_capability": "CAPABILITY_IAM",
        "secret_metadata_probe": "DescribeSecret",
        "secret_value_read": False,
        "schedule_enable_supported": False,
    }
    assert '"scripts/operate_accuracy_v2_p5_external_dispatch.py"' in workflow
    assert '"tests/test_accuracy_v2_p5_external_dispatch_operator.py"' in workflow


def test_validator_fails_closed_if_schedule_auto_enables_or_window_changes():
    contract, template, workflow = _docs()
    bad_template = deepcopy(template)
    bad_template["Parameters"]["ScheduleState"]["Default"] = "ENABLED"
    bad_contract = deepcopy(contract)
    bad_contract["p5_frozen_invariants"]["max_lateness_minutes"] = 30
    errors = validate_documents(bad_contract, bad_template, workflow)
    assert any("ScheduleState must default to DISABLED" in error for error in errors)
    assert any("max_lateness_minutes" in error for error in errors)


def test_validator_cli_requires_no_aws_runtime():
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate_accuracy_v2_p5_external_dispatch.py"),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert '"status": "PASS"' in proc.stdout
