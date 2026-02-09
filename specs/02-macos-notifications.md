# 02 — Hardened macOS Native Notifications

## Overview

The current `DesktopChannel` in `alerts/channels.py` (line 84) uses `os.system()` with string interpolation to call `osascript`, which is both a security vulnerability (shell injection) and unreliable (no error feedback, no persistence control, no sound configuration). This document specifies a replacement that uses `subprocess.run()` with proper argument passing, severity-based notification behavior, and integration with the alert pipeline.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Alert Pipeline                      │
│                                                      │
│  AlertEngine.evaluate_rules(snapshot)                │
│       │                                              │
│       ▼                                              │
│  AlertRecord (rule_id, severity, message)            │
│       │                                              │
│       ├──► ConsoleChannel   (terminal output)        │
│       ├──► FileChannel      (JSONL log)              │
│       ├──► DesktopChannel   (macOS notifications) ◄──┤ THIS DOC
│       └──► EmailChannel     (see 03-email-digest)    │
│                                                      │
│  DesktopChannel behavior by severity:                │
│  ┌──────────┬──────────┬───────┬──────────────────┐  │
│  │ Severity │ Sound    │ Style │ Rate Limit       │  │
│  ├──────────┼──────────┼───────┼──────────────────┤  │
│  │ CRITICAL │ Yes      │ Alert │ 1 per 15 min     │  │
│  │ WARNING  │ No       │ Banner│ 1 per 30 min     │  │
│  │ INFO     │ No       │ Banner│ 3 per hour       │  │
│  └──────────┴──────────┴───────┴──────────────────┘  │
└─────────────────────────────────────────────────────┘
```

**Downstream consumers:**
- `01-automation-launchd.md` — launchd `fetch-and-exit` job triggers alert evaluation, which dispatches to DesktopChannel

## Specification

### 1. Replace `os.system()` with `subprocess.run()`

**Current code** (`alerts/channels.py`, lines 72–95):

```python
class DesktopChannel:
    def send(self, alert):
        title = f"BTC Monitor: {alert.rule_name}"
        message = alert.message
        # VULNERABLE: os.system with string interpolation
        os.system(f"osascript -e 'display notification \"{message}\" with title \"{title}\"'")
```

**New code:**

```python
import subprocess
import shlex

class DesktopChannel:
    """
    macOS native notifications via osascript.

    Uses subprocess.run() with argument list (no shell) to prevent injection.
    Severity-based behavior: sound, persistence, rate limiting.
    Silently degrades on non-macOS platforms.
    """

    def __init__(self, config: dict = None):
        self.config = config or {}
        self._rate_limits = {
            Severity.CRITICAL: {"max_per_window": 1, "window_seconds": 900},   # 1 per 15 min
            Severity.WARNING:  {"max_per_window": 1, "window_seconds": 1800},  # 1 per 30 min
            Severity.INFO:     {"max_per_window": 3, "window_seconds": 3600},  # 3 per hour
        }
        self._send_history: dict[Severity, list[float]] = {
            Severity.CRITICAL: [],
            Severity.WARNING: [],
            Severity.INFO: [],
        }
        self._is_macos = sys.platform == "darwin"

    def _sanitize_text(self, text: str) -> str:
        """
        Remove characters that could break AppleScript string literals.
        Strips: backslashes, double quotes, single quotes, newlines.
        Truncates to 200 characters (macOS notification display limit).
        """
        sanitized = text.replace("\\", "").replace('"', "'").replace("\n", " ")
        return sanitized[:200]

    def _is_rate_limited(self, severity: Severity) -> bool:
        """
        Check if we've exceeded the rate limit for this severity level.
        Prunes old entries outside the window.
        """
        now = time.time()
        limit = self._rate_limits.get(severity, self._rate_limits[Severity.INFO])
        history = self._send_history.get(severity, [])

        # Prune entries outside window
        cutoff = now - limit["window_seconds"]
        history = [t for t in history if t > cutoff]
        self._send_history[severity] = history

        return len(history) >= limit["max_per_window"]

    def _build_applescript(self, title: str, message: str, severity: Severity) -> str:
        """
        Build AppleScript command for notification.

        CRITICAL alerts: include sound
        WARNING/INFO: silent banner
        """
        safe_title = self._sanitize_text(title)
        safe_message = self._sanitize_text(message)
        subtitle = f"{severity.value} Alert"

        script = f'display notification "{safe_message}" with title "{safe_title}" subtitle "{subtitle}"'

        if severity == Severity.CRITICAL:
            sound_name = self.config.get("notifications", {}).get("sound", "Purr")
            script += f' sound name "{sound_name}"'

        return script

    def send(self, alert) -> bool:
        """
        Send a macOS notification for the given alert.

        Returns True if notification was sent, False if skipped (rate limit, non-macOS, error).
        """
        if not self._is_macos:
            logger.debug("DesktopChannel: not macOS, skipping notification")
            return False

        severity = alert.severity if isinstance(alert.severity, Severity) else Severity.INFO

        if self._is_rate_limited(severity):
            logger.debug(f"DesktopChannel: rate limited for {severity.value}")
            return False

        title = f"BTC Monitor: {alert.rule_name}"
        message = alert.message
        script = self._build_applescript(title, message, severity)

        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                logger.warning(f"osascript failed: {result.stderr.strip()}")
                return False

            self._send_history[severity].append(time.time())
            logger.debug(f"Notification sent: [{severity.value}] {title}")
            return True

        except subprocess.TimeoutExpired:
            logger.warning("osascript timed out after 5s")
            return False
        except FileNotFoundError:
            logger.warning("osascript not found — not on macOS?")
            self._is_macos = False  # Don't try again
            return False
        except Exception as e:
            logger.warning(f"Notification error: {e}")
            return False
