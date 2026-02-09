# 03 — Email Digest (SMTP)

## Overview

The Bitcoin Cycle Monitor generates weekly digests in terminal and HTML formats (`digest/weekly_digest.py`), and the couples report (`dashboard/couples_report.py`) already embeds charts as base64 PNGs. But there's no way to deliver these to an inbox. This document specifies SMTP email delivery for the weekly digest and critical alert notifications — so the Sunday summary arrives in your inbox without touching a terminal.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Email System                                 │
│                                                                  │
│  Two delivery paths:                                             │
│                                                                  │
│  1. Weekly Digest Email (Sunday)                                 │
│     ┌──────────────┐    ┌──────────────┐    ┌───────────────┐   │
│     │ WeeklyDigest │───▶│ EmailSender  │───▶│ SMTP Server   │   │
│     │ .format_html │    │ .send_digest │    │ (Gmail, etc)  │   │
│     └──────────────┘    └──────────────┘    └───────────────┘   │
│           │                                                      │
│     Chart images from                                            │
│     dca/charts.py                                                │
│     (Matplotlib PNGs,                                            │
│      base64 embedded)                                            │
│                                                                  │
│  2. Critical Alert Emails (on trigger)                           │
│     ┌──────────────┐    ┌──────────────┐    ┌───────────────┐   │
│     │ AlertEngine  │───▶│ EmailChannel │───▶│ SMTP Server   │   │
│     │ .evaluate()  │    │ .send()      │    │               │   │
│     └──────────────┘    └──────────────┘    └───────────────┘   │
│                                                                  │
│  Shared:                                                         │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ notifications/email_sender.py (NEW)                        │  │
│  │ - SMTP connection management                               │  │
│  │ - MIME multipart construction                              │  │
│  │ - HTML + plaintext + base64 image embedding                │  │
│  │ - Credential loading (env var or config)                   │  │
│  └────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

**Downstream consumers:**
- `01-automation-launchd.md` — launchd Sunday job calls `python main.py email send-digest`

## Specification

### 1. New Module: `notifications/email_sender.py`

