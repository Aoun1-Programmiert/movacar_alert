"""End-to-end integration scenarios for the complete offer-monitoring flow."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Any

import pytest

from src.config.settings import BoundingBox, Settings, SmtpSettings
from src.loop import poll_loop
from src.mailer.smtp_mailer import SmtpTransportError
from src.storage.sqlite_store import SQLiteStore


@pytest.fixture
def api_response() -> dict[str, Any]:
    fixture_path = Path(__file__).with_name("example_response.json")
    return json.loads(fixture_path.read_text(encoding="utf-8"))


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        api_url="https://api.example.test/offers",
        poll_interval_minutes=15,
        sqlite_path=tmp_path / "offers.sqlite",
        smtp=SmtpSettings(
            host="smtp.example.test",
            port=587,
            user="user",
            password="password",
            sender="sender@example.test",
            recipients=("recipient@example.test",),
            use_tls=True,
        ),
        http_timeout_seconds=15.0,
        de_bbox=BoundingBox(47.2701114, 55.058347, 5.8663425, 15.0418962),
        log_file_path=None,
    )


@pytest.fixture
def store(settings: Settings) -> SQLiteStore:
    sqlite_store = SQLiteStore(settings.sqlite_path)
    sqlite_store.initialize_schema()
    return sqlite_store


def test_new_fixture_offers_are_mailed_once_then_recognized_as_known(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    store: SQLiteStore,
    api_response: dict[str, Any],
) -> None:
    sent_bodies: list[str] = []
    monkeypatch.setattr(poll_loop, "fetch_offers", lambda _: api_response)
    monkeypatch.setattr(
        poll_loop,
        "send_html_email",
        lambda _smtp, html_body: sent_bodies.append(html_body),
    )

    first_cycle = poll_loop.run_polling_cycle(settings, store)
    second_cycle = poll_loop.run_polling_cycle(settings, store)

    offer_ids = {offer["id"] for offer in api_response["data"]}
    assert first_cycle.mail_sent is True
    assert first_cycle.new_count == len(offer_ids)
    assert second_cycle.mail_sent is False
    assert second_cycle.new_count == 0
    assert second_cycle.existing_count == len(offer_ids)
    assert len(sent_bodies) == 1
    assert set(store.read_offers()) == offer_ids


def test_removed_fixture_offers_are_soft_deleted_then_purged_after_retention(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    store: SQLiteStore,
    api_response: dict[str, Any],
) -> None:
    sent_bodies: list[str] = []
    monkeypatch.setattr(poll_loop, "send_html_email", lambda _smtp, html: sent_bodies.append(html))
    monkeypatch.setattr(poll_loop, "fetch_offers", lambda _: api_response)
    poll_loop.run_polling_cycle(settings, store)

    remaining_response = deepcopy(api_response)
    remaining_response["data"] = remaining_response["data"][:1]
    monkeypatch.setattr(poll_loop, "fetch_offers", lambda _: remaining_response)

    removal_cycle = poll_loop.run_polling_cycle(settings, store)

    remaining_id = remaining_response["data"][0]["id"]
    deleted_offers = {
        offer_id: offer
        for offer_id, offer in store.read_offers(include_deleted=True).items()
        if offer.is_deleted
    }
    assert removal_cycle.mail_sent is False
    assert removal_cycle.removed_count == len(api_response["data"]) - 1
    assert len(sent_bodies) == 1
    assert set(deleted_offers) == {
        offer["id"] for offer in api_response["data"][1:]
    }
    assert all(offer.deleted_at is not None for offer in deleted_offers.values())

    retention_time = max(
        datetime.fromisoformat(offer.deleted_at)
        for offer in deleted_offers.values()
        if offer.deleted_at is not None
    ) + timedelta(days=14, seconds=1)
    assert store.purge_soft_deleted_offers(now=retention_time) == len(deleted_offers)
    assert set(store.read_offers(include_deleted=True)) == {remaining_id}


def test_smtp_failure_keeps_new_fixture_offers_unpersisted(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    store: SQLiteStore,
    api_response: dict[str, Any],
) -> None:
    monkeypatch.setattr(poll_loop, "fetch_offers", lambda _: api_response)
    monkeypatch.setattr(
        poll_loop,
        "send_html_email",
        lambda _smtp, _html: (_ for _ in ()).throw(SmtpTransportError("rejected")),
    )

    result = poll_loop.run_polling_cycle(settings, store)

    assert result.completed is True
    assert result.mail_sent is False
    assert result.new_count == len(api_response["data"])
    assert store.read_offers(include_deleted=True) == {}
