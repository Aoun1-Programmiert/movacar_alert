"""Sequential, fault-isolated orchestration for trip offer monitoring."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import time

from src.api.api_client import ApiClientError, fetch_offers
from src.config.settings import Settings
from src.config.timezone import LOCAL_TIMEZONE
from src.mailer.smtp_mailer import SmtpSendError, send_html_email
from src.mailer.templates import render_offer_email, render_offer_summary_email
from src.models.offer import Offer, Trip
from src.notifications.instant_notification import (
    MissingTripRecipientsError,
    send_instant_trip_notification,
)
from src.notifications.trip_summary import send_due_trip_summary
from src.parser.offer_parser import OfferParsingError, parse_offers
from src.storage.sqlite_store import SQLiteStore, SQLiteStoreError
from src.synchronization.trip_offer_synchronizer import synchronize_trip_offers


LOGGER = logging.getLogger("movacar_alert.loop.poll_loop")


@dataclass(frozen=True)
class TripProcessingResult:
    """Result of processing one persisted trip."""

    trip_id: str
    trip_name: str
    completed: bool


@dataclass(frozen=True)
class OrchestrationCycleResult:
    """Result of one orchestration cycle across all persisted trips."""

    trip_results: tuple[TripProcessingResult, ...]
    completed: bool = True

    @property
    def idle(self) -> bool:
        """Return whether a successful trip lookup found no work."""

        return self.completed and not self.trip_results

    @property
    def completed_trip_count(self) -> int:
        """Return the number of trips whose fetch and synchronization completed."""

        return sum(result.completed for result in self.trip_results)


def run_orchestration_cycle(
    settings: Settings,
    store: SQLiteStore,
    *,
    now: datetime,
) -> OrchestrationCycleResult:
    """Load and sequentially process every trip while isolating trip failures."""

    try:
        trips = store.list_trips()
    except SQLiteStoreError as error:
        LOGGER.error("Reisen konnten nicht geladen werden: %s", error)
        return OrchestrationCycleResult((), completed=False)

    trip_results = tuple(
        _process_one_trip(settings, store, trip, now=now) for trip in trips
    )

    try:
        store.purge_unavailable_trip_offers(now=now)
    except SQLiteStoreError as error:
        LOGGER.error("Bereinigung nicht verfügbarer Reiseangebote fehlgeschlagen: %s", error)
        return OrchestrationCycleResult(trip_results, completed=False)

    return OrchestrationCycleResult(trip_results)


def _process_one_trip(
    settings: Settings,
    store: SQLiteStore,
    trip: Trip,
    *,
    now: datetime,
) -> TripProcessingResult:
    """Fetch, synchronize, and notify for one trip."""

    try:
        response = fetch_offers(settings, trip)
        offers = _with_local_dates(parse_offers(response))
    except (ApiClientError, OfferParsingError) as error:
        _log_trip_error(trip, "Abruf/Parsing", error)
        return TripProcessingResult(trip.trip_id, trip.name, completed=False)

    try:
        synchronization = synchronize_trip_offers(store, trip, offers)
    except SQLiteStoreError as error:
        _log_trip_error(trip, "Synchronisierung", error)
        return TripProcessingResult(trip.trip_id, trip.name, completed=False)

    try:
        instant_sent = send_instant_trip_notification(
            store,
            settings.smtp,
            trip,
            composer=render_offer_email,
            mailer=send_html_email,
        )
    except (SmtpSendError, MissingTripRecipientsError, SQLiteStoreError) as error:
        _log_trip_error(trip, "Sofortbenachrichtigung", error)
        instant_sent = False

    try:
        summary_sent = send_due_trip_summary(
            store,
            settings.smtp,
            trip,
            now,
            composer=render_offer_summary_email,
            mailer=send_html_email,
        )
    except (SmtpSendError, MissingTripRecipientsError, SQLiteStoreError) as error:
        _log_trip_error(trip, "Übersicht", error)
        summary_sent = False

    LOGGER.info(
        "Reise verarbeitet [id=%s, name=%s]: %d Angebote synchronisiert, "
        "Sofortmail=%s, Übersicht=%s.",
        trip.trip_id,
        trip.name,
        len(synchronization.offer_ids),
        "versendet" if instant_sent else "nicht versendet",
        "versendet" if summary_sent else "nicht versendet",
    )
    return TripProcessingResult(trip.trip_id, trip.name, completed=True)


def poll_forever(
    settings: Settings,
    store: SQLiteStore,
    *,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] | None = None,
) -> None:
    """Run trip orchestration cycles indefinitely at the configured interval."""

    interval_seconds = settings.poll_interval_minutes * 60
    clock = (lambda: datetime.now(LOCAL_TIMEZONE)) if now is None else now
    while True:
        cycle_now = _local_now(clock())
        result = run_orchestration_cycle(settings, store, now=cycle_now)
        next_cycle_at = _local_now(clock()) + timedelta(seconds=interval_seconds)
        if result.idle:
            LOGGER.info(
                "Keine Reisen konfiguriert; nächster Zyklus um %s.",
                next_cycle_at.strftime("%Y-%m-%d %H:%M:%S"),
            )
        elif result.completed:
            LOGGER.info(
                "Zyklus abgeschlossen: %d/%d Reisen erfolgreich verarbeitet. "
                "Nächster Zyklus um %s.",
                result.completed_trip_count,
                len(result.trip_results),
                next_cycle_at.strftime("%Y-%m-%d %H:%M:%S"),
            )
        sleep(interval_seconds)


def _log_trip_error(trip: Trip, phase: str, error: Exception) -> None:
    LOGGER.error(
        "Reise fehlgeschlagen [id=%s, name=%s, phase=%s]: %s",
        trip.trip_id,
        trip.name,
        phase,
        error,
    )


def _local_now(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=LOCAL_TIMEZONE)
    return value.astimezone(LOCAL_TIMEZONE)


def _with_local_dates(offers: Iterable[Offer]) -> tuple[Offer, ...]:
    """Convert parser-normalized timestamps to the configured local-time policy."""

    converted: list[Offer] = []
    for offer in offers:
        if offer.start_date.tzinfo is None or offer.start_date.utcoffset() is None:
            raise OfferParsingError("Offer start_date must include a timezone.")
        if offer.end_date.tzinfo is None or offer.end_date.utcoffset() is None:
            raise OfferParsingError("Offer end_date must include a timezone.")
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
