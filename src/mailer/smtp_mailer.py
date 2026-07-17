"""SMTP transport boundary."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from typing import Final

from src.config.settings import SmtpSettings


DEFAULT_SUBJECT: Final = "Neue Angebote bei Movacar gefunden"


class SmtpSendError(RuntimeError):
    """Raised when an email could not be handed to the SMTP server."""


class SmtpConnectionError(SmtpSendError):
    """Raised when the SMTP server cannot be reached."""


class SmtpAuthenticationError(SmtpSendError):
    """Raised when SMTP authentication is rejected."""


class SmtpTransportError(SmtpSendError):
    """Raised when an established SMTP transport rejects the message."""


def send_html_email(
    smtp_settings: SmtpSettings,
    html_body: str,
    *,
    recipients: tuple[str, ...] | None = None,
    subject: str = DEFAULT_SUBJECT,
) -> None:
    """Send an HTML notification using STARTTLS when configured.

    ``SMTP_USE_TLS=true`` selects explicit TLS via STARTTLS, intended for port
    587. SMTP errors are translated to specific transport-boundary exceptions.
    """
    message_recipients = smtp_settings.recipients if recipients is None else recipients
    if not message_recipients:
        raise ValueError("At least one email recipient is required.")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = smtp_settings.sender
    message["To"] = ", ".join(message_recipients)
    message.set_content("Diese Benachrichtigung enthält HTML-Inhalt.")
    message.add_alternative(html_body, subtype="html")

    try:
        with smtplib.SMTP(smtp_settings.host, smtp_settings.port) as smtp:
            if smtp_settings.use_tls:
                smtp.starttls(context=ssl.create_default_context())
            smtp.login(smtp_settings.user, smtp_settings.password)
            refused_recipients = smtp.send_message(
                message,
                from_addr=smtp_settings.sender,
                to_addrs=message_recipients,
            )
    except smtplib.SMTPAuthenticationError as error:
        raise SmtpAuthenticationError("SMTP authentication was rejected.") from error
    except (smtplib.SMTPConnectError, OSError) as error:
        raise SmtpConnectionError("SMTP server connection failed.") from error
    except smtplib.SMTPException as error:
        raise SmtpTransportError("SMTP transport failed while sending the message.") from error

    if refused_recipients:
        raise SmtpTransportError(
            f"SMTP server refused recipient addresses: {', '.join(refused_recipients)}."
        )
