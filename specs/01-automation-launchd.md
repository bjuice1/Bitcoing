# 01 — Automation via macOS launchd

## Overview

The Bitcoin Cycle Monitor currently requires manual execution of every command. The `MonitorScheduler` class uses Python's `schedule` library in a daemon thread, but it only runs while a terminal session is active — close the terminal, monitoring stops. There is no persistent background process, no crash recovery, and no scheduled digest delivery.

This document specifies a launchd-based automation layer that runs two persistent jobs on macOS:

1. **Fetch job** (every 15 minutes) — fetches data, evaluates alerts, sends notifications
2. **Digest job** (every Sunday at 9:00 AM) — generates and emails the weekly digest

Both survive reboots, recover from crashes, and log output to `~/Library/Logs/`.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    macOS launchd                                 │
│                                                                  │
│  Job 1: com.bitcoin-monitor.fetch                               │
│  ┌────────────────────────────────────────────────────────┐     │
│  │  Every 15 minutes:                                     │     │
│  │  python main.py service run-fetch                      │     │
│  │                                                        │     │
│  │  → Fetch data from 5 APIs                              │     │
│  │  → Store snapshot in SQLite                            │     │
│  │  → Evaluate alert rules                                │     │
│  │  → Send macOS notifications (02-macos-notifications)   │     │
│  │  → Send CRITICAL alert emails (03-email-digest)        │     │
│  │  → Check smart alerts (DCA reminders, dips, streaks)   │     │
│  │  → Exit 0                                              │     │
│  └────────────────────────────────────────────────────────┘     │
│                                                                  │
│  Job 2: com.bitcoin-monitor.digest                              │
│  ┌────────────────────────────────────────────────────────┐     │
│  │  Every Sunday at 09:00 local time:                     │     │
│  │  python main.py service run-digest                     │     │
│  │                                                        │     │
│  │  → Generate weekly digest                              │     │
│  │  → Generate charts (Matplotlib PNGs)                   │     │
│  │  → Send digest email (03-email-digest)                 │     │
│  │  → Send macOS notification: "Digest sent"              │     │
│  │  → Exit 0                                              │     │
│  └────────────────────────────────────────────────────────┘     │
│                                                                  │
│  Logging:                                                        │
│  ~/Library/Logs/bitcoin-monitor/fetch.log                       │
│  ~/Library/Logs/bitcoin-monitor/digest.log                      │
│                                                                  │
│  Management:                                                     │
│  python main.py service install    (create + load plists)       │
│  python main.py service uninstall  (unload + remove plists)     │
│  python main.py service status     (check if loaded + running)  │
│  python main.py service logs       (tail recent log output)     │
└─────────────────────────────────────────────────────────────────┘
```

**Dependencies:**
- `02-macos-notifications.md` — fetch job dispatches alerts to DesktopChannel
- `03-email-digest.md` — digest job calls EmailSender; fetch job calls EmailChannel for CRITICAL alerts

## Specification

### 1. New CLI Command Group: `service`

Add to `main.py`:

```python
@cli.group()
def service():
    """Manage background automation (macOS launchd)."""
    pass

@service.command("install")
@click.option("--fetch-interval", default=15, type=int, help="Fetch interval in minutes")
@click.option("--digest-day", default=0, type=int, help="Digest day (0=Sunday, 1=Monday, ...)")
@click.option("--digest-hour", default=9, type=int, help="Digest hour (24h format)")
@click.pass_context
def service_install(ctx, fetch_interval, digest_day, digest_hour):
    """Install launchd jobs for background monitoring."""

@service.command("uninstall")
@click.pass_context
def service_uninstall(ctx):
    """Remove launchd jobs."""

@service.command("status")
@click.pass_context
def service_status(ctx):
    """Check if background jobs are running."""

@service.command("logs")
@click.option("--job", type=click.Choice(["fetch", "digest", "all"]), default="all")
@click.option("--lines", default=50, type=int, help="Number of lines to show")
@click.pass_context
def service_logs(ctx, job, lines):
    """Show recent log output."""