```python
"""
SMTP email sender for Bitcoin Cycle Monitor.

Handles:
  - SMTP connection with TLS
  - MIME multipart construction (HTML + plaintext fallback)
  - Base64 image embedding for charts
  - Credential management (env vars > config file)

No external dependencies beyond Python stdlib (email, smtplib, ssl).
"""

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.utils import formataddr, formatdate
from pathlib import Path
import base64

class EmailSender:
    """
    SMTP email sender.

    Credential resolution order:
      1. Environment variables: BTC_MONITOR_SMTP_USER, BTC_MONITOR_SMTP_PASS
      2. Config file: config.email.smtp_username, config.email.smtp_password

    Usage:
      sender = EmailSender(config)
      sender.send_digest(html_content, subject, chart_images=[])
      sender.send_alert(alert_record)
    """

    def __init__(self, config: dict):
        email_config = config.get("email", {})
        self.smtp_host = email_config.get("smtp_host", "smtp.gmail.com")
        self.smtp_port = email_config.get("smtp_port", 587)
        self.use_tls = email_config.get("use_tls", True)
        self.from_address = email_config.get("from_address", "")
        self.to_address = email_config.get("to_address", "")
        self.from_name = email_config.get("from_name", "Bitcoin Monitor")

        # Credential resolution: env vars take priority
        import os
        self.username = os.environ.get("BTC_MONITOR_SMTP_USER",
                                       email_config.get("smtp_username", ""))
        self.password = os.environ.get("BTC_MONITOR_SMTP_PASS",
                                       email_config.get("smtp_password", ""))

    def is_configured(self) -> bool:
        """Check if all required SMTP fields are present."""
        return all([self.smtp_host, self.from_address, self.to_address,
                    self.username, self.password])

    def send_digest(
        self,
        html_content: str,
        subject: str = "Your Weekly Bitcoin Digest",
        chart_images: list[tuple[str, bytes]] = None,
        plaintext_fallback: str = None,
    ) -> bool:
        """
        Send weekly digest as HTML email with optional embedded charts.

        Args:
            html_content: Full HTML body (from WeeklyDigest.format_html() or
                         CouplesReportGenerator.generate())
            subject: Email subject line
            chart_images: list of (cid_name, png_bytes) for inline images.
                         Referenced in HTML as <img src="cid:cid_name">
            plaintext_fallback: Optional plain text version for email clients
                               that don't render HTML

        Returns:
            True if sent successfully, False otherwise.

        MIME structure:
            multipart/mixed
            ├── multipart/alternative
            │   ├── text/plain (fallback)
            │   └── text/html (digest)
            └── image/png (inline, for each chart)
        """
        if not self.is_configured():
            logger.warning("Email not configured — skipping digest send")
            return False

        msg = MIMEMultipart("mixed")
        msg["From"] = formataddr((self.from_name, self.from_address))
        msg["To"] = self.to_address
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=True)

        # Alternative part (plaintext + HTML)
        alt = MIMEMultipart("alternative")
        if plaintext_fallback:
            alt.attach(MIMEText(plaintext_fallback, "plain", "utf-8"))
        alt.attach(MIMEText(html_content, "html", "utf-8"))
        msg.attach(alt)

        # Inline chart images
        if chart_images:
            for cid_name, png_bytes in chart_images:
                img = MIMEImage(png_bytes, _subtype="png")
                img.add_header("Content-ID", f"<{cid_name}>")
                img.add_header("Content-Disposition", "inline", filename=f"{cid_name}.png")
                msg.attach(img)

        return self._send(msg)

    def send_alert(
        self,
        rule_name: str,
        severity: str,
        message: str,
        metric_value: float = None,
    ) -> bool:
        """
        Send a single alert email (for CRITICAL alerts only).

        Subject line includes severity emoji equivalent:
            CRITICAL: "[CRITICAL] BTC Monitor: Capitulation Zone Detected"

        Body is minimal HTML with alert details.
        """
        if not self.is_configured():
            return False

        severity_prefix = {"CRITICAL": "[CRITICAL]", "WARNING": "[WARNING]"}.get(severity, "[INFO]")
        subject = f"{severity_prefix} BTC Monitor: {rule_name}"

        html = f"""
        <div style="font-family: system-ui, sans-serif; max-width: 500px; margin: 0 auto;
                    padding: 20px; background: #1A1A2E; color: #E0E0E0; border-radius: 12px;">
            <h2 style="color: #F7931A; margin-top: 0;">Bitcoin Alert</h2>
            <div style="background: #16213E; padding: 16px; border-radius: 8px;
                        border-left: 4px solid {'#FF1744' if severity == 'CRITICAL' else '#FFC107'};">
                <h3 style="margin-top: 0; color: {'#FF1744' if severity == 'CRITICAL' else '#FFC107'};">
                    {severity}: {rule_name}
                </h3>
                <p>{message}</p>
                {f'<p style="color: #888;">Metric value: {metric_value}</p>' if metric_value else ''}
            </div>
            <p style="color: #636E72; font-size: 12px; margin-top: 16px;">
                Bitcoin Cycle Monitor &mdash; automated alert
            </p>
        </div>
        """

        msg = MIMEMultipart("alternative")
        msg["From"] = formataddr((self.from_name, self.from_address))
        msg["To"] = self.to_address
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=True)
        msg.attach(MIMEText(f"{severity}: {rule_name}\n{message}", "plain"))
        msg.attach(MIMEText(html, "html", "utf-8"))

        return self._send(msg)

    def test_connection(self) -> dict:
        """
        Test SMTP connectivity without sending an email.

        Returns:
            {"status": "ok"|"error", "message": str, "server_response": str}
        """
        try:
            context = ssl.create_default_context()
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
                server.ehlo()
                if self.use_tls:
                    server.starttls(context=context)
                    server.ehlo()
                server.login(self.username, self.password)
                return {"status": "ok", "message": "SMTP connection successful",
                        "server_response": str(server.noop())}
        except smtplib.SMTPAuthenticationError as e:
            return {"status": "error", "message": f"Authentication failed: {e}"}
        except smtplib.SMTPConnectError as e:
            return {"status": "error", "message": f"Connection failed: {e}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _send(self, msg: MIMEMultipart) -> bool:
        """Internal: send a constructed MIME message via SMTP."""
        try:
            context = ssl.create_default_context()
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as server:
                server.ehlo()
                if self.use_tls:
                    server.starttls(context=context)
                    server.ehlo()
                server.login(self.username, self.password)
                server.send_message(msg)
            logger.info(f"Email sent to {self.to_address}: {msg['Subject']}")
            return True
        except smtplib.SMTPAuthenticationError:
            logger.error("SMTP authentication failed. Check username/password.")
            return False
        except smtplib.SMTPRecipientsRefused:
            logger.error(f"Recipient refused: {self.to_address}")
            return False
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return False
```

