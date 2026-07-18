"""HTTP transport for the Movacar offers API."""

from __future__ import annotations

import json
import logging
import socket
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from src.config.settings import Settings
from src.models.trip import Trip


HTTP_RETRY_DELAYS_SECONDS = (1, 2, 4)
MAX_RETRIES = len(HTTP_RETRY_DELAYS_SECONDS)

logger = logging.getLogger("movacar_alert.api.api_client")


class ApiClientError(RuntimeError):
    """Base error raised when the offers API cannot provide usable data."""


class ApiNetworkError(ApiClientError):
    """Raised after all retryable network requests have failed."""


class ApiResponseError(ApiClientError):
    """Raised when the API response is not valid offers JSON."""


def fetch_offers(settings: Settings, trip: Trip) -> dict[str, Any]:
    """Fetch and validate offers for one trip's pickup window."""

    request = Request(build_trip_url(settings.api_url, trip), method="GET")

    for attempt in range(MAX_RETRIES + 1):
        try:
            with urlopen(request, timeout=settings.http_timeout_seconds) as response:
                return _parse_response(response.read())
        except (HTTPError, URLError, TimeoutError, socket.timeout) as error:
            if attempt == MAX_RETRIES:
                logger.error(
                    "Offers API request failed after %s attempts: %s",
                    attempt + 1,
                    error,
                )
                raise ApiNetworkError(
                    f"Offers API request failed after {attempt + 1} attempts."
                ) from error

            delay = HTTP_RETRY_DELAYS_SECONDS[attempt]
            logger.warning(
                "Offers API request failed (attempt %s/%s); retrying in %ss: %s",
                attempt + 1,
                MAX_RETRIES + 1,
                delay,
                error,
            )
            time.sleep(delay)

    raise AssertionError("The retry loop must return or raise.")


def build_trip_url(api_url: str, trip: Trip) -> str:
    """Add the confirmed Movacar query parameters to the configured API URL."""

    parsed = urlsplit(api_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update(
        {
            "locale": "en",
            "pickupDateFrom": trip.pickup_start.isoformat(),
            "pickupDateTo": trip.pickup_end.isoformat(),
        }
    )
    return urlunsplit(parsed._replace(query=urlencode(query)))


def _parse_response(payload: bytes) -> dict[str, Any]:
    try:
        decoded = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ApiResponseError("Offers API returned invalid JSON.") from error

    if not isinstance(decoded, dict):
        raise ApiResponseError("Offers API response must be a JSON object.")
    if not isinstance(decoded.get("data"), list) or not isinstance(decoded.get("included"), list):
        raise ApiResponseError(
            "Offers API response must contain list-valued 'data' and 'included' fields."
        )
    return decoded
