"""Email notification helper for Tuya Watering."""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .const import CONF_SMTP_HOST, CONF_SMTP_PASSWORD, CONF_SMTP_PORT, CONF_SMTP_SENDER

_LOGGER = logging.getLogger(__name__)


class Notifier:
    """Sends plain-text/HTML emails for watering skip alerts."""

    def __init__(self, smtp_config: dict) -> None:
        self._host     = smtp_config[CONF_SMTP_HOST]
        self._port     = smtp_config[CONF_SMTP_PORT]
        self._sender   = smtp_config[CONF_SMTP_SENDER]
        self._password = smtp_config[CONF_SMTP_PASSWORD]

    def send(self, subject: str, body_html: str, to_addrs: list[str]) -> None:
        """Send email — never raises; logs on failure."""
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"]    = self._sender
            msg["To"]      = ", ".join(to_addrs)
            msg.attach(MIMEText(body_html, "html"))

            with smtplib.SMTP(self._host, self._port) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(self._sender, self._password)
                smtp.sendmail(self._sender, to_addrs, msg.as_string())

            _LOGGER.debug("Email sent to %s: %s", to_addrs, subject)

        except Exception as err:
            _LOGGER.error("Email send failed to %s: %s", to_addrs, err)