### 2. New Alert Channel: `EmailChannel`

Add to `alerts/channels.py`:

```python
class EmailChannel:
    """
    Email alert channel — sends CRITICAL alerts as individual emails.

    Only sends for CRITICAL severity to avoid inbox flooding.
    Rate limited: max 1 email per 30 minutes.

    Requires email to be configured (see config/default_config.yaml email section).
    """

    def __init__(self, config: dict):
        from notifications.email_sender import EmailSender
        self.sender = EmailSender(config)
        self.enabled = config.get("email", {}).get("critical_alerts_enabled", True)
        self._last_sent = 0
        self._cooldown = 1800  # 30 minutes between alert emails

    def send(self, alert) -> bool:
        if not self.enabled or not self.sender.is_configured():
            return False

        # Only email CRITICAL alerts
        severity = alert.severity.value if hasattr(alert.severity, 'value') else str(alert.severity)
        if severity != "CRITICAL":
            return False

        # Rate limit
        now = time.time()
        if now - self._last_sent < self._cooldown:
            logger.debug("EmailChannel: rate limited")
            return False

        result = self.sender.send_alert(
            rule_name=alert.rule_name,
            severity=severity,
            message=alert.message,
            metric_value=getattr(alert, 'metric_value', None),
        )

        if result:
            self._last_sent = now

        return result
```

### 3. Digest Email Assembly

The weekly digest email combines the existing `WeeklyDigest.format_html()` output with embedded chart images from `dca/charts.py`.

Add to `notifications/email_sender.py`:

```python
def build_digest_email(
    weekly_digest,
    chart_generator,
    projector,
    goal_tracker,
    current_price: float,
    monthly_dca: float,
) -> tuple[str, list[tuple[str, bytes]]]:
    """
    Assemble digest HTML and chart images for email.

    Returns:
        (html_content, chart_images) where chart_images is list of (cid, png_bytes)

    Chart embedding strategy:
      - Generate charts via Matplotlib (not Plotly — email can't run JS)
      - Save to BytesIO buffers (no temp files)
      - Reference in HTML as <img src="cid:scenario_fan">
      - Attach as inline MIME images
    """
    import io

    # Generate digest HTML
    digest_data = weekly_digest.generate()
    html = weekly_digest.format_html()

    # Generate chart images in memory
    chart_images = []
    try:
        # Scenario fan
        buf = io.BytesIO()
        chart_generator.plot_scenario_fan(
            projector=projector,
            current_price=current_price,
            monthly_dca=monthly_dca,
            save_path=None,  # Modified: if save_path is None, write to buffer
            buffer=buf,
        )
        chart_images.append(("scenario_fan", buf.getvalue()))
    except Exception as e:
        logger.warning(f"Failed to generate scenario_fan for email: {e}")

    try:
        # Goal timeline
        buf = io.BytesIO()
        chart_generator.plot_goal_timeline(
            goal_tracker=goal_tracker,
            projector=projector,
            current_price=current_price,
            monthly_dca=monthly_dca,
            save_path=None,
            buffer=buf,
        )
        chart_images.append(("goal_timeline", buf.getvalue()))
    except Exception as e:
        logger.warning(f"Failed to generate goal_timeline for email: {e}")

    # Inject chart image references into HTML
    chart_html = ""
    if chart_images:
        chart_html = """
        <div style="margin-top: 20px;">
            <h3 style="color: #F7931A;">Charts</h3>
        """
        for cid, _ in chart_images:
            label = cid.replace("_", " ").title()
            chart_html += f"""
            <div style="margin-bottom: 16px;">
                <h4 style="color: #636E72;">{label}</h4>
                <img src="cid:{cid}" style="max-width: 100%; border-radius: 8px;"
                     alt="{label}">
            </div>
            """
        chart_html += "</div>"

    # Insert charts before closing </body> or at end
    html = html.replace("</body>", f"{chart_html}</body>")

    return html, chart_images
```

### 4. Matplotlib Chart Buffer Support

Modify `dca/charts.py` `_save()` method to support writing to a BytesIO buffer:

```python
# CURRENT:
def _save(self, fig, path):
    fig.savefig(path, dpi=200, bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close(fig)

# NEW:
def _save(self, fig, path=None, buffer=None):
    """
    Save figure to file path or BytesIO buffer.

    If buffer is provided, writes PNG to buffer (for email embedding).
    If path is provided, saves to file (existing behavior).
    """
    kwargs = dict(dpi=200, bbox_inches='tight', facecolor=fig.get_facecolor(), format='png')
    if buffer is not None:
        fig.savefig(buffer, **kwargs)
        buffer.seek(0)
    elif path is not None:
        fig.savefig(path, **kwargs)
    plt.close(fig)
```

