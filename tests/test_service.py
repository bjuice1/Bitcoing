"""Tests for launchd service management."""
import os
import plistlib
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from service.launchd import (
    LaunchdManager, FETCH_LABEL, DIGEST_LABEL,
    PLIST_DIR, LOG_DIR, rotate_logs,
)


@pytest.fixture
def manager(tmp_path):
    return LaunchdManager(
        project_dir=str(tmp_path / "project"),
        python_path="/usr/bin/python3",
    )


class TestPlistGeneration:
    def test_fetch_plist_has_correct_label(self, manager):
        plist = manager.generate_fetch_plist()
        assert plist["Label"] == FETCH_LABEL

    def test_fetch_plist_default_interval(self, manager):
        plist = manager.generate_fetch_plist()
        assert plist["StartInterval"] == 15 * 60

    def test_fetch_plist_custom_interval(self, manager):
        plist = manager.generate_fetch_plist(interval_minutes=5)
        assert plist["StartInterval"] == 5 * 60

    def test_fetch_plist_run_at_load(self, manager):
        plist = manager.generate_fetch_plist()
        assert plist["RunAtLoad"] is True

    def test_fetch_plist_program_arguments(self, manager):
        plist = manager.generate_fetch_plist()
        args = plist["ProgramArguments"]
        assert args[0] == "/usr/bin/python3"
        assert args[-2] == "service"
        assert args[-1] == "run-fetch"

    def test_fetch_plist_nice_priority(self, manager):
        plist = manager.generate_fetch_plist()
        assert plist["Nice"] == 10

    def test_fetch_plist_background_process_type(self, manager):
        plist = manager.generate_fetch_plist()
        assert plist["ProcessType"] == "Background"
        assert plist["LowPriorityBackgroundIO"] is True

    def test_fetch_plist_log_paths(self, manager):
        plist = manager.generate_fetch_plist()
        assert plist["StandardOutPath"].endswith("fetch.log")
        assert plist["StandardErrorPath"].endswith("fetch.log")

    def test_digest_plist_has_correct_label(self, manager):
        plist = manager.generate_digest_plist()
        assert plist["Label"] == DIGEST_LABEL

    def test_digest_plist_calendar_interval_defaults(self, manager):
        plist = manager.generate_digest_plist()
        cal = plist["StartCalendarInterval"]
        assert cal["Weekday"] == 0  # Sunday
        assert cal["Hour"] == 9
        assert cal["Minute"] == 0

    def test_digest_plist_custom_schedule(self, manager):
        plist = manager.generate_digest_plist(day=1, hour=18)
        cal = plist["StartCalendarInterval"]
        assert cal["Weekday"] == 1  # Monday
        assert cal["Hour"] == 18

    def test_digest_plist_program_arguments(self, manager):
        plist = manager.generate_digest_plist()
        args = plist["ProgramArguments"]
        assert args[-1] == "run-digest"

    def test_digest_plist_log_paths(self, manager):
        plist = manager.generate_digest_plist()
        assert plist["StandardOutPath"].endswith("digest.log")
        assert plist["StandardErrorPath"].endswith("digest.log")

    def test_digest_plist_no_low_priority_io(self, manager):
        plist = manager.generate_digest_plist()
        assert "LowPriorityBackgroundIO" not in plist

    def test_plist_serializable(self, manager):
        """Both plists should serialize as valid plist XML."""
        for plist in [manager.generate_fetch_plist(), manager.generate_digest_plist()]:
            data = plistlib.dumps(plist)
            assert b"<?xml" in data
            roundtrip = plistlib.loads(data)
            assert roundtrip["Label"] == plist["Label"]


class TestPathResolution:
    def test_project_dir_resolved(self, tmp_path):
        mgr = LaunchdManager(str(tmp_path / "project"))
        assert mgr.project_dir.is_absolute()

    def test_default_python_path(self, tmp_path):
        mgr = LaunchdManager(str(tmp_path / "project"))
        assert mgr.python_path.endswith("venv/bin/python")

    def test_custom_python_path(self, tmp_path):
        mgr = LaunchdManager(str(tmp_path), python_path="/opt/python/bin/python3")
        assert mgr.python_path == "/opt/python/bin/python3"

    def test_main_py_path(self, tmp_path):
        mgr = LaunchdManager(str(tmp_path / "project"))
        assert mgr.main_py.endswith("main.py")

    def test_working_directory_in_plist(self, manager):
        plist = manager.generate_fetch_plist()
        assert plist["WorkingDirectory"] == str(manager.project_dir)


