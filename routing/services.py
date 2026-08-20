"""The only module in this codebase allowed to call Nominatim or OSRM live.

Every external call is logged with `external_call=...` and the caller's
`request_id`, so validate-implementation can grep logs and prove the
per-request call count.
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger("routing")


class GeocodeError(Exception):
    pass


class RouteNotFoundError(Exception):
    pass


def geocode_location(text: str, request_id: str) -> tuple[float, float]:
    """Geocode a free-text place name/address via Nominatim. Raises
    GeocodeError if it can't be resolved."""
    try:
        resp = requests.get(
            f"{settings.GEOCODING_BASE_URL}/search",
            params={"q": text, "format": "json", "limit": 1},
            headers={"User-Agent": settings.GEOCODING_USER_AGENT},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.info(
            "external_call=geocode request_id=%s query=%r status=error error=%s",
            request_id, text, exc,
        )
        raise GeocodeError(f"Geocoding request failed for {text!r}") from exc

    logger.info(
        "external_call=geocode request_id=%s query=%r status=%s results=%d",
        request_id, text, resp.status_code, len(results),
    )

    if not results:
        raise GeocodeError(f"Could not geocode {text!r}")

    return float(results[0]["lat"]), float(results[0]["lon"])


def get_route(
    start: tuple[float, float], finish: tuple[float, float], request_id: str
) -> tuple[dict, float]:
    """Fetch route geometry + total distance from OSRM. Coordinates are
    (lat, lng) in, matching everywhere else in this codebase; OSRM itself
    wants lng,lat in the URL. Raises RouteNotFoundError if OSRM has no
    drivable route between the two points."""
    start_lat, start_lng = start
    finish_lat, finish_lng = finish

    try:
        resp = requests.get(
            f"{settings.ROUTING_API_BASE_URL}/route/v1/driving/"
            f"{start_lng},{start_lat};{finish_lng},{finish_lat}",
            params={"overview": "full", "geometries": "geojson", "steps": "false"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.info(
            "external_call=osrm_route request_id=%s status=error error=%s",
            request_id, exc,
        )
        raise RouteNotFoundError("Routing request failed") from exc

    logger.info(
        "external_call=osrm_route request_id=%s status=%s code=%s",
        request_id, resp.status_code, data.get("code"),
    )

    if data.get("code") != "Ok" or not data.get("routes"):
        raise RouteNotFoundError("No drivable route found between the two locations")

    route = data["routes"][0]
    geometry = route["geometry"]  # GeoJSON LineString, coordinates as [lng, lat]
    distance_miles = route["distance"] / 1609.344  # meters -> miles

    return geometry, distance_miles