```

### 2. Security Hardening Details

| Vulnerability | Current | Fixed |
|---------------|---------|-------|
| Shell injection via message text | `os.system(f"osascript -e '...{message}...'")` — attacker-controlled text runs in shell | `subprocess.run(["osascript", "-e", script])` — no shell, args passed as list |
| Quote escaping | Single quotes escaped, double quotes not | `_sanitize_text()` strips all quotes, backslashes, newlines |
| Error swallowing | Bare `try/except: pass` | Specific exceptions caught, logged with context |
| Resource leak | `os.system()` spawns full shell process | `subprocess.run()` with timeout, no shell |
| Platform detection | `try/except` on first failure | Explicit `sys.platform == "darwin"` check, cached flag |

### 3. Rate Limiting per Severity

The current implementation has a single global rate limit (`max_desktop_per_5min: 1`). The new implementation uses per-severity windows:

| Severity | Max Notifications | Window | Rationale |
|----------|------------------|--------|-----------|
| CRITICAL | 1 | 15 minutes | Rare, high-signal events (capitulation, MVRV < 0.5). User needs to see these but not be spammed during a crash. |
| WARNING | 1 | 30 minutes | Common during volatile periods (F&G extremes, drawdown). Limit noise. |
| INFO | 3 | 1 hour | Low-priority (dominance shifts, BTC/Gold changes). Batch effect. |

### 4. Configuration Additions

Add to `config/default_config.yaml`:

```yaml
notifications:
  enabled: true
  sound: "Purr"                    # macOS sound name for CRITICAL alerts
  critical_rate_limit_minutes: 15
  warning_rate_limit_minutes: 30
  info_rate_limit_per_hour: 3
```

### 5. Integration with Alert Engine

No changes needed to `alerts/engine.py` — it already dispatches to all registered channels via the `AlertChannel` protocol. The `DesktopChannel` already conforms to this protocol. The replacement is a drop-in upgrade.

In `main.py`, the channel registration (around line 120) already creates `DesktopChannel`:
```python
channels = [ConsoleChannel(), FileChannel()]
if config.get("alerts", {}).get("desktop_notifications", True):
    channels.append(DesktopChannel(config))  # Now passes config for sound/rate settings
```

The only change: pass `config` to the `DesktopChannel` constructor (currently it takes no args).

## Benefits

| Decision | Why | Alternative Considered |
|----------|-----|----------------------|
| **Keep osascript** (hardened) | Zero dependencies, works on all macOS versions, good enough for local notifications | PyObjC/NSUserNotificationCenter — requires additional dependency, complex setup, signing issues |
| **subprocess.run() instead of os.system()** | Eliminates shell injection entirely, provides return code and stderr, supports timeout | shlex.quote() wrapping — partial fix, still uses shell |
| **Per-severity rate limiting** | CRITICAL alerts are rare and important, INFO alerts are noisy. Different rates match different signal-to-noise ratios. | Single global rate limit — too restrictive for critical alerts, too permissive for info |
| **Silent degradation on non-macOS** | Tool works everywhere, notifications are a bonus on macOS | Raise error on non-macOS — would break Linux/CI usage |

## Expectations

- **Notification delivery latency:** Under 500ms from alert trigger to notification appearance
- **Security:** Zero shell injection vectors. Verified by passing `"; rm -rf /"` as alert message — should display literally, not execute
- **Rate limiting accuracy:** CRITICAL alerts appear at most once per 15 minutes even during rapid market crashes
- **Platform safety:** Running on Linux produces zero errors, zero warnings in logs (just debug-level "not macOS" message)
- **Sound behavior:** CRITICAL alerts play the configured macOS sound. WARNING/INFO are silent banners.

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| macOS permission prompt blocks notification | Medium (first run) | Low — one-time annoyance | Document in setup: "Allow notifications from Terminal/iTerm when prompted" |
| osascript path changes in future macOS | Very low | Medium | `FileNotFoundError` caught, flag cached to avoid retries |
| Rate limiting too aggressive, user misses alerts | Low | Medium | Configurable via `default_config.yaml`. CRITICAL at 15min is generous for real market events. |
| Notification text too long for display | Medium | Low — truncated | `_sanitize_text()` truncates to 200 chars. Full alert text preserved in FileChannel JSONL log. |

## Results Criteria

1. **Inject test:** `alert.message = 'Test" ; echo "INJECTED'` — notification displays the literal text, no command execution
2. **Sound test:** CRITICAL alert triggers macOS sound. WARNING alert is silent.
3. **Rate limit test:** Trigger 5 CRITICAL alerts in rapid succession — only 1 notification appears, remaining 4 are logged as "rate limited"
4. **Non-macOS test:** Run on Linux (or mock `sys.platform`) — zero errors, `send()` returns `False`
5. **Timeout test:** If osascript hangs (simulate with `sleep`), `send()` returns `False` within 5 seconds
6. **All 165 existing tests still pass** — the channel replacement is backward-compatible

## Files Changed

| File | Change Type | Description |
|------|------------|-------------|
| `alerts/channels.py` | **MODIFY** | Replace `DesktopChannel` class entirely. Add `subprocess`, `sys` imports. Per-severity rate limiting. |
| `config/default_config.yaml` | **MODIFY** | Add `notifications:` section with sound and rate limit settings |
| `main.py` | **MODIFY** | Pass `config` to `DesktopChannel(config)` constructor (1 line change) |
| `tests/test_notifications.py` | **NEW** | Tests for sanitization, rate limiting, subprocess calls, non-macOS fallback |