class TestEnvironmentVariables:
    def test_basic_env_vars(self, manager):
        plist = manager.generate_fetch_plist()
        env = plist["EnvironmentVariables"]
        assert "PATH" in env
        assert "HOME" in env
        assert "PYTHONPATH" in env

    def test_pythonpath_is_project_dir(self, manager):
        plist = manager.generate_fetch_plist()
        env = plist["EnvironmentVariables"]
        assert env["PYTHONPATH"] == str(manager.project_dir)

    def test_smtp_vars_passed_when_set(self, manager):
        with patch.dict(os.environ, {
            "BTC_MONITOR_SMTP_USER": "test_user",
            "BTC_MONITOR_SMTP_PASS": "test_pass",
        }):
            plist = manager.generate_fetch_plist()
            env = plist["EnvironmentVariables"]
            assert env["BTC_MONITOR_SMTP_USER"] == "test_user"
            assert env["BTC_MONITOR_SMTP_PASS"] == "test_pass"

    def test_smtp_vars_omitted_when_unset(self, manager):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("BTC_MONITOR_SMTP_USER", None)
            os.environ.pop("BTC_MONITOR_SMTP_PASS", None)
            plist = manager.generate_fetch_plist()
            env = plist["EnvironmentVariables"]
            assert "BTC_MONITOR_SMTP_USER" not in env
            assert "BTC_MONITOR_SMTP_PASS" not in env

    def test_optional_vars_passed(self, manager):
        with patch.dict(os.environ, {"BTC_MONITOR_LOG_LEVEL": "DEBUG"}):
            plist = manager.generate_fetch_plist()
            env = plist["EnvironmentVariables"]
            assert env["BTC_MONITOR_LOG_LEVEL"] == "DEBUG"


class TestInstallUninstall:
    @patch("service.launchd.LaunchdManager._launchctl")
    @patch("service.launchd.PLIST_DIR")
    @patch("service.launchd.LOG_DIR")
    def test_install_creates_both_plists(self, mock_log_dir, mock_plist_dir, mock_launchctl, tmp_path):
        mock_plist_dir.__truediv__ = lambda self, x: tmp_path / x
        mock_plist_dir.mkdir = MagicMock()
        mock_log_dir.mkdir = MagicMock()

        mgr = LaunchdManager(str(tmp_path), python_path="/usr/bin/python3")
        results = mgr.install()

        assert results["fetch"] == "installed"
        assert results["digest"] == "installed"
        assert mock_launchctl.call_count == 2

    @patch("service.launchd.LaunchdManager._launchctl")
    @patch("service.launchd.PLIST_DIR")
    @patch("service.launchd.LOG_DIR")
    def test_install_writes_valid_plists(self, mock_log_dir, mock_plist_dir, mock_launchctl, tmp_path):
        mock_plist_dir.__truediv__ = lambda self, x: tmp_path / x
        mock_plist_dir.mkdir = MagicMock()
        mock_log_dir.mkdir = MagicMock()

        mgr = LaunchdManager(str(tmp_path), python_path="/usr/bin/python3")
        mgr.install()

        fetch_plist = tmp_path / f"{FETCH_LABEL}.plist"
        digest_plist = tmp_path / f"{DIGEST_LABEL}.plist"
        assert fetch_plist.exists()
        assert digest_plist.exists()

        with open(fetch_plist, "rb") as f:
            data = plistlib.load(f)
            assert data["Label"] == FETCH_LABEL

    @patch("service.launchd.LaunchdManager._launchctl")
    @patch("service.launchd.PLIST_DIR")
    @patch("service.launchd.LOG_DIR")
    def test_install_with_custom_interval(self, mock_log_dir, mock_plist_dir, mock_launchctl, tmp_path):
        mock_plist_dir.__truediv__ = lambda self, x: tmp_path / x
        mock_plist_dir.mkdir = MagicMock()
        mock_log_dir.mkdir = MagicMock()

        mgr = LaunchdManager(str(tmp_path), python_path="/usr/bin/python3")
        mgr.install(fetch_interval=5, digest_day=3, digest_hour=20)

        fetch_plist = tmp_path / f"{FETCH_LABEL}.plist"
        with open(fetch_plist, "rb") as f:
            data = plistlib.load(f)
            assert data["StartInterval"] == 300

    @patch("service.launchd.LaunchdManager._launchctl")
    def test_uninstall_removes_plists(self, mock_launchctl, tmp_path):
        # Create fake plist files
        fetch_path = tmp_path / f"{FETCH_LABEL}.plist"
        digest_path = tmp_path / f"{DIGEST_LABEL}.plist"
        fetch_path.write_text("fake")
        digest_path.write_text("fake")

        with patch("service.launchd.PLIST_DIR", tmp_path):
            mgr = LaunchdManager(str(tmp_path), python_path="/usr/bin/python3")
            results = mgr.uninstall()

        assert results["fetch"] == "removed"
        assert results["digest"] == "removed"
        assert not fetch_path.exists()
        assert not digest_path.exists()

    @patch("service.launchd.LaunchdManager._launchctl")
    def test_uninstall_not_installed(self, mock_launchctl, tmp_path):
        with patch("service.launchd.PLIST_DIR", tmp_path):
            mgr = LaunchdManager(str(tmp_path), python_path="/usr/bin/python3")
            results = mgr.uninstall()

        assert results["fetch"] == "not installed"
        assert results["digest"] == "not installed"


