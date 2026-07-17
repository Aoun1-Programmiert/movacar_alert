"""HTML templates for trip-scoped notification emails."""

from __future__ import annotations

from html import escape

from src.models.offer import TripOfferView
from src.notifications.trip_mail_view import TripMailView


def render_offer_email(view: TripMailView) -> str:
    """Render an instant notification from a prepared trip mail view."""

    _validate_view(view)
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <title>Neue Angebote - {escape(view.trip.name)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; color: #222; }}
    .trip-details {{ background: #f5f5f5; padding: 12px; }}
    .offer-list {{ padding: 0; }}
    .offer {{ list-style: none; margin: 0 0 12px; padding: 12px; border: 1px solid #ddd; }}
    .offer--green {{ background: #d9f7d9; border: 2px solid #198754; }}
    .offer--yellow {{ background: #fff8d6; border: 1px solid #d39e00; }}
    .offer--neutral {{ background: #fff; }}
    .distance--green {{ color: #126b35; font-weight: bold; }}
    .distance--yellow {{ color: #7a5a00; }}
    .distance--neutral {{ color: #555; }}
    .empty-section {{ color: #666; font-style: italic; }}
  </style>
</head>
<body>
  <h1>Neue Movacar-Angebote</h1>
  {_render_trip_details(view)}
  {_render_section("new-offers", "Neue Angebote", view.new_offers)}
  {_render_section("available-offers", "Alle verfügbaren Angebote", view.available_offers)}
</body>
</html>
"""


def render_offer_summary_email(view: TripMailView) -> str:
    """Render a scheduled overview without delivery-state classifications."""

    _validate_view(view)
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <title>Aktuelle Angebote - {escape(view.trip.name)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; color: #222; }}
    .trip-details {{ background: #f5f5f5; padding: 12px; }}
    .offer-list {{ padding: 0; }}
    .offer {{ list-style: none; margin: 0 0 12px; padding: 12px; border: 1px solid #ddd; }}
    .offer--green {{ background: #d9f7d9; border: 2px solid #198754; }}
    .offer--yellow {{ background: #fff8d6; border: 1px solid #d39e00; }}
    .offer--neutral {{ background: #fff; }}
    .distance--green {{ color: #126b35; font-weight: bold; }}
    .distance--yellow {{ color: #7a5a00; }}
    .distance--neutral {{ color: #555; }}
    .empty-section {{ color: #666; font-style: italic; }}
  </style>
</head>
<body>
  <h1>Aktuelle Movacar-Angebote</h1>
  {_render_trip_details(view)}
  {_render_section("available-offers", "Alle verfügbaren Angebote", view.available_offers)}
</body>
</html>
"""


def _validate_view(view: TripMailView) -> None:
    if not isinstance(view, TripMailView):
        raise TypeError("mail view must be a TripMailView.")


def _render_trip_details(view: TripMailView) -> str:
    trip = view.trip
    return f"""  <section class="trip-details" aria-label="Reiseinformationen">
    <h2>Reiseinformationen</h2>
    <div><strong>Reise:</strong> {escape(trip.name)}</div>
    <div><strong>Pick-up-Zeitraum:</strong> {trip.pickup_start.strftime("%d.%m.%Y")} bis {trip.pickup_end.strftime("%d.%m.%Y")}</div>
    <div><strong>Startstadt:</strong> {escape(trip.start_city)}</div>
    <div><strong>Koordinaten:</strong> {trip.latitude:.5f}, {trip.longitude:.5f}</div>
  </section>"""


def _render_section(
    section_id: str,
    heading: str,
    offers: tuple[TripOfferView, ...],
) -> str:
    if not offers:
        content = '<p class="empty-section">Keine Angebote.</p>'
    else:
        content = '<ul class="offer-list">\n' + "\n".join(
            _render_offer(offer) for offer in offers
        ) + "\n</ul>"
    return f'  <section id="{section_id}">\n    <h2>{heading}</h2>\n    {content}\n  </section>'


def _render_offer(offer_view: TripOfferView) -> str:
    offer = offer_view.offer
    tier_class = f"offer--{offer_view.distance_tier.value}"
    distance_class = f"distance--{offer_view.distance_tier.value}"
    return f"""    <li class="offer {tier_class}" data-offer-id="{escape(offer.id, quote=True)}">
      <strong>{escape(offer.origin.city)} &rarr; {escape(offer.destination.city)}</strong>
      <div>Zeitraum: {offer.start_date.strftime("%d.%m.%Y")} bis {offer.end_date.strftime("%d.%m.%Y")}</div>
      <div>Freikilometer: {offer.free_km}</div>
      <div class="{distance_class}">Entfernung zur Startstadt: {offer_view.distance_km_rounded:.1f} km</div>
    </li>"""
