"""
macOS launchd integration for persistent background scheduling.

Manages two launchd user agents:
  - com.bitcoin-monitor.fetch (periodic data fetching + alerts)
  - com.bitcoin-monitor.digest (weekly digest email)

Plist files are installed to ~/Library/LaunchAgents/
Log files go to ~/Library/Logs/bitcoin-monitor/
"""

import os
import plistlib
import subprocess
from pathlib import Path

FETCH_LABEL = "com.bitcoin-monitor.fetch"
DIGEST_LABEL = "com.bitcoin-monitor.digest"
PLIST_DIR = Path.home() / "Library" / "LaunchAgents"
LOG_DIR = Path.home() / "Library" / "Logs" / "bitcoin-monitor"


class LaunchdManager:
    def __init__(self, project_dir: str, python_path: str = None):
        """
        Args:
            project_dir: Absolute path to the Bitcoin project directory
            python_path: Absolute path to the Python interpreter (defaults to venv python)
        """
        self.project_dir = Path(project_dir).resolve()
        self.python_path = python_path or str(self.project_dir / "venv" / "bin" / "python")
        self.main_py = str(self.project_dir / "main.py")

    def generate_fetch_plist(self, interval_minutes: int = 15) -> dict:
        """Generate the fetch job plist dictionary."""
        return {
            "Label": FETCH_LABEL,
            "ProgramArguments": [
                self.python_path,
                self.main_py,
                "service", "run-fetch",
            ],
            "StartInterval": interval_minutes * 60,
            "RunAtLoad": True,
            "WorkingDirectory": str(self.project_dir),
            "EnvironmentVariables": self._get_env_vars(),
            "StandardOutPath": str(LOG_DIR / "fetch.log"),
            "StandardErrorPath": str(LOG_DIR / "fetch.log"),
            "Nice": 10,
            "ProcessType": "Background",
            "LowPriorityBackgroundIO": True,
        }

    def generate_digest_plist(self, day: int = 0, hour: int = 9) -> dict:
        """Generate the digest job plist dictionary."""
        return {
            "Label": DIGEST_LABEL,
            "ProgramArguments": [
                self.python_path,
                self.main_py,
                "service", "run-digest",
            ],
            "StartCalendarInterval": {
                "Weekday": day,
                "Hour": hour,
                "Minute": 0,
            },
            "WorkingDirectory": str(self.project_dir),
            "EnvironmentVariables": self._get_env_vars(),
            "StandardOutPath": str(LOG_DIR / "digest.log"),
            "StandardErrorPath": str(LOG_DIR / "digest.log"),
            "Nice": 10,
            "ProcessType": "Background",
        }

    def _get_env_vars(self) -> dict:
        """Collect environment variables to pass to launchd jobs."""
        env = {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": str(Path.home()),
            "PYTHONPATH": str(self.project_dir),
        }

        for key in ["BTC_MONITOR_SMTP_USER", "BTC_MONITOR_SMTP_PASS",
                     "BTC_MONITOR_DB_PATH", "BTC_MONITOR_LOG_LEVEL"]:
            val = os.environ.get(key)
            if val:
                env[key] = val

        return env

    def install(self, fetch_interval: int = 15, digest_day: int = 0,
                digest_hour: int = 9) -> dict:
        """
        Install both launchd jobs.

        Returns:
            {"fetch": "installed"|"error: ...", "digest": "installed"|"error: ..."}
        """
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        PLIST_DIR.mkdir(parents=True, exist_ok=True)

        results = {}

        # Fetch job
        fetch_plist_path = PLIST_DIR / f"{FETCH_LABEL}.plist"
        fetch_plist = self.generate_fetch_plist(fetch_interval)
        try:
            with open(fetch_plist_path, "wb") as f:
                plistlib.dump(fetch_plist, f)
            self._launchctl("load", str(fetch_plist_path))
            results["fetch"] = "installed"
        except Exception as e:
            results["fetch"] = f"error: {e}"

        # Digest job
        digest_plist_path = PLIST_DIR / f"{DIGEST_LABEL}.plist"
        digest_plist = self.generate_digest_plist(digest_day, digest_hour)
        try:
            with open(digest_plist_path, "wb") as f:
                plistlib.dump(digest_plist, f)
            self._launchctl("load", str(digest_plist_path))
            results["digest"] = "installed"
        except Exception as e:
            results["digest"] = f"error: {e}"

        return results

    def uninstall(self) -> dict:
        """
        Uninstall both launchd jobs.

        Returns:
            {"fetch": "removed"|"not installed"|"error: ...",
             "digest": "removed"|"not installed"|"error: ..."}
        """
        results = {}

        for label in [FETCH_LABEL, DIGEST_LABEL]:
            name = label.split(".")[-1]
            plist_path = PLIST_DIR / f"{label}.plist"

            if not plist_path.exists():
                results[name] = "not installed"
                continue

            try:
                self._launchctl("unload", str(plist_path))
                plist_path.unlink()
                results[name] = "removed"
            except Exception as e:
                results[name] = f"error: {e}"

        return results

    def status(self) -> dict:
        """Check if jobs are loaded and running."""
        results = {}
        for label in [FETCH_LABEL, DIGEST_LABEL]:
            name = label.split(".")[-1]
            try:
                output = subprocess.run(
                    ["launchctl", "list", label],
                    capture_output=True, text=True, timeout=5
                )
                if output.returncode == 0:
                    lines = output.stdout.strip().split("\n")
                    info = {}
                    for line in lines:
                        if "=" in line:
                            key, val = line.split("=", 1)
                            info[key.strip().strip('"')] = val.strip().strip('";')

                    pid = info.get("PID")
                    last_exit = info.get("LastExitStatus")

                    results[name] = {
                        "loaded": True,
                        "running": pid is not None and pid != "0",
                        "pid": int(pid) if pid and pid != "0" else None,
                        "last_exit": int(last_exit) if last_exit else None,
                    }
                else:
                    results[name] = {"loaded": False, "running": False,
                                     "pid": None, "last_exit": None}
            except Exception:
                results[name] = {"loaded": False, "running": False,
                                 "pid": None, "last_exit": None}

            # Check log for last run time
            log_path = LOG_DIR / f"{name}.log"
            if log_path.exists():
                try:
                    content = log_path.read_text()
                    lines = content.strip().split("\n")
                    if lines:
                        results[name]["last_log_line"] = lines[-1][:100]
                except Exception:
                    pass

        return results

    def get_logs(self, job: str = "all", lines: int = 50) -> str:
        """Read recent log output."""
        output = []
        jobs = [job] if job != "all" else ["fetch", "digest"]

        for j in jobs:
            log_path = LOG_DIR / f"{j}.log"
            if log_path.exists():
                content = log_path.read_text()
                log_lines = content.strip().split("\n")
                recent = log_lines[-lines:]
                output.append(f"=== {j.upper()} LOG (last {len(recent)} lines) ===")
                output.extend(recent)
                output.append("")
            else:
                output.append(f"=== {j.upper()} LOG ===")
                output.append("No log file yet. Job may not have run.")
                output.append("")

        return "\n".join(output)

    def _launchctl(self, action: str, plist_path: str):
        """Run launchctl load/unload."""
        result = subprocess.run(
            ["launchctl", action, plist_path],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0 and "already loaded" not in result.stderr.lower():
            raise RuntimeError(f"launchctl {action} failed: {result.stderr.strip()}")


def rotate_logs(max_size_mb: int = 10):
    """Rotate log files if they exceed max_size_mb.

    Truncates to last 1000 lines if file exceeds size limit.
    Called at the start of each fetch/digest cycle.
    """
    for log_name in ["fetch.log", "digest.log"]:
        log_path = LOG_DIR / log_name
        if not log_path.exists():
            continue
        size_mb = log_path.stat().st_size / (1024 * 1024)
        if size_mb > max_size_mb:
            lines = log_path.read_text().strip().split("\n")
            recent = lines[-1000:]
            log_path.write_text("\n".join(recent) + "\n")
