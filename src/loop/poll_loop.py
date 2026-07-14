"""Polling-cycle orchestration for offer monitoring."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
import time
from uuid import uuid4

from src.api.api_client import ApiClientError, fetch_offers
from src.config.settings import Settings
from src.logging.logger import EventName, log_event
from src.mailer.smtp_mailer import SmtpSendError, send_html_email
from src.mailer.templates import render_offer_email
from src.matcher.offer_matcher import calculate_delta
from src.models.offer import Offer
from src.parser.offer_parser import OfferParsingError, parse_offers
from src.storage.sqlite_store import SQLiteStore, SQLiteStoreError


LOGGER = logging.getLogger("movacar_alert.loop.poll_loop")


@dataclass(frozen=True)
class PollCycleResult:
    """Outcome counts and completion state of one polling cycle."""

    completed: bool
    mail_sent: bool
    new_count: int = 0
    existing_count: int = 0
    removed_count: int = 0


def run_polling_cycle(
    settings: Settings, store: SQLiteStore, *, cycle_id: str | None = None
) -> PollCycleResult:
    """Execute one complete polling cycle while handling expected operational errors.

    API and parsing failures leave persisted state untouched. SMTP failures do not
    persist newly discovered offers, so they are retried during the next cycle.
    """
    cycle_id = cycle_id or uuid4().hex
    log_event(
        LOGGER,
        level="INFO",
        event=EventName.CYCLE_STARTED,
        cycle_id=cycle_id,
        message="Polling cycle started.",
    )
    try:
        log_event(
            LOGGER,
            level="INFO",
            event=EventName.API_REQUESTED,
            cycle_id=cycle_id,
            message="New API request started.",
        )
        response = fetch_offers(settings)
        offers = _with_local_dates(parse_offers(response))
    except (ApiClientError, OfferParsingError) as error:
        log_event(
            LOGGER,
            level="ERROR",
            event=EventName.API_FAILED,
            cycle_id=cycle_id,
            message=f"Polling cycle aborted while fetching or parsing offers: {error}",
        )
        return PollCycleResult(completed=False, mail_sent=False)
    log_event(
        LOGGER,
        level="INFO",
        event=EventName.API_SUCCEEDED,
        cycle_id=cycle_id,
        message="API response was fetched and parsed successfully.",
        data={"offer_count": len(offers)},
    )

    try:
        known_offers = store.read_offers()
        delta = calculate_delta(offers, known_offers, settings.de_bbox)
    except SQLiteStoreError as error:
        log_event(
            LOGGER,
            level="ERROR",
            event=EventName.DB_READ_FAILED,
            cycle_id=cycle_id,
            message=f"Polling cycle aborted while reading persisted offers: {error}",
        )
        return PollCycleResult(completed=False, mail_sent=False)

    result = PollCycleResult(
        completed=True,
        mail_sent=False,
        new_count=delta.new_count,
        existing_count=delta.existing_count,
        removed_count=delta.removed_count,
    )
    log_event(
        LOGGER,
        level="INFO",
        event=EventName.DELTA_CALCULATED,
        cycle_id=cycle_id,
        message="Offer delta calculated.",
        data={
            "new_count": result.new_count,
            "existing_count": result.existing_count,
            "removed_count": result.removed_count,
        },
    )

    if delta.new:
        log_event(
            LOGGER,
            level="INFO",
            event=EventName.NEW_OFFERS_RECEIVED,
            cycle_id=cycle_id,
            message="New offers received.",
            data={"new_count": result.new_count},
        )
        try:
            html_body = render_offer_email(delta.new, delta.existing)
            send_html_email(settings.smtp, html_body)
        except SmtpSendError as error:
            log_event(
                LOGGER,
                level="ERROR",
                event=EventName.MAIL_FAILED,
                cycle_id=cycle_id,
                message=f"Polling cycle mail delivery failed: {error}",
            )
            return result

        result = PollCycleResult(
            completed=True,
            mail_sent=True,
            new_count=result.new_count,
            existing_count=result.existing_count,
            removed_count=result.removed_count,
        )
        log_event(
            LOGGER,
            level="INFO",
            event=EventName.MAIL_SENT,
            cycle_id=cycle_id,
            message="Offer notification sent successfully.",
            data={"new_count": result.new_count},
        )

        try:
            store.insert_offers(delta.new)
        except SQLiteStoreError as error:
            log_event(
                LOGGER,
                level="ERROR",
                event=EventName.DB_WRITE_FAILED,
                cycle_id=cycle_id,
                message=f"Polling cycle aborted while persisting new offers: {error}",
            )
            return PollCycleResult(
                completed=False,
                mail_sent=True,
                new_count=result.new_count,
                existing_count=result.existing_count,
                removed_count=result.removed_count,
            )
        log_event(
            LOGGER,
            level="INFO",
            event=EventName.DB_WRITE_SUCCEEDED,
            cycle_id=cycle_id,
            message="New offers persisted successfully.",
            data={"new_count": result.new_count},
        )

    try:
        soft_deleted = store.soft_delete_removed_offers(offer.id for offer in offers)
        purged = store.purge_soft_deleted_offers()
    except SQLiteStoreError as error:
        log_event(
            LOGGER,
            level="ERROR",
            event=EventName.DB_CLEANUP_FAILED,
            cycle_id=cycle_id,
            message=f"Polling cycle aborted during persisted-offer cleanup: {error}",
        )
        return PollCycleResult(
            completed=False,
            mail_sent=result.mail_sent,
            new_count=result.new_count,
            existing_count=result.existing_count,
            removed_count=result.removed_count,
        )

    log_event(
        LOGGER,
        level="INFO",
        event=EventName.DB_CLEANUP_SUCCEEDED,
        cycle_id=cycle_id,
        message="Persisted-offer cleanup completed.",
        data={"soft_deleted": soft_deleted, "purged": purged},
    )
    log_event(
        LOGGER,
        level="INFO",
        event=EventName.CYCLE_COMPLETED,
        cycle_id=cycle_id,
        message="Polling cycle completed.",
        data={
            "mail_sent": result.mail_sent,
            "new_count": result.new_count,
            "existing_count": result.existing_count,
            "removed_count": result.removed_count,
        },
    )
    return result


def poll_forever(
    settings: Settings,
    store: SQLiteStore,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Run polling cycles indefinitely at the configured interval."""
    interval_seconds = settings.poll_interval_minutes * 60
    while True:
        cycle_id = uuid4().hex
        result = run_polling_cycle(settings, store, cycle_id=cycle_id)
        next_cycle_at = datetime.now(timezone.utc) + timedelta(seconds=interval_seconds)
        log_event(
            LOGGER,
            level="INFO",
            event=EventName.CYCLE_WAITING,
            cycle_id=cycle_id,
            message="Polling cycle finished; program is waiting for the next cycle.",
            data={
                "completed": result.completed,
                "sleep_seconds": interval_seconds,
                "next_cycle_at": next_cycle_at.isoformat().replace("+00:00", "Z"),
            },
        )
        sleep(interval_seconds)


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
                start_date=offer.start_date.astimezone(),
                end_date=offer.end_date.astimezone(),
                free_km=offer.free_km,
                origin=offer.origin,
                destination=offer.destination,
            )
        )
    return tuple(converted)
