"""Unit tests for polling-cycle orchestration."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.api.api_client import ApiNetworkError
from src.loop import poll_loop
from src.logging.logger import configure_logger
from src.mailer.smtp_mailer import SmtpTransportError
from src.models.offer import GeoLocation, Offer
from src.parser.offer_parser import OfferParsingError
from src.storage.sqlite_store import SQLiteStoreError


class FakeStore:
    """In-memory storage spy for orchestration tests."""

    def __init__(self, known: dict[str, object] | None = None) -> None:
        self.known = {} if known is None else known
        self.calls: list[object] = []

    def read_offers(self) -> dict[str, object]:
        self.calls.append("read")
        return self.known

    def insert_offers(self, offers: object) -> None:
        self.calls.append(("insert", tuple(offer.id for offer in offers)))

    def soft_delete_removed_offers(self, active_ids: object) -> int:
        self.calls.append(("soft_delete", tuple(active_ids)))
        return 1

    def purge_soft_deleted_offers(self) -> int:
        self.calls.append("purge")
        return 1


@pytest.fixture
def settings() -> SimpleNamespace:
    return SimpleNamespace(
        de_bbox=None,
        smtp=object(),
        poll_interval_minutes=15,
    )


@pytest.fixture
def offer() -> Offer:
    start = datetime(2026, 7, 14, 8, tzinfo=timezone.utc)
    return Offer(
        id="new-offer",
        start_date=start,
        end_date=start + timedelta(days=2),
        free_km=500,
        origin=GeoLocation("Berlin", 52.52, 13.405),
        destination=GeoLocation("Paris", 48.8566, 2.3522),
    )


def _stub_response(monkeypatch: pytest.MonkeyPatch, offer: Offer) -> None:
    monkeypatch.setattr(poll_loop, "fetch_offers", lambda settings: {"data": [], "included": []})
    monkeypatch.setattr(poll_loop, "parse_offers", lambda response: [offer])


def test_new_offers_are_mailed_before_being_persisted_and_then_cleaned(
    monkeypatch: pytest.MonkeyPatch, settings: SimpleNamespace, offer: Offer
) -> None:
    store = FakeStore()
    _stub_response(monkeypatch, offer)

    def send(smtp: object, html: str) -> None:
        store.calls.append("send")
        assert "Neue Angebote" in html

    monkeypatch.setattr(poll_loop, "send_html_email", send)

    result = poll_loop.run_polling_cycle(settings, store)  # type: ignore[arg-type]

    assert result == poll_loop.PollCycleResult(
        completed=True, mail_sent=True, new_count=1, existing_count=0, removed_count=0
    )
    assert store.calls == [
        "read",
        "send",
        ("insert", ("new-offer",)),
        ("soft_delete", ("new-offer",)),
        "purge",
    ]


def test_successful_cycle_logs_summary_before_sleep(
    monkeypatch: pytest.MonkeyPatch,
    settings: SimpleNamespace,
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "movacar.log"
    monkeypatch.setattr(
        poll_loop,
        "LOGGER",
        configure_logger(log_path, logger_name="movacar_alert.loop.poll_loop"),
    )
    monkeypatch.setattr(
        poll_loop,
        "run_polling_cycle",
        lambda settings, store: poll_loop.PollCycleResult(
            completed=True, mail_sent=True, new_count=2
        ),
    )

    with pytest.raises(RuntimeError, match="stop test loop"):
        poll_loop.poll_forever(
            settings,
            object(),
            sleep=lambda seconds: (_ for _ in ()).throw(RuntimeError("stop test loop")),
        )

    log_line = log_path.read_text(encoding="utf-8")
    assert "INFO — Erfolgreicher Polling-Durchlauf: 2 neue Angebote gesichtet;" in log_line
    assert "eine E-Mail versendet. Nächster Durchlauf um " in log_line


def test_no_new_offers_skip_mail_but_still_cleanup_and_purge(
    monkeypatch: pytest.MonkeyPatch, settings: SimpleNamespace, offer: Offer
) -> None:
    store = FakeStore(known={offer.id: object(), "removed": object()})
    _stub_response(monkeypatch, offer)
    monkeypatch.setattr(
        poll_loop,
        "send_html_email",
        lambda smtp, html: pytest.fail("No email may be sent without new offers."),
    )

    result = poll_loop.run_polling_cycle(settings, store)  # type: ignore[arg-type]

    assert result == poll_loop.PollCycleResult(
        completed=True, mail_sent=False, new_count=0, existing_count=1, removed_count=1
    )
    assert store.calls == [
        "read",
        ("soft_delete", ("new-offer",)),
        "purge",
    ]


def test_smtp_failure_leaves_new_offers_unpersisted(
    monkeypatch: pytest.MonkeyPatch, settings: SimpleNamespace, offer: Offer, caplog: pytest.LogCaptureFixture
) -> None:
    store = FakeStore()
    _stub_response(monkeypatch, offer)
    monkeypatch.setattr(
        poll_loop,
        "send_html_email",
        lambda smtp, html: (_ for _ in ()).throw(SmtpTransportError("rejected")),
    )

    with caplog.at_level("ERROR"):
        result = poll_loop.run_polling_cycle(settings, store)  # type: ignore[arg-type]

    assert result == poll_loop.PollCycleResult(
        completed=True, mail_sent=False, new_count=1, existing_count=0, removed_count=0
    )
    assert store.calls == ["read"]
    assert "mail delivery failed" in caplog.text


@pytest.mark.parametrize(
    ("error", "expected_text"),
    (
        (ApiNetworkError("offline"), "fetching or parsing"),
        (OfferParsingError("malformed"), "fetching or parsing"),
    ),
)
def test_api_and_parser_failures_are_logged_and_abort_only_current_cycle(
    monkeypatch: pytest.MonkeyPatch,
    settings: SimpleNamespace,
    error: Exception,
    expected_text: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = FakeStore()
    monkeypatch.setattr(
        poll_loop,
        "fetch_offers",
        lambda settings: (_ for _ in ()).throw(error),
    )

    with caplog.at_level("ERROR"):
        result = poll_loop.run_polling_cycle(settings, store)  # type: ignore[arg-type]

    assert result == poll_loop.PollCycleResult(completed=False, mail_sent=False)
    assert store.calls == []
    assert expected_text in caplog.text


def test_database_errors_are_logged_and_abort_only_current_cycle(
    monkeypatch: pytest.MonkeyPatch,
    settings: SimpleNamespace,
    offer: Offer,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _stub_response(monkeypatch, offer)
    store = FakeStore()
    monkeypatch.setattr(
        store,
        "read_offers",
        lambda: (_ for _ in ()).throw(SQLiteStoreError("unavailable")),
    )

    with caplog.at_level("ERROR"):
        result = poll_loop.run_polling_cycle(settings, store)  # type: ignore[arg-type]

    assert result == poll_loop.PollCycleResult(completed=False, mail_sent=False)
    assert "reading persisted offers" in caplog.text


def test_cycle_converts_dates_to_local_time_before_matching(
    monkeypatch: pytest.MonkeyPatch, settings: SimpleNamespace, offer: Offer
) -> None:
    store = FakeStore()
    captured: list[Offer] = []
    _stub_response(monkeypatch, offer)

    def capture_delta(offers: object, known: object, bbox: object) -> object:
        captured.extend(offers)
        return SimpleNamespace(
            new=(),
            existing=(),
            new_count=0,
            existing_count=0,
            removed_count=0,
        )

    monkeypatch.setattr(poll_loop, "calculate_delta", capture_delta)

    poll_loop.run_polling_cycle(settings, store)  # type: ignore[arg-type]

    assert captured[0].start_date == offer.start_date.astimezone()
    assert captured[0].end_date == offer.end_date.astimezone()
    assert captured[0].start_date.tzinfo == datetime.now().astimezone().tzinfo


def test_poll_forever_sleeps_for_configured_interval(
    monkeypatch: pytest.MonkeyPatch, settings: SimpleNamespace
) -> None:
    calls: list[object] = []

    def run_cycle(settings: SimpleNamespace, store: object) -> poll_loop.PollCycleResult:
        calls.append("cycle")
        return poll_loop.PollCycleResult(completed=True, mail_sent=False)

    monkeypatch.setattr(poll_loop, "run_polling_cycle", run_cycle)

    def stop_after_first_sleep(seconds: float) -> None:
        calls.append(seconds)
        raise RuntimeError("stop test loop")

    with pytest.raises(RuntimeError, match="stop test loop"):
        poll_loop.poll_forever(settings, object(), sleep=stop_after_first_sleep)  # type: ignore[arg-type]

    assert calls == ["cycle", 900]
