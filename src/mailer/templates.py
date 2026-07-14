"""HTML templates for classified offer notification emails."""

from __future__ import annotations

from collections.abc import Iterable
from html import escape

from src.models.offer import ClassifiedOffer


def render_offer_email(
    new_offers: Iterable[ClassifiedOffer],
    existing_offers: Iterable[ClassifiedOffer],
) -> str:
    """Render the new and existing offer sections in a stable HTML structure.

    Highlighting is deliberately read from ``ClassifiedOffer.is_highlighted``.
    The renderer does not recalculate domain rules.
    """

    new = _validated_section(new_offers, expected_state="new", section_name="new")
    existing = _validated_section(
        existing_offers,
        expected_state="existing",
        section_name="existing",
    )

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <title>Movacar-Angebote</title>
  <style>
    body {{ font-family: Arial, sans-serif; color: #222; }}
    .offer-list {{ padding: 0; }}
    .offer {{ list-style: none; margin: 0 0 12px; padding: 12px; border: 1px solid #ddd; }}
    .offer--highlight {{ background: #fff3cd; border: 3px solid #d39e00; }}
    .highlight-label {{ color: #7a4f00; font-weight: bold; }}
    .empty-section {{ color: #666; font-style: italic; }}
  </style>
</head>
<body>
  <h1>Movacar-Angebote</h1>
  {_render_section("new-offers", "Neue Angebote", new)}
  {_render_section("existing-offers", "Bestehende Angebote", existing)}
</body>
</html>
"""


def render_offer_summary_email(offers: Iterable[ClassifiedOffer]) -> str:
    """Render a single overview of all currently available offers."""

    current = tuple(offers)
    for offer in current:
        if not isinstance(offer, ClassifiedOffer):
            raise TypeError("current offers must be ClassifiedOffer instances.")

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <title>Aktuelle Movacar-Angebote</title>
  <style>
    body {{ font-family: Arial, sans-serif; color: #222; }}
    .offer-list {{ padding: 0; }}
    .offer {{ list-style: none; margin: 0 0 12px; padding: 12px; border: 1px solid #ddd; }}
    .offer--highlight {{ background: #fff3cd; border: 3px solid #d39e00; }}
    .highlight-label {{ color: #7a4f00; font-weight: bold; }}
    .empty-section {{ color: #666; font-style: italic; }}
  </style>
</head>
<body>
  <h1>Aktuelle Movacar-Angebote</h1>
  {_render_section("current-offers", "Aktuelle Angebote", current)}
</body>
</html>
"""


def _validated_section(
    offers: Iterable[ClassifiedOffer],
    *,
    expected_state: str,
    section_name: str,
) -> tuple[ClassifiedOffer, ...]:
    validated = tuple(offers)
    for offer in validated:
        if not isinstance(offer, ClassifiedOffer):
            raise TypeError(f"{section_name} offers must be ClassifiedOffer instances.")
        if offer.state != expected_state:
            raise ValueError(
                f"{section_name} offers must have state '{expected_state}'."
            )
    return validated


def _render_section(
    section_id: str,
    heading: str,
    offers: tuple[ClassifiedOffer, ...],
) -> str:
    if not offers:
        content = '<p class="empty-section">Keine Angebote.</p>'
    else:
        content = '<ul class="offer-list">\n' + "\n".join(
            _render_offer(offer) for offer in offers
        ) + "\n</ul>"
    return f'  <section id="{section_id}">\n    <h2>{heading}</h2>\n    {content}\n  </section>'


def _render_offer(offer: ClassifiedOffer) -> str:
    highlight_class = " offer--highlight" if offer.is_highlighted else ""
    highlight_label = (
        '<div class="highlight-label" data-highlight="true">'
        "&Auml;u&szlig;erst interessant"
        "</div>"
        if offer.is_highlighted
        else ""
    )
    return f"""    <li class="offer{highlight_class}" data-offer-id="{escape(offer.id, quote=True)}">
      {highlight_label}
      <strong>{escape(offer.origin.city)} &rarr; {escape(offer.destination.city)}</strong>
      <div>Zeitraum: {offer.start_date.strftime("%d-%m-%Y")} bis {offer.end_date.strftime("%d-%m-%Y")}</div>
      <div>Freikilometer: {offer.free_km}</div>
    </li>"""
