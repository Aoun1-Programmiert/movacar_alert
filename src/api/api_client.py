"""HTTP transport for the Movacar offers API."""

from __future__ import annotations

import json
import logging
import socket
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.config.settings import Settings


HTTP_RETRY_DELAYS_SECONDS = (1, 2, 4)
MAX_RETRIES = len(HTTP_RETRY_DELAYS_SECONDS)

logger = logging.getLogger("movacar_alert.api.api_client")


class ApiClientError(RuntimeError):
    """Base error raised when the offers API cannot provide usable data."""


class ApiNetworkError(ApiClientError):
    """Raised after all retryable network requests have failed."""


class ApiResponseError(ApiClientError):
    """Raised when the API response is not valid offers JSON."""


def fetch_offers(settings: Settings) -> dict[str, Any]:
    """Fetch and validate the raw offers response using configured HTTP settings."""

    request = Request(settings.api_url, method="GET")

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
