"""Trip-scoped scheduled overview notifications."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from src.config.settings import SmtpSettings
from src.loop.summary_schedule import SummarySlot, latest_due_summary_slot
from src.mailer.smtp_mailer import send_html_email
from src.models.offer import Trip
from src.notifications.instant_notification import MissingTripRecipientsError
from src.notifications.trip_mail_view import TripMailView, prepare_trip_mail_view
from src.storage.sqlite_store import SQLiteStore


SUMMARY_SUBJECT_PREFIX = "Regelmäßiges Update - "
MailComposer = Callable[[TripMailView], str]
MailSender = Callable[..., None]


def send_due_trip_summary(
    store: SQLiteStore,
    smtp_settings: SmtpSettings,
    trip: Trip,
    now: datetime,
    *,
    composer: MailComposer,
    mailer: MailSender = send_html_email,
) -> bool:
    """Send one due trip overview and persist its slot only after SMTP acceptance."""

    slot = latest_due_summary_slot(now)
    if slot is None or store.has_trip_overview_slot(
        trip.trip_id, slot.local_date, slot.hour
    ):
        return False

    view = prepare_trip_mail_view(store, trip)
    if not view.recipients:
        raise MissingTripRecipientsError(
            f"Trip {trip.trip_id!r} has no recipients for overview notifications."
        )

    mailer(
        smtp_settings,
        composer(view),
        recipients=view.recipients,
        subject=f"{SUMMARY_SUBJECT_PREFIX}{trip.name}",
    )
    return store.mark_trip_overview_slot_sent(
        trip.trip_id, slot.local_date, slot.hour
    )
