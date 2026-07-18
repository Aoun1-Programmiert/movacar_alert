"""Unit tests for the trip-scoped HTML mail templates."""

from datetime import date, datetime, timedelta

import pytest

from src.mailer.templates import render_offer_email, render_offer_summary_email
from src.models.offer import DistanceTier, GeoLocation, Offer, Trip, TripOfferView
from src.notifications.trip_mail_view import TripMailView


def make_trip() -> Trip:
    return Trip(
        trip_id="trip-1",
        name="Sommerfahrt",
        pickup_start=date(2026, 7, 20),
        pickup_end=date(2026, 7, 25),
        start_city="Berlin",
        latitude=52.52,
        longitude=13.405,
    )


def make_view(
    offer_id: str,
    distance_km: float,
    *,
    state: str = "new",
    is_sent: bool = False,
    trip: Trip | None = None,
    duration: timedelta = timedelta(days=2),
    origin: GeoLocation | None = None,
) -> TripOfferView:
    start_date = datetime(2026, 7, 20, 8)
    return TripOfferView(
        trip=trip or make_trip(),
        offer=Offer(
            id=offer_id,
            start_date=start_date,
            end_date=start_date + duration,
            free_km=500,
            origin=origin or GeoLocation("Potsdam", 52.4, 13.1),
            destination=GeoLocation("Paris", 48.8566, 2.3522),
        ),
        distance_km=distance_km,
        is_available=True,
        state=state,  # type: ignore[arg-type]
        is_sent=is_sent,
        distance_tier=DistanceTier.for_distance(distance_km),
    )


def test_instant_template_renders_trip_details_and_new_offers_first() -> None:
    trip = make_trip()
    new_offer = make_view("new-1", 99.95, trip=trip)
    available_offer = make_view("old-1", 250, state="existing", is_sent=True, trip=trip)
    view = TripMailView(
        trip,
        ("recipient@example.test",),
        (new_offer,),
        (new_offer, available_offer),
        "https://api.example.test/offers?pickupDateFrom=2026-07-20&pickupDateTo=2026-07-25",
    )

    html = render_offer_email(view)

    assert "Hier der Link zu den Angeboten" in html
    assert (
        'href="https://api.example.test/offers?pickupDateFrom=2026-07-20&amp;'
        'pickupDateTo=2026-07-25"'
    ) in html
    assert "Angebote insgesamt: 2" in html
    assert html.index("Hier der Link zu den Angeboten") < html.index('id="new-offers"')
    assert html.index('id="new-offers"') < html.index('id="available-offers"')
    assert html.index('data-offer-id="new-1"') < html.index(
        'id="available-offers"'
    )
    assert "Sommerfahrt" in html
    assert "20.07.2026 bis 25.07.2026" in html
    assert "Startstadt:</strong> Berlin" in html
    assert "Koordinaten:" not in html
    assert "Entfernung zur Startstadt: 100.0 km" in html
    assert html.count('data-offer-id="new-1"') == 2


@pytest.mark.parametrize(
    ("distance", "offer_class", "distance_class"),
    (
        (99.999, "offer--red", "distance--red"),
        (100, "offer--orange", "distance--orange"),
        (249.999, "offer--orange", "distance--orange"),
        (250, "offer--yellow", "distance--yellow"),
        (499.999, "offer--yellow", "distance--yellow"),
        (500, "offer--neutral", "distance--neutral"),
    ),
)
def test_template_renders_all_distance_tiers(
    distance: float, offer_class: str, distance_class: str
) -> None:
    view = make_view("distance", distance)

    html = render_offer_email(TripMailView(make_trip(), ("a@example.test",), (view,), (view,)))

    assert f'class="offer {offer_class}"' in html
    assert f'class="{distance_class}"' in html


def test_template_uses_trip_distance_tier_without_legacy_duration_or_country_rules() -> None:
    view = make_view(
        "short-domestic",
        99,
        duration=timedelta(hours=1),
        origin=GeoLocation("Paris", 48.8566, 2.3522),
    )

    html = render_offer_email(TripMailView(make_trip(), ("a@example.test",), (view,), (view,)))

    assert 'class="offer offer--red"' in html
    assert 'class="distance--red"' in html


def test_summary_contains_trip_and_distance_without_new_offer_classification() -> None:
    trip = make_trip()
    offer = make_view("current", 12.3, trip=trip)
    view = TripMailView(
        trip,
        ("recipient@example.test",),
        (),
        (offer,),
        "https://api.example.test/offers",
    )

    html = render_offer_summary_email(view)

    assert "Reiseinformationen" in html
    assert (
        '<a href="https://api.example.test/offers">Hier der Link zu den Angeboten</a>'
        " <span>Angebote insgesamt: 1</span>"
    ) in html
    assert "Koordinaten:" not in html
    assert "Entfernung zur Startstadt: 12.3 km" in html
    assert "Neue Angebote" not in html
    assert "Versendet" not in html
    assert "Neu" not in html
    assert html.count('data-offer-id="current"') == 1


def test_template_escapes_trip_and_offer_content_and_renders_empty_sections() -> None:
    trip = Trip(
        trip_id="trip-1",
        name="<Sommerfahrt>",
        pickup_start=date(2026, 7, 20),
        pickup_end=date(2026, 7, 25),
        start_city="<Berlin>",
        latitude=52.52,
        longitude=13.405,
    )
    offer = make_view("<offer&1>", 20, trip=trip)
    escaped_offer = Offer(
        id=offer.offer.id,
        start_date=offer.offer.start_date,
        end_date=offer.offer.end_date,
        free_km=offer.offer.free_km,
        origin=GeoLocation("<Potsdam>", 52.4, 13.1),
        destination=offer.offer.destination,
    )
    offer = TripOfferView(
        trip=trip,
        offer=escaped_offer,
        distance_km=20,
        is_available=True,
        state="new",
        is_sent=False,
        distance_tier=DistanceTier.RED,
    )
    view = TripMailView(trip, ("a@example.test",), (offer,), (offer,))

    html = render_offer_email(view)

    assert "&lt;Sommerfahrt&gt;" in html
    assert "&lt;Berlin&gt;" in html
    assert 'data-offer-id="&lt;offer&amp;1&gt;"' in html
    assert "&lt;Potsdam&gt;" in html
    assert '<p class="empty-section">Keine Angebote.</p>' not in html

    empty_view = TripMailView(trip, ("a@example.test",), (), ())
    assert '<p class="empty-section">Keine Angebote.</p>' in render_offer_email(empty_view)


@pytest.mark.parametrize("renderer", (render_offer_email, render_offer_summary_email))
def test_templates_require_prepared_trip_mail_view(renderer: object) -> None:
    with pytest.raises(TypeError, match="TripMailView"):
        renderer(object())  # type: ignore[operator]
