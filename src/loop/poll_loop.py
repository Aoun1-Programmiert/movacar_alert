"""Polling-cycle orchestration for offer monitoring."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import time

from src.api.api_client import ApiClientError, fetch_offers
from src.config.settings import Settings
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
        result = run_polling_cycle(settings, store)
        if result.completed and (result.new_count == 0 or result.mail_sent):
            next_cycle_at = datetime.now() + timedelta(seconds=interval_seconds)
            email_status = "eine" if result.mail_sent else "keine"
            LOGGER.info(
                "Erfolgreicher Polling-Durchlauf: %s neue Angebote gesichtet; "
                "%s E-Mail versendet. Nächster Durchlauf um %s.",
                result.new_count,
                email_status,
                next_cycle_at.strftime("%Y-%m-%d %H:%M:%S"),
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
