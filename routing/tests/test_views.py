"""Integration tests for POST /api/route/. All external HTTP calls are
mocked with `responses` — nothing here touches the real network, per
CLAUDE.md's guidance to keep the test suite hermetic.
"""

import json
import re

import pytest
import responses
from django.conf import settings
from django.test import Client

from stations.models import FuelStation

pytestmark = pytest.mark.django_db


def mock_geocode(lat, lng, query_matches_any=True):
    responses.add(
        responses.GET,
        f"{settings.GEOCODING_BASE_URL}/search",
        json=[{"lat": str(lat), "lon": str(lng)}],
        status=200,
    )


def mock_geocode_failure():
    responses.add(
        responses.GET,
        f"{settings.GEOCODING_BASE_URL}/search",
        json=[],
        status=200,
    )


def mock_osrm_route(coordinates, distance_meters, code="Ok"):
    body = {
        "code": code,
        "routes": [
            {
                "geometry": {"type": "LineString", "coordinates": coordinates},
                "distance": distance_meters,
            }
        ]
        if code == "Ok"
        else [],
    }
    responses.add(
        responses.GET,
        re.compile(rf"{re.escape(settings.ROUTING_API_BASE_URL)}/route/v1/driving/.*"),
        json=body,
        status=200,
    )


@responses.activate
def test_short_route_returns_no_stops():
    client = Client()
    mock_geocode(30.0, -97.0)
    mock_geocode(30.5, -97.0)  # ~35mi north, well under 500mi
    mock_osrm_route([[-97.0, 30.0], [-97.0, 30.5]], distance_meters=56000)

    FuelStation.objects.create(
        opis_id=1, name="Near start", address="a", city="c", state="TX",
        price="3.10", lat=30.05, lng=-97.0, geocode_source="city_state",
    )

    resp = client.post(
        "/api/route/",
        data=json.dumps({"start_location": "Austin, TX", "finish_location": "Georgetown, TX"}),
        content_type="application/json",
    )

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["fuel_stops"] == []
    assert body["total_distance_miles"] == pytest.approx(56000 / 1609.344, abs=0.1)
    assert body["total_fuel_cost"] > 0
    assert len(responses.calls) == 3  # geocode start, geocode finish, osrm route


@responses.activate
def test_long_route_returns_stops_and_total_cost():
    client = Client()
    mock_geocode(30.0, -97.0)
    mock_geocode(44.0, -97.0)
    # ~966mi raw haversine over 3 vertices; tell OSRM to report 600mi, so
    # exactly one stop (~mile 193) covers the rest of the trip in range.
    mock_osrm_route(
        [[-97.0, 30.0], [-97.0, 37.0], [-97.0, 44.0]],
        distance_meters=600 * 1609.344,
    )

    FuelStation.objects.create(
        opis_id=1, name="Mid station", address="a", city="c", state="TX",
        price="3.10", lat=33.0, lng=-97.0, geocode_source="city_state",
    )

    resp = client.post(
        "/api/route/",
        data=json.dumps({"start_location": "Austin, TX", "finish_location": "Somewhere, ND"}),
        content_type="application/json",
    )

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert len(body["fuel_stops"]) == 1
    assert body["fuel_stops"][0]["price_per_gallon"] == 3.10
    # total_fuel_cost is rounded to cents, like any currency figure — round
    # the expected value the same way rather than comparing to raw float
    # multiplication.
    assert body["total_fuel_cost"] == round(
        body["fuel_stops"][0]["gallons_purchased"] * 3.10, 2
    )
    assert len(responses.calls) == 3


def test_identical_start_and_finish_is_invalid_input():
    client = Client()
    resp = client.post(
        "/api/route/",
        data=json.dumps({"start_location": "Austin, TX", "finish_location": "Austin, TX"}),
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_INPUT"


def test_missing_fields_is_invalid_input():
    client = Client()
    resp = client.post(
        "/api/route/",
        data=json.dumps({"start_location": "Austin, TX"}),
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_INPUT"


@responses.activate
def test_ungeocodable_location_returns_422():
    client = Client()
    mock_geocode_failure()

    resp = client.post(
        "/api/route/",
        data=json.dumps({"start_location": "Nowhereville Zzyzx", "finish_location": "Austin, TX"}),
        content_type="application/json",
    )

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "GEOCODE_FAILED"


@responses.activate
def test_no_route_found_returns_422():
    client = Client()
    mock_geocode(30.0, -97.0)
    mock_geocode(21.3, -157.8)  # Honolulu, unreachable by road
    mock_osrm_route([], distance_meters=0, code="NoRoute")

    resp = client.post(
        "/api/route/",
        data=json.dumps({"start_location": "Austin, TX", "finish_location": "Honolulu, HI"}),
        content_type="application/json",
    )

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "ROUTE_NOT_FOUND"
