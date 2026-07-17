"""Unit tests for the SMTP mail transport."""

from unittest.mock import MagicMock, patch

import pytest

from src.config.settings import SmtpSettings
from src.mailer.smtp_mailer import (
    SmtpAuthenticationError,
    SmtpConnectionError,
    SmtpTransportError,
    send_html_email,
)


@pytest.fixture
def smtp_settings() -> SmtpSettings:
    return SmtpSettings(
        host="smtp.example.test",
        port=587,
        user="mailer",
        password="secret",
        sender="sender@example.test",
        use_tls=True,
    )


@patch("src.mailer.smtp_mailer.smtplib.SMTP")
def test_send_html_email_uses_all_settings_and_reports_success(
    smtp_constructor: MagicMock, smtp_settings: SmtpSettings
) -> None:
    smtp = smtp_constructor.return_value.__enter__.return_value
    smtp.send_message.return_value = {}

    send_html_email(
        smtp_settings,
        "<h1>Neue Angebote</h1>",
        recipients=("first@example.test", "second@example.test"),
        subject="Testangebot",
    )

    smtp_constructor.assert_called_once_with("smtp.example.test", 587)
    smtp.starttls.assert_called_once()
    smtp.login.assert_called_once_with("mailer", "secret")
    smtp.send_message.assert_called_once()
    message = smtp.send_message.call_args.args[0]
    assert message["Subject"] == "Testangebot"
    assert message["From"] == "sender@example.test"
    assert message["To"] == "first@example.test, second@example.test"
    assert smtp.send_message.call_args.kwargs == {
        "from_addr": "sender@example.test",
        "to_addrs": ("first@example.test", "second@example.test"),
    }


@patch("src.mailer.smtp_mailer.smtplib.SMTP")
def test_send_html_email_uses_explicit_trip_recipients(
    smtp_constructor: MagicMock, smtp_settings: SmtpSettings
) -> None:
    smtp = smtp_constructor.return_value.__enter__.return_value
    smtp.send_message.return_value = {}

    send_html_email(
        smtp_settings,
        "<p>Reiseangebote</p>",
        recipients=("trip@example.test",),
    )

    message = smtp.send_message.call_args.args[0]
    assert message["To"] == "trip@example.test"
    assert smtp.send_message.call_args.kwargs["to_addrs"] == ("trip@example.test",)


@patch("src.mailer.smtp_mailer.smtplib.SMTP")
def test_send_html_email_keeps_recipients_isolated_between_trip_sends(
    smtp_constructor: MagicMock, smtp_settings: SmtpSettings
) -> None:
    smtp = smtp_constructor.return_value.__enter__.return_value
    smtp.send_message.return_value = {}

    send_html_email(
        smtp_settings,
        "<p>Erste Reise</p>",
        recipients=("first-trip@example.test",),
    )
    send_html_email(
        smtp_settings,
        "<p>Zweite Reise</p>",
        recipients=("second-trip@example.test",),
    )

    assert smtp.send_message.call_count == 2
    first_message, second_message = (
        call.args[0] for call in smtp.send_message.call_args_list
    )
    assert first_message["To"] == "first-trip@example.test"
    assert second_message["To"] == "second-trip@example.test"
    assert [
        call.kwargs["to_addrs"] for call in smtp.send_message.call_args_list
    ] == [
        ("first-trip@example.test",),
        ("second-trip@example.test",),
    ]


@patch("src.mailer.smtp_mailer.smtplib.SMTP")
def test_send_html_email_requires_explicit_recipients(
    smtp_constructor: MagicMock, smtp_settings: SmtpSettings
) -> None:
    with pytest.raises(ValueError, match="recipient"):
        send_html_email(smtp_settings, "<p>HTML</p>", recipients=())

    smtp_constructor.assert_not_called()


@patch("src.mailer.smtp_mailer.smtplib.SMTP")
def test_send_html_email_without_tls_skips_starttls(
    smtp_constructor: MagicMock, smtp_settings: SmtpSettings
) -> None:
    smtp = smtp_constructor.return_value.__enter__.return_value
    smtp.send_message.return_value = {}
    smtp_settings = SmtpSettings(**{**smtp_settings.__dict__, "use_tls": False})

    send_html_email(smtp_settings, "<p>HTML</p>", recipients=("recipient@example.test",))

    smtp.starttls.assert_not_called()


@patch("src.mailer.smtp_mailer.smtplib.SMTP")
def test_send_html_email_signals_authentication_failure(
    smtp_constructor: MagicMock, smtp_settings: SmtpSettings
) -> None:
    smtp = smtp_constructor.return_value.__enter__.return_value
    smtp.login.side_effect = __import__("smtplib").SMTPAuthenticationError(535, b"denied")

    with pytest.raises(SmtpAuthenticationError, match="authentication"):
        send_html_email(smtp_settings, "<p>HTML</p>", recipients=("recipient@example.test",))


@patch("src.mailer.smtp_mailer.smtplib.SMTP", side_effect=OSError("network unreachable"))
def test_send_html_email_signals_connection_failure(
    smtp_constructor: MagicMock, smtp_settings: SmtpSettings
) -> None:
    with pytest.raises(SmtpConnectionError, match="connection"):
        send_html_email(smtp_settings, "<p>HTML</p>", recipients=("recipient@example.test",))


@patch("src.mailer.smtp_mailer.smtplib.SMTP")
def test_send_html_email_signals_transport_failure(
    smtp_constructor: MagicMock, smtp_settings: SmtpSettings
) -> None:
    smtp = smtp_constructor.return_value.__enter__.return_value
    smtp.send_message.return_value = {"second@example.test": (550, b"rejected")}

    with pytest.raises(SmtpTransportError, match="refused"):
        send_html_email(
            smtp_settings, "<p>HTML</p>", recipients=("second@example.test",)
        )
