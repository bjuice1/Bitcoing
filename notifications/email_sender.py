"""
SMTP email sender for Bitcoin Cycle Monitor.

Handles:
  - SMTP connection with TLS
  - MIME multipart construction (HTML + plaintext fallback)
  - Base64 image embedding for charts
  - Credential management (env vars > config file)

No external dependencies beyond Python stdlib (email, smtplib, ssl).
"""
import os
import ssl
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.utils import formataddr, formatdate

logger = logging.getLogger("btcmonitor.notifications.email_sender")


class EmailSender:
    """
    SMTP email sender.

    Credential resolution order:
      1. Environment variables: BTC_MONITOR_SMTP_USER, BTC_MONITOR_SMTP_PASS
      2. Config file: config.email.smtp_username, config.email.smtp_password
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
        self.username = os.environ.get(
            "BTC_MONITOR_SMTP_USER",
            email_config.get("smtp_username", ""),
        )
        self.password = os.environ.get(
            "BTC_MONITOR_SMTP_PASS",
            email_config.get("smtp_password", ""),
        )

    def is_configured(self) -> bool:
        """Check if all required SMTP fields are present."""
        return all([self.smtp_host, self.from_address, self.to_address,
                    self.username, self.password])

    def send_digest(
        self,
        html_content: str,
        subject: str = "Your Weekly Bitcoin Digest",
        chart_images: list = None,
        plaintext_fallback: str = None,
    ) -> bool:
        """
        Send weekly digest as HTML email with optional embedded charts.

        Args:
            html_content: Full HTML body
            subject: Email subject line
            chart_images: list of (cid_name, png_bytes) for inline images
            plaintext_fallback: Optional plain text version
        """
        if not self.is_configured():
            logger.warning("Email not configured - skipping digest send")
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
        """Send a single alert email (for CRITICAL alerts)."""
        if not self.is_configured():
            return False

        severity_prefix = {"CRITICAL": "[CRITICAL]", "WARNING": "[WARNING]"}.get(severity, "[INFO]")
        subject = f"{severity_prefix} BTC Monitor: {rule_name}"

        metric_html = f'<p style="color: #888;">Metric value: {metric_value}</p>' if metric_value is not None else ""
        severity_color = "#FF1744" if severity == "CRITICAL" else "#FFC107"

        html = f"""
        <div style="font-family: system-ui, sans-serif; max-width: 500px; margin: 0 auto;
                    padding: 20px; background: #FFFFFF; color: #1E272E; border-radius: 12px;">
            <h2 style="color: #F7931A; margin-top: 0;">Bitcoin Alert</h2>
            <div style="background: #F0F1F6; padding: 16px; border-radius: 8px;
                        border-left: 4px solid {severity_color};">
                <h3 style="margin-top: 0; color: {severity_color};">
                    {severity}: {rule_name}
                </h3>
                <p>{message}</p>
                {metric_html}
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
        """Test SMTP connectivity without sending an email."""
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
