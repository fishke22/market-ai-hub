from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_hidden_runner_is_console_free_and_nonblocking():
    text = (ROOT / "scripts" / "run-hidden.vbs").read_text(encoding="utf-8")
    assert 'CreateObject("WScript.Shell")' in text
    assert "shell.Run cmd, 0, False" in text


def test_jnu_capture_watchdog_registration_is_hidden_and_keeps_variable_pc_policy():
    text = (ROOT / "scripts" / "register_jnu_capture_watchdog.ps1").read_text(
        encoding="utf-8"
    )
    assert "run-hidden.vbs" in text
    assert 'System32\\wscript.exe' in text
    assert 'New-ScheduledTaskAction -Execute $WScript' in text
    assert '"-WindowStyle" "Hidden"' in text
    assert "interval_minutes = 5" in text
    assert 'preferred_user_window = "18:55-22:00 Asia/Taipei (informational only)"' in text
    assert "early_or_late_capture_allowed = $true" in text
    assert "MARKET_AI_HUB_JNU_Capture_Stop_2205" in text
    assert "Unregister-ScheduledTask -TaskName $LegacyStopTaskName" in text
    assert "broker_order_action = $false" in text
    assert "New-ScheduledTaskAction -Execute $PowerShell" not in text


def test_c23_registration_source_matches_hidden_task_policy():
    text = (ROOT / "scripts" / "register_c23_terminal_close_task.ps1").read_text(
        encoding="utf-8"
    )
    assert "run-hidden.vbs" in text
    assert 'System32\\wscript.exe' in text
    assert 'New-ScheduledTaskAction -Execute $WScript' in text
    assert '"-WindowStyle" "Hidden"' in text
    assert "hidden_window = $true" in text
    assert "broker_order_action = $false" in text
    assert "New-ScheduledTaskAction -Execute $PowerShell" not in text