Update chart methods to accept optional `buffer` parameter and pass through to `_save()`.

### 5. CLI Commands

Add to `main.py`:

```python
@cli.group()
def email():
    """Email configuration and sending."""
    pass

@email.command("setup")
@click.pass_context
def email_setup(ctx):
    """Interactive email setup wizard."""
    from rich.prompt import Prompt, Confirm
    config = ctx.obj["config"]

    console.print("\n[btc]Email Setup[/]\n")
    console.print("You'll need SMTP credentials. For Gmail, use an App Password:")
    console.print("  https://myaccount.google.com/apppasswords\n")

    smtp_host = Prompt.ask("SMTP host", default="smtp.gmail.com")
    smtp_port = Prompt.ask("SMTP port", default="587")
    from_addr = Prompt.ask("From email address")
    to_addr = Prompt.ask("To email address (where digests go)")
    username = Prompt.ask("SMTP username (usually your email)")
    password = Prompt.ask("SMTP password (app password)", password=True)

    # Save to user config
    email_config = {
        "enabled": True,
        "smtp_host": smtp_host,
        "smtp_port": int(smtp_port),
        "from_address": from_addr,
        "to_address": to_addr,
        "smtp_username": username,
        "smtp_password": password,
        "use_tls": True,
        "digest_enabled": True,
        "critical_alerts_enabled": True,
    }

    # Update user config file
    user_config_path = "config/user_config.yaml"
    # ... save email_config to YAML ...

    # Test connection
    if Confirm.ask("Test the connection now?"):
        from notifications.email_sender import EmailSender
        sender = EmailSender({"email": email_config})
        result = sender.test_connection()
        if result["status"] == "ok":
            console.print(f"[bull]Connection successful![/]")
        else:
            console.print(f"[bear]Failed:[/] {result['message']}")

@email.command("test")
@click.pass_context
def email_test(ctx):
    """Send a test email."""
    from notifications.email_sender import EmailSender
    sender = EmailSender(ctx.obj["config"])

    if not sender.is_configured():
        console.print("[bear]Email not configured.[/] Run: python main.py email setup")
        return

    result = sender.send_digest(
        html_content="<h1>Test Email</h1><p>Bitcoin Cycle Monitor email is working.</p>",
        subject="BTC Monitor — Test Email",
    )
    if result:
        console.print(f"[bull]Test email sent to {sender.to_address}[/]")
    else:
        console.print("[bear]Failed to send test email. Check logs.[/]")

@email.command("send-digest")
@click.pass_context
def email_send_digest(ctx):
    """Send the weekly digest via email (with charts)."""
    from notifications.email_sender import EmailSender, build_digest_email
    c = ctx.obj

    sender = EmailSender(c["config"])
    if not sender.is_configured():
        console.print("[bear]Email not configured.[/] Run: python main.py email setup")
        return

    console.print("[btc]Generating weekly digest with charts...[/]")

    html, charts = build_digest_email(
        weekly_digest=c["weekly_digest"],
        chart_generator=c["chart_gen"],
        projector=c["projector"],
        goal_tracker=c.get("goal_tracker"),
        current_price=c["monitor"].get_current_status().price.price_usd,
        monthly_dca=c["config"].get("dca", {}).get("default_amount", 200),
    )

    result = sender.send_digest(html, chart_images=charts)
    if result:
        console.print(f"[bull]Digest sent to {sender.to_address}[/]")
    else:
        console.print("[bear]Failed to send digest.[/]")
```

### 6. Configuration Additions

Add to `config/default_config.yaml`:

```yaml
email:
  enabled: false
  smtp_host: "smtp.gmail.com"
  smtp_port: 587
  use_tls: true
  smtp_username: ""      # Or set BTC_MONITOR_SMTP_USER env var
  smtp_password: ""      # Or set BTC_MONITOR_SMTP_PASS env var
  from_address: ""
  from_name: "Bitcoin Monitor"
  to_address: ""
  digest_enabled: true
  critical_alerts_enabled: true
```

### 7. Credential Security

SMTP credentials can be stored in three places (resolution order):

