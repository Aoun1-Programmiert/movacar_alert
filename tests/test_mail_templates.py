"""Unit tests for the classified offer HTML mail template."""

from datetime import datetime

import pytest

from src.mailer.templates import render_offer_email, render_offer_summary_email
from src.models.offer import ClassifiedOffer, GeoLocation


def make_classified(
    offer_id: str,
    *,
    state: str,
    is_highlighted: bool,
    origin_city: str = "Berlin",
) -> ClassifiedOffer:
    return ClassifiedOffer(
        id=offer_id,
        start_date=datetime(2026, 7, 14, 8, 0),
        end_date=datetime(2026, 7, 16, 8, 0),
        free_km=500,
        origin=GeoLocation(origin_city, 52.52, 13.405),
        destination=GeoLocation("Paris", 48.8566, 2.3522),
        is_highlighted=is_highlighted,
        state=state,  # type: ignore[arg-type]
    )


def test_render_contains_stable_new_and_existing_sections() -> None:
    html = render_offer_email(
        [make_classified("new-1", state="new", is_highlighted=False)],
        [make_classified("old-1", state="existing", is_highlighted=False)],
    )

    assert html.index('id="new-offers"') < html.index('id="existing-offers"')
    assert html.count("<section ") == 2
    assert 'data-offer-id="new-1"' in html
    assert 'data-offer-id="old-1"' in html
    assert "Neue Angebote" in html
    assert "Bestehende Angebote" in html


def test_highlighted_offer_has_visual_class_and_label() -> None:
    html = render_offer_email(
        [make_classified("highlighted", state="new", is_highlighted=True)],
        [],
    )

    assert 'class="offer offer--highlight"' in html
    assert 'data-highlight="true"' in html
    assert "&Auml;u&szlig;erst interessant" in html
    assert "background: #fff3cd" in html


def test_non_highlighted_offer_has_no_highlight_output() -> None:
    html = render_offer_email(
        [make_classified("regular", state="new", is_highlighted=False)],
        [],
    )

    assert 'class="offer offer--highlight"' not in html
    assert "data-highlight" not in html
    assert '<div class="highlight-label"' not in html


def test_renderer_formats_offer_dates_without_times() -> None:
    html = render_offer_email(
        [make_classified("dated", state="new", is_highlighted=False)],
        [],
    )

    assert "Zeitraum: 14-07-2026 bis 16-07-2026" in html
    assert "2026-07-14T08:00:00" not in html
    assert "2026-07-16T08:00:00" not in html


def test_renderer_escapes_offer_content_and_renders_empty_sections() -> None:
    html = render_offer_email(
        [make_classified('<new&1>', state="new", is_highlighted=False, origin_city="<Berlin>")],
        [],
    )

    assert 'data-offer-id="&lt;new&amp;1&gt;"' in html
    assert "&lt;Berlin&gt;" in html
    assert '<p class="empty-section">Keine Angebote.</p>' in html


@pytest.mark.parametrize(
    ("new_offers", "existing_offers", "error", "message"),
    (
        ([object()], [], TypeError, "ClassifiedOffer"),
        ([], [make_classified("wrong", state="new", is_highlighted=False)], ValueError, "existing"),
    ),
)
def test_renderer_requires_classified_offers_in_matching_sections(
    new_offers: list[object],
    existing_offers: list[object],
    error: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error, match=message):
        render_offer_email(new_offers, existing_offers)  # type: ignore[arg-type]


def test_summary_renderer_contains_all_current_offers() -> None:
    html = render_offer_summary_email(
        [
            make_classified("current-1", state="new", is_highlighted=True),
            make_classified("current-2", state="existing", is_highlighted=False),
        ]
    )

    assert "<h1>Aktuelles Update</h1>" in html
    assert "Aktuelle Movacar-Angebote" in html
    assert html.count('data-offer-id="current-') == 2
    assert 'data-offer-id="current-1"' in html
    assert 'data-offer-id="current-2"' in html


def test_summary_renderer_renders_empty_overview() -> None:
    html = render_offer_summary_email([])

    assert '<section id="current-offers">' in html
    assert '<p class="empty-section">Keine Angebote.</p>' in html
