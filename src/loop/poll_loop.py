"""Polling-cycle orchestration for offer monitoring."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, time as datetime_time, timedelta
import logging
import time

from src.api.api_client import ApiClientError, fetch_offers
from src.config.settings import Settings
from src.config.timezone import LOCAL_TIMEZONE
from src.mailer.smtp_mailer import SmtpSendError, send_html_email
from src.mailer.templates import render_offer_email, render_offer_summary_email
from src.matcher.offer_matcher import calculate_delta
from src.models.offer import ClassifiedOffer, Offer
from src.parser.offer_parser import OfferParsingError, parse_offers
from src.storage.sqlite_store import SQLiteStore, SQLiteStoreError


LOGGER = logging.getLogger("movacar_alert.loop.poll_loop")
SUMMARY_HOURS = (9, 21)
SUMMARY_SUBJECT = "Regelmäßiges Update - Aktuelle Angebote"


@dataclass(frozen=True)
class PollCycleResult:
    """Outcome counts and completion state of one polling cycle."""

    completed: bool
    mail_sent: bool
    new_count: int = 0
    existing_count: int = 0
    removed_count: int = 0
    current_offers: tuple[ClassifiedOffer, ...] = field(default=(), compare=False)


def run_polling_cycle(settings: Settings, store: SQLiteStore) -> PollCycleResult:
    """Execute one complete polling cycle while handling expected operational errors.

    API and parsing failures leave persisted state untouched. SMTP failures do not
    persist newly discovered offers, so they are retried during the next cycle.
    """
    try:
        response = fetch_offers(settings)
        offers = _with_local_dates(parse_offers(response))
    except (ApiClientError, OfferParsingError) as error:
        LOGGER.error("Polling cycle aborted while fetching or parsing offers: %s", error)
        return PollCycleResult(completed=False, mail_sent=False)

    try:
        known_offers = store.read_offers()
        delta = calculate_delta(offers, known_offers, settings.de_bbox)
    except SQLiteStoreError as error:
        LOGGER.error("Polling cycle aborted while reading persisted offers: %s", error)
        return PollCycleResult(completed=False, mail_sent=False)

    result = PollCycleResult(
        completed=True,
        mail_sent=False,
        new_count=delta.new_count,
        existing_count=delta.existing_count,
        removed_count=delta.removed_count,
        current_offers=delta.new + delta.existing,
    )
    if delta.new:
        try:
            html_body = render_offer_email(delta.new, delta.existing)
            send_html_email(settings.smtp, html_body)
        except SmtpSendError as error:
            LOGGER.error("Polling cycle mail delivery failed: %s", error)
            return result

        result = PollCycleResult(
            completed=True,
            mail_sent=True,
            new_count=result.new_count,
            existing_count=result.existing_count,
            removed_count=result.removed_count,
            current_offers=result.current_offers,
        )
        try:
            store.insert_offers(delta.new)
        except SQLiteStoreError as error:
            LOGGER.error("Polling cycle aborted while persisting new offers: %s", error)
            return PollCycleResult(
                completed=False,
                mail_sent=True,
                new_count=result.new_count,
                existing_count=result.existing_count,
                removed_count=result.removed_count,
                current_offers=result.current_offers,
            )
    try:
        soft_deleted = store.soft_delete_removed_offers(offer.id for offer in offers)
        purged = store.purge_soft_deleted_offers()
    except SQLiteStoreError as error:
        LOGGER.error("Polling cycle aborted during persisted-offer cleanup: %s", error)
        return PollCycleResult(
            completed=False,
            mail_sent=result.mail_sent,
            new_count=result.new_count,
            existing_count=result.existing_count,
            removed_count=result.removed_count,
            current_offers=result.current_offers,
        )

    return result


def poll_forever(
    settings: Settings,
    store: SQLiteStore,
    *,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] | None = None,
) -> None:
    """Run polling cycles indefinitely at the configured interval."""
    interval_seconds = settings.poll_interval_minutes * 60
    clock = (lambda: datetime.now(LOCAL_TIMEZONE)) if now is None else now
    last_summary_slot = _latest_summary_slot(_local_now(clock()))
    while True:
        result = run_polling_cycle(settings, store)
        if result.completed:
            last_summary_slot = _send_due_summary(
                settings,
                result,
                _local_now(clock()),
                last_summary_slot,
            )
        if result.completed and (result.new_count == 0 or result.mail_sent):
            next_cycle_at = _local_now(clock()) + timedelta(seconds=interval_seconds)
            email_status = "eine" if result.mail_sent else "keine"
            LOGGER.info(
                "Erfolgreicher Polling-Durchlauf: %s neue Angebote gesichtet; "
                "%s E-Mail versendet. Nächster Durchlauf um %s.",
                result.new_count,
                email_status,
                next_cycle_at.strftime("%Y-%m-%d %H:%M:%S"),
            )
        sleep(interval_seconds)


def _send_due_summary(
    settings: Settings,
    result: PollCycleResult,
    now: datetime,
    last_summary_slot: tuple[date, int] | None,
) -> tuple[date, int] | None:
    """Send at most one due summary slot and retain failed slots for retry."""

    due_slot = _due_summary_slot(now, last_summary_slot)
    if due_slot is None:
        return last_summary_slot

    try:
        send_html_email(
            settings.smtp,
            render_offer_summary_email(result.current_offers),
            subject=SUMMARY_SUBJECT,
        )
    except SmtpSendError as error:
        LOGGER.error("Scheduled summary mail delivery failed: %s", error)
        return last_summary_slot

    LOGGER.info(
        "Geplante Angebotsübersicht versendet für %s Uhr.",
        f"{due_slot[1]:02d}:00",
    )
    return due_slot


def _due_summary_slot(
    now: datetime,
    last_summary_slot: tuple[date, int] | None,
) -> tuple[date, int] | None:
    """Return the latest local summary slot that is due and not yet sent."""

    local_now = _local_now(now)
    latest_slot = _latest_summary_slot(local_now)
    if latest_slot is not None and latest_slot != last_summary_slot:
        return latest_slot
    return None


def _latest_summary_slot(now: datetime) -> tuple[date, int] | None:
    """Return the most recent summary slot reached at the given local time."""

    local_now = _local_now(now)
    reached_hours = (hour for hour in SUMMARY_HOURS if local_now.time() >= datetime_time(hour))
    latest_hour = next(reversed(tuple(reached_hours)), None)
    if latest_hour is None:
        return None
    return local_now.date(), latest_hour


def _local_now(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=LOCAL_TIMEZONE)
    return value.astimezone(LOCAL_TIMEZONE)


def _with_local_dates(offers: Iterable[Offer]) -> tuple[Offer, ...]:
    """Convert parser-normalized timestamps to the configured local-time policy."""
    converted: list[Offer] = []
    for offer in offers:
        if offer.start_date.tzinfo is None or offer.start_date.utcoffset() is None:
            raise ValueError("Offer start_date must include a timezone.")
        if offer.end_date.tzinfo is None or offer.end_date.utcoffset() is None:
            raise ValueError("Offer end_date must include a timezone.")
        converted.append(
            Offer(
                id=offer.id,
                start_date=offer.start_date.astimezone(LOCAL_TIMEZONE),
                end_date=offer.end_date.astimezone(LOCAL_TIMEZONE),
                free_km=offer.free_km,
                origin=offer.origin,
                destination=offer.destination,
            )
        )
    return tuple(converted)