| Method | Config Key | Security Level | Use Case |
|--------|-----------|---------------|----------|
| **Environment variables** | `BTC_MONITOR_SMTP_USER`, `BTC_MONITOR_SMTP_PASS` | Best — not in files | Production, launchd |
| **Config file** | `email.smtp_username`, `email.smtp_password` | Moderate — plaintext YAML | Quick local setup |
| **macOS Keychain** | Future enhancement | Best — OS-level encryption | Not implemented in v1 |

For Gmail specifically: users must generate an App Password (not their main password). The setup wizard links to the App Password page.

**`.gitignore` update:** Ensure `config/user_config.yaml` is already in `.gitignore` (it is — contains user-specific settings including potential credentials).

## Benefits

| Decision | Why | Alternative Considered |
|----------|-----|----------------------|
| **Python stdlib `smtplib`** | Zero dependencies. SMTP is simple. SSL/TLS built in. | SendGrid/Mailgun API — external dependency, requires API key, overkill for personal use |
| **MIME multipart with inline images** | Charts render in all major email clients (Gmail, Apple Mail, Outlook). No external image hosting needed. | Base64 data URIs — blocked by Gmail. External image URLs — requires hosting. |
| **Critical-only alert emails** | Prevents inbox flooding. CRITICAL alerts are rare (capitulation, MVRV < 0.5). | All severities — would send 5+ emails per day during volatile markets |
| **Env var credential priority** | Keeps passwords out of config files. Works with launchd EnvironmentVariables. | Config-only — works but risky if repo pushed to remote |
| **Gmail as default SMTP** | Most common email provider. App Passwords are well-documented. | Generic SMTP — harder to document, more setup variability |

## Expectations

- **Digest email delivery:** Under 10 seconds from command to inbox (including chart generation)
- **Email rendering:** Correct in Gmail (web + mobile), Apple Mail, and Outlook. Charts display inline, not as attachments.
- **Alert email delivery:** Under 5 seconds from alert trigger to inbox
- **SMTP errors:** Clear error messages for: wrong password, wrong host, wrong port, TLS mismatch, recipient refused
- **Rate limiting:** Max 1 CRITICAL alert email per 30 minutes. Digest emails are manual/scheduled (no rate limit).
- **Credential security:** Passwords never logged. Env vars take priority over config file.

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Gmail blocks SMTP login | Low (App Passwords work reliably) | High — no emails | Clear setup instructions with App Password link. `email test` command for verification. |
| Email marked as spam | Medium (personal SMTP, no DKIM) | Medium — digest goes to spam | Document: "Check spam folder. Mark as 'Not Spam' once." From address matches SMTP user. |
| SMTP password in config file leaked | Low (file is in .gitignore) | High — email account compromised | Env var priority. Setup wizard warns about this. Future: macOS Keychain integration. |
| Chart generation fails (no data) | Low | Low — email sends without charts | Graceful fallback: charts are optional. HTML digest works standalone. |
| SMTP timeout during launchd run | Low | Low — digest skipped this week | Retry logic in launchd (see `01-automation-launchd.md`). 30-second timeout per connection. |

## Results Criteria

1. **`python main.py email setup`** walks through SMTP configuration and saves to `user_config.yaml`
2. **`python main.py email test`** sends a test email that arrives in inbox within 10 seconds
3. **`python main.py email send-digest`** sends weekly digest with 2 embedded chart images
4. **Gmail renders digest correctly** — charts inline, colors correct, mobile-responsive
5. **Apple Mail renders digest correctly** — same criteria
6. **CRITICAL alert triggers email** — when a CRITICAL alert fires with EmailChannel registered, email arrives
7. **Non-CRITICAL alerts don't send email** — WARNING and INFO alerts are desktop-only
8. **Env var credentials work** — setting `BTC_MONITOR_SMTP_PASS` overrides config file
9. **Wrong password shows clear error** — `email test` with bad credentials prints "Authentication failed"
10. **All 165 existing tests still pass** — email module is additive

## Files Changed

| File | Change Type | Description |
|------|------------|-------------|
| `notifications/email_sender.py` | **NEW** | EmailSender class with SMTP, MIME, test_connection |
| `alerts/channels.py` | **MODIFY** | Add EmailChannel class (CRITICAL-only, rate-limited) |
| `main.py` | **MODIFY** | Add `email` command group with `setup`, `test`, `send-digest` |
| `config/default_config.yaml` | **MODIFY** | Add `email:` section |
| `dca/charts.py` | **MODIFY** | Update `_save()` to accept BytesIO buffer for in-memory chart generation |
| `tests/test_email.py` | **NEW** | Tests for EmailSender (mock SMTP), EmailChannel, MIME construction, credential resolution |