class TestStatus:
    @patch("subprocess.run")
    def test_status_loaded(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='"PID" = 1234;\n"LastExitStatus" = 0;\n',
        )
        mgr = LaunchdManager("/tmp/test", python_path="/usr/bin/python3")
        with patch("service.launchd.LOG_DIR", Path("/nonexistent")):
            result = mgr.status()

        assert result["fetch"]["loaded"] is True
        assert result["fetch"]["running"] is True
        assert result["fetch"]["pid"] == 1234

    @patch("subprocess.run")
    def test_status_not_loaded(self, mock_run):
        mock_run.return_value = MagicMock(returncode=113, stdout="", stderr="")
        mgr = LaunchdManager("/tmp/test", python_path="/usr/bin/python3")
        with patch("service.launchd.LOG_DIR", Path("/nonexistent")):
            result = mgr.status()

        assert result["fetch"]["loaded"] is False
        assert result["fetch"]["running"] is False

    @patch("subprocess.run")
    def test_status_with_log(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='"PID" = 0;\n"LastExitStatus" = 0;\n',
        )
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        (log_dir / "fetch.log").write_text("=== Fetch completed ===\n")
        (log_dir / "digest.log").write_text("=== Digest completed ===\n")

        mgr = LaunchdManager("/tmp/test", python_path="/usr/bin/python3")
        with patch("service.launchd.LOG_DIR", log_dir):
            result = mgr.status()

        assert "last_log_line" in result["fetch"]
        assert "Fetch completed" in result["fetch"]["last_log_line"]

    @patch("subprocess.run")
    def test_status_exception_handling(self, mock_run):
        mock_run.side_effect = Exception("timeout")
        mgr = LaunchdManager("/tmp/test", python_path="/usr/bin/python3")
        with patch("service.launchd.LOG_DIR", Path("/nonexistent")):
            result = mgr.status()

        assert result["fetch"]["loaded"] is False
        assert result["digest"]["loaded"] is False


class TestGetLogs:
    def test_get_logs_no_files(self, tmp_path):
        mgr = LaunchdManager(str(tmp_path), python_path="/usr/bin/python3")
        with patch("service.launchd.LOG_DIR", tmp_path):
            output = mgr.get_logs()

        assert "No log file yet" in output

    def test_get_logs_with_content(self, tmp_path):
        (tmp_path / "fetch.log").write_text("line1\nline2\nline3\n")
        mgr = LaunchdManager(str(tmp_path), python_path="/usr/bin/python3")
        with patch("service.launchd.LOG_DIR", tmp_path):
            output = mgr.get_logs(job="fetch")

        assert "FETCH LOG" in output
        assert "line1" in output
        assert "line3" in output

    def test_get_logs_respects_line_limit(self, tmp_path):
        lines = [f"line{i}" for i in range(100)]
        (tmp_path / "fetch.log").write_text("\n".join(lines))
        mgr = LaunchdManager(str(tmp_path), python_path="/usr/bin/python3")
        with patch("service.launchd.LOG_DIR", tmp_path):
            output = mgr.get_logs(job="fetch", lines=5)

        assert "line95" in output
        assert "line99" in output
        assert "line0" not in output

    def test_get_logs_all_jobs(self, tmp_path):
        (tmp_path / "fetch.log").write_text("fetch data\n")
        (tmp_path / "digest.log").write_text("digest data\n")
        mgr = LaunchdManager(str(tmp_path), python_path="/usr/bin/python3")
        with patch("service.launchd.LOG_DIR", tmp_path):
            output = mgr.get_logs(job="all")

        assert "FETCH LOG" in output
        assert "DIGEST LOG" in output


class TestLogRotation:
    def test_rotate_small_file_untouched(self, tmp_path):
        log = tmp_path / "fetch.log"
        log.write_text("small\n")
        with patch("service.launchd.LOG_DIR", tmp_path):
            rotate_logs(max_size_mb=10)
        assert log.read_text() == "small\n"

    def test_rotate_large_file_truncated(self, tmp_path):
        log = tmp_path / "fetch.log"
        # Write > 1MB of data
        lines = [f"line {i}: " + "x" * 100 for i in range(20000)]
        log.write_text("\n".join(lines))
        assert log.stat().st_size > 1_000_000

        with patch("service.launchd.LOG_DIR", tmp_path):
            rotate_logs(max_size_mb=1)

        content = log.read_text()
        remaining_lines = content.strip().split("\n")
        assert len(remaining_lines) == 1000

    def test_rotate_missing_file_no_error(self, tmp_path):
        with patch("service.launchd.LOG_DIR", tmp_path):
            rotate_logs()  # Should not raise


class TestLaunchctl:
    @patch("subprocess.run")
    def test_launchctl_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        mgr = LaunchdManager("/tmp/test", python_path="/usr/bin/python3")
        mgr._launchctl("load", "/tmp/test.plist")
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_launchctl_already_loaded_ignored(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="Already loaded")
        mgr = LaunchdManager("/tmp/test", python_path="/usr/bin/python3")
        mgr._launchctl("load", "/tmp/test.plist")  # Should not raise

    @patch("subprocess.run")
    def test_launchctl_failure_raises(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="Permission denied")
        mgr = LaunchdManager("/tmp/test", python_path="/usr/bin/python3")
        with pytest.raises(RuntimeError, match="Permission denied"):
            mgr._launchctl("load", "/tmp/test.plist")
