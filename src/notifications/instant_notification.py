"""Trip-scoped instant offer notifications."""

from __future__ import annotations

from collections.abc import Callable

from src.config.settings import SmtpSettings
from src.mailer.smtp_mailer import send_html_email
from src.models.offer import Trip
from src.notifications.trip_mail_view import TripMailView, prepare_trip_mail_view
from src.storage.sqlite_store import SQLiteStore


class MissingTripRecipientsError(ValueError):
    """Raised when an instant notification has no trip-specific recipients."""


MailComposer = Callable[[TripMailView], str]
MailSender = Callable[..., None]


def send_instant_trip_notification(
    store: SQLiteStore,
    smtp_settings: SmtpSettings,
    trip: Trip,
    *,
    composer: MailComposer,
    mailer: MailSender = send_html_email,
) -> bool:
    """Send one trip's new offers and persist delivery only after SMTP acceptance."""

    view = prepare_trip_mail_view(store, trip)
    if not view.new_offers:
        return False
    if not view.recipients:
        raise MissingTripRecipientsError(
            f"Trip {trip.trip_id!r} has no recipients for instant notifications."
        )

    html_body = composer(view)
    mailer(
        smtp_settings,
        html_body,
        recipients=view.recipients,
        subject=f"Neue Angebote für {trip.name}",
    )
    store.mark_trip_offers_sent(
        trip.trip_id, (offer.offer_id for offer in view.new_offers)
    )
    return True