@service.command("run-fetch")
@click.pass_context
def service_run_fetch(ctx):
    """Single fetch cycle (called by launchd, not meant for manual use)."""

@service.command("run-digest")
@click.pass_context
def service_run_digest(ctx):
    """Single digest cycle (called by launchd, not meant for manual use)."""
```

### 2. New Module: `service/launchd.py`

```python
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
        """
        Generate the fetch job plist dictionary.

        Key behaviors:
          - StartInterval: runs every N minutes
          - RunAtLoad: runs immediately when loaded (first fetch on install)
          - WorkingDirectory: project root (so relative paths work)
          - EnvironmentVariables: inherits user env (for SMTP credentials)
          - StandardOutPath / StandardErrorPath: log files
          - Nice: 10 (lower priority than interactive processes)
        """
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
        """
        Generate the digest job plist dictionary.

        Key behaviors:
          - StartCalendarInterval: fires at specific day/hour
          - Day 0 = Sunday (launchd uses 0=Sunday convention)
          - Hour in 24h format (9 = 9:00 AM)
          - If the Mac was asleep at the scheduled time, launchd runs it
            when the Mac wakes up (default behavior).
        """
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
        """
        Collect environment variables to pass to launchd jobs.

        Includes:
          - PATH (so python and system commands work)
          - HOME (for config file resolution)
          - BTC_MONITOR_SMTP_USER / BTC_MONITOR_SMTP_PASS (if set)
          - PYTHONPATH (so imports work)
        """
        env = {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": str(Path.home()),
            "PYTHONPATH": str(self.project_dir),
        }

        # Pass through email credentials if set
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

        Steps:
          1. Create log directory
          2. Write plist files to ~/Library/LaunchAgents/
          3. Load both jobs via launchctl
          4. Verify they're loaded

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

        Steps:
          1. Unload jobs via launchctl (stops them if running)
          2. Delete plist files
          3. Optionally keep log files (don't delete logs)

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
        """
        Check if jobs are loaded and running.

        Returns:
            {
                "fetch": {"loaded": bool, "running": bool, "last_exit": int|None,
                          "pid": int|None, "last_run": str|None},
                "digest": {"loaded": bool, "running": bool, "last_exit": int|None,
                           "pid": int|None, "next_run": str|None},
            }

        Implementation:
          Uses `launchctl list | grep com.bitcoin-monitor` to check loaded status.
          Parses output for PID and last exit status.
          Reads log files for last run timestamp.
        """
        results = {}
        for label in [FETCH_LABEL, DIGEST_LABEL]:
            name = label.split(".")[-1]
            try:
                output = subprocess.run(
                    ["launchctl", "list", label],
                    capture_output=True, text=True, timeout=5
                )
                if output.returncode == 0:
                    # Parse launchctl output for PID and status
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
                    # Read last few lines of log to find timestamp
                    content = log_path.read_text()
                    lines = content.strip().split("\n")
                    if lines:
                        results[name]["last_log_line"] = lines[-1][:100]
                except Exception:
                    pass

        return results

    def get_logs(self, job: str = "all", lines: int = 50) -> str:
        """
        Read recent log output.

        Args:
            job: "fetch", "digest", or "all"
            lines: Number of lines to return

        Returns:
            Log content as string.
        """
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
```

### 3. Run-Fetch Implementation

The `run-fetch` command is the core automation entry point. Called by launchd every 15 minutes.

```python
@service.command("run-fetch")
@click.pass_context
def service_run_fetch(ctx):
    """
    Single fetch cycle — called by launchd.

    Steps:
      1. Fetch fresh data from all APIs
      2. Store snapshot in database
      3. Evaluate all alert rules against the snapshot
      4. Dispatch triggered alerts to channels:
         - DesktopChannel (macOS notifications, see 02-macos-notifications.md)
         - FileChannel (JSONL log)
         - EmailChannel (CRITICAL only, see 03-email-digest.md)
      5. Check smart alerts (DCA reminders, dip opportunities)
      6. Log summary and exit

    Exit codes:
      0 — success (even if some APIs failed, as long as we got a snapshot)
      1 — complete failure (no data fetched, database error, etc.)

    This command is designed to be silent on success (logs only).
    Output goes to ~/Library/Logs/bitcoin-monitor/fetch.log via launchd.
    """
    import logging
    from datetime import datetime

    logger = logging.getLogger("bitcoin-monitor")
    logger.info(f"=== Fetch cycle started at {datetime.now().isoformat()} ===")

    c = ctx.obj
    monitor = c["monitor"]
    alert_engine = c["alert_engine"]
    smart_engine = c.get("smart_engine")

    try:
        # 1. Fetch and store
        snapshot = monitor.fetch_and_store()
        if snapshot is None:
            logger.error("Fetch returned no data")
            raise SystemExit(1)

        logger.info(f"Fetched: BTC ${snapshot.price.price_usd:,.0f}, "
                    f"F&G {snapshot.sentiment.fear_greed_value}")

        # 2. Evaluate alert rules
        triggered = alert_engine.evaluate_rules(snapshot)
        if triggered:
            logger.info(f"Alerts triggered: {len(triggered)}")
            for alert in triggered:
                logger.info(f"  [{alert.severity}] {alert.rule_name}: {alert.message}")
        else:
            logger.info("No alerts triggered")

        # 3. Evaluate composite signals
        composites = alert_engine.evaluate_composites(snapshot, triggered)
        if composites:
            logger.info(f"Composite signals: {len(composites)}")

        # 4. Check smart alerts
        if smart_engine:
            smart_alerts = smart_engine.check_all(
                snapshot=snapshot,
                portfolio=c.get("dca_portfolio"),
                goal=c.get("goal_tracker"),
            )
            if smart_alerts:
                logger.info(f"Smart alerts: {len(smart_alerts)}")
                # Dispatch smart alerts to channels
                for sa in smart_alerts:
                    for channel in alert_engine.channels:
                        try:
                            channel.send(sa)
                        except Exception as e:
                            logger.warning(f"Channel dispatch failed: {e}")

        logger.info(f"=== Fetch cycle completed successfully ===\n")

    except SystemExit:
        raise
    except Exception as e:
        logger.error(f"Fetch cycle failed: {e}", exc_info=True)
        raise SystemExit(1)
```

### 4. Run-Digest Implementation

```python
@service.command("run-digest")
@click.pass_context
def service_run_digest(ctx):
    """
    Single digest cycle — called by launchd on Sundays.

    Steps:
      1. Generate weekly digest data
      2. Generate charts (Matplotlib PNGs to memory)
      3. Assemble email with embedded charts
      4. Send via SMTP
      5. Send macOS notification: "Weekly digest sent"
      6. Log summary and exit

    Exit codes:
      0 — success
      1 — failure (email not configured, SMTP error, etc.)
    """
    import logging
    from datetime import datetime

    logger = logging.getLogger("bitcoin-monitor")
    logger.info(f"=== Digest cycle started at {datetime.now().isoformat()} ===")

    c = ctx.obj
    config = c["config"]

    # Check if email is configured
    email_config = config.get("email", {})
    if not email_config.get("enabled") or not email_config.get("digest_enabled"):
        logger.info("Email digest not enabled — skipping")
        raise SystemExit(0)

    try:
        from notifications.email_sender import EmailSender, build_digest_email

        sender = EmailSender(config)
        if not sender.is_configured():
            logger.warning("Email not fully configured — skipping digest")
            raise SystemExit(0)

        # Generate digest + charts
        logger.info("Generating weekly digest...")
        html, charts = build_digest_email(
            weekly_digest=c["weekly_digest"],
            chart_generator=c["chart_gen"],
            projector=c["projector"],
            goal_tracker=c.get("goal_tracker"),
            current_price=c["monitor"].get_current_status().price.price_usd,
            monthly_dca=config.get("dca", {}).get("default_amount", 200),
        )

        logger.info(f"Digest generated: {len(html)} chars HTML, {len(charts)} charts")

        # Send email
        result = sender.send_digest(html, chart_images=charts)
        if result:
            logger.info(f"Digest email sent to {sender.to_address}")

            # Desktop notification
            try:
                import subprocess as sp
                sp.run(["osascript", "-e",
                        'display notification "Weekly digest sent to your inbox" '
                        'with title "Bitcoin Monitor" sound name "Purr"'],
                       capture_output=True, timeout=5)
            except Exception:
                pass  # Notification is nice-to-have
        else:
            logger.error("Failed to send digest email")
            raise SystemExit(1)

        logger.info(f"=== Digest cycle completed successfully ===\n")

    except SystemExit:
        raise
    except Exception as e:
        logger.error(f"Digest cycle failed: {e}", exc_info=True)
        raise SystemExit(1)
```

### 5. Service Install Implementation

```python
@service.command("install")
@click.option("--fetch-interval", default=15, type=int, help="Fetch interval in minutes (default: 15)")
@click.option("--digest-day", default=0, type=int, help="Digest day: 0=Sun, 1=Mon, ... (default: 0)")
@click.option("--digest-hour", default=9, type=int, help="Digest hour in 24h format (default: 9)")
@click.pass_context
def service_install(ctx, fetch_interval, digest_day, digest_hour):
    """Install launchd jobs for background monitoring."""
    from service.launchd import LaunchdManager

    project_dir = os.path.dirname(os.path.abspath(__file__))
    manager = LaunchdManager(project_dir)

    console.print("\n[btc]Installing Bitcoin Monitor background services...[/]\n")

    results = manager.install(
        fetch_interval=fetch_interval,
        digest_day=digest_day,
        digest_hour=digest_hour,
    )

    day_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

    for job, status in results.items():
        if status == "installed":
            console.print(f"  [bull]{job}:[/] installed and loaded")
        else:
            console.print(f"  [bear]{job}:[/] {status}")

    console.print(f"\n  Fetch: every {fetch_interval} minutes")
    console.print(f"  Digest: {day_names[digest_day]}s at {digest_hour:02d}:00")
    console.print(f"  Logs: ~/Library/Logs/bitcoin-monitor/")
    console.print(f"\n  Run [dim]python main.py service status[/] to verify.")
    console.print(f"  Run [dim]python main.py service logs[/] to view output.\n")
```

### 6. Alert Channel Registration Update

In `main.py`, update the channel registration to include EmailChannel when configured:

```python
# Current channel setup (approximately):
channels = [ConsoleChannel(), FileChannel()]
if config.get("alerts", {}).get("desktop_notifications", True):
    channels.append(DesktopChannel(config))

# Updated: add EmailChannel
channels = [FileChannel()]  # Always log to file

# Console only if running interactively (not from launchd)
import sys
if sys.stdout.isatty():
    channels.append(ConsoleChannel())

# Desktop notifications (see 02-macos-notifications.md)
if config.get("notifications", {}).get("enabled", True):
    channels.append(DesktopChannel(config))

# Email for CRITICAL alerts (see 03-email-digest.md)
if config.get("email", {}).get("critical_alerts_enabled", False):
    from alerts.channels import EmailChannel
    channels.append(EmailChannel(config))
```

The `sys.stdout.isatty()` check ensures ConsoleChannel isn't used when running from launchd (where stdout goes to a log file).

### 7. Configuration Additions

Add to `config/default_config.yaml`:

```yaml
service:
  fetch_interval_minutes: 15
  digest_day: 0          # 0=Sunday
  digest_hour: 9         # 24h format
  log_retention_days: 30 # How long to keep log files
```

### 8. Log Rotation

launchd log files can grow indefinitely. Add a simple rotation mechanism:

```python
def rotate_logs(max_size_mb: int = 10):
    """
    Rotate log files if they exceed max_size_mb.
    Called at the start of each fetch/digest cycle.

    Strategy: truncate to last 1000 lines if file exceeds size limit.
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
```

## Benefits

| Decision | Why | Alternative Considered |
|----------|-----|----------------------|
| **launchd over cron** | Native macOS. Survives reboots. Runs missed jobs on wake. Built-in logging. Process management. | cron — no missed-job recovery, no process management, less macOS-native |
| **launchd over systemd** | macOS doesn't have systemd. launchd is the macOS equivalent. | systemd — Linux only |
| **Two jobs over one** | Fetch runs every 15 min (fast, lightweight). Digest runs weekly (slow, generates charts). Separation of concerns. | Single job that checks "is it Sunday?" — harder to debug, mixed concerns |
| **Exit-after-run over daemon** | launchd manages the lifecycle. No long-running Python process consuming RAM. Each run is clean. | Daemon mode — stays in memory, can accumulate leaks, harder to update |
| **RunAtLoad: true** | First fetch happens immediately on install. User gets instant feedback that it's working. | RunAtLoad: false — user has to wait 15 minutes for first data |
| **Nice: 10** | Lower priority than interactive processes. Monitor shouldn't slow down normal work. | Nice: 0 — competes with user apps for CPU |
| **Environment passthrough** | SMTP credentials via env vars work in launchd (EnvironmentVariables key). | No env passthrough — forces credentials into config file |

## Expectations

- **Fetch job frequency:** Runs every 15 minutes (±30 seconds, launchd scheduling precision)
- **Fetch job duration:** Under 15 seconds per cycle (API fetches + alert evaluation)
- **Digest job:** Fires every Sunday at 09:00 local time (or on wake if Mac was asleep)
- **Digest job duration:** Under 30 seconds (chart generation + email send)
- **Memory usage:** Under 100 MB per run (Python process exits after each cycle)
- **Boot survival:** Jobs survive macOS restart (plist in ~/Library/LaunchAgents)
- **Sleep recovery:** launchd fires missed StartInterval jobs immediately on wake. StartCalendarInterval fires on wake if the scheduled time was missed.
- **Log size:** Under 10 MB per log file with rotation. ~100 bytes per fetch cycle log entry.
- **Install time:** Under 2 seconds (`python main.py service install`)

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| launchd permission issues (macOS security) | Medium (Ventura+ tightened permissions) | High — jobs don't run | Document: may need to approve in System Settings > Privacy. `service status` shows if loaded. |
| Python venv path changes | Low | High — jobs fail to start | Plist uses absolute paths. If user moves project, they must `service uninstall && service install`. |
| SMTP creds not available in launchd env | Medium | Medium — digest fails | `_get_env_vars()` explicitly passes through `BTC_MONITOR_SMTP_*` vars. Document: "Set env vars in your shell profile before installing." |
| API rate limiting during heavy fetch cycles | Low (only 5 requests per 15 min) | Low — some metrics missing | Existing rate limiter and retry logic handles this. Partial snapshots are stored. |
| Log files fill disk | Very low (rotation in place) | Low | `rotate_logs()` called at start of each cycle. Max 10 MB per log. |
| User forgets jobs are running after project change | Medium | Low — stale data fetched | `service status` prints clear info. `service uninstall` is easy. |

## Results Criteria

1. **`python main.py service install`** creates 2 plist files in `~/Library/LaunchAgents/` and loads them
2. **`python main.py service status`** shows both jobs as "loaded"
3. **After 15 minutes,** `~/Library/Logs/bitcoin-monitor/fetch.log` contains a successful fetch entry
4. **`python main.py service logs`** shows recent log output
5. **After macOS restart,** `python main.py service status` still shows both jobs loaded
6. **On Sunday at 09:00,** digest email arrives in inbox (if email is configured)
7. **CRITICAL alert triggers macOS notification** (via launchd fetch job, not manual run)
8. **`python main.py service uninstall`** removes plist files and unloads jobs
9. **After uninstall,** `python main.py service status` shows "not installed"
10. **All 165 existing tests still pass** — service module is additive

## Files Changed

| File | Change Type | Description |
|------|------------|-------------|
| `service/__init__.py` | **NEW** | Package init |
| `service/launchd.py` | **NEW** | LaunchdManager class with plist generation, install, uninstall, status, logs |
| `main.py` | **MODIFY** | Add `service` command group with install, uninstall, status, logs, run-fetch, run-digest |
| `config/default_config.yaml` | **MODIFY** | Add `service:` section |
| `tests/test_service.py` | **NEW** | Tests for plist generation, path resolution, status parsing (mock launchctl) |
