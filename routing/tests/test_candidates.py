"""DB-backed tests for corridor filtering / mile-marker assignment. Uses a
tiny synthetic north-south route so distances are easy to reason about by
hand; no network calls (station coordinates come straight from the DB).
"""

import pytest

from routing.candidates import select_stops_for_route
from stations.models import FuelStation

pytestmark = pytest.mark.django_db

# A straight route running north along a fixed longitude, roughly 1 degree
# of latitude ~= 69 miles, used to build a route with a known, simple
# total distance.
ROUTE_GEOMETRY = {
    "type": "LineString",
    "coordinates": [[-97.0, 30.0], [-97.0, 37.0], [-97.0, 44.0]],  # [lng, lat]
}
START_COORDS = (30.0, -97.0)


def make_station(lat, lng, price, name="Station", city="City", state="TX"):
    return FuelStation.objects.create(
        opis_id=1, name=name, address="addr", city=city, state=state,
        price=price, lat=lat, lng=lng, geocode_source="city_state",
    )


def test_station_far_outside_bbox_is_excluded():
    make_station(lat=30.5, lng=-70.0, price=2.50, name="Far away")  # ~1600mi east
    result = select_stops_for_route(ROUTE_GEOMETRY, total_distance_miles=400, start_coords=START_COORDS)
    assert result.fuel_stops == []  # short route, no stops needed regardless
    # station shouldn't have influenced default_price either (too far from start)


def test_short_route_default_price_uses_nearest_station_to_start():
    make_station(lat=30.1, lng=-97.0, price=2.75, name="Near start", city="StartCity")
    make_station(lat=43.9, lng=-97.0, price=9.99, name="Near finish", city="FarCity")
    result = select_stops_for_route(ROUTE_GEOMETRY, total_distance_miles=400, start_coords=START_COORDS)
    assert result.fuel_stops == []
    assert result.total_fuel_cost == pytest.approx(400 / 10 * 2.75)


def test_long_route_selects_cheapest_station_on_corridor():
    # route is ~966mi raw (haversine over the 3 vertices), reported total
    # distance is passed in explicitly (as OSRM would provide it).
    # Window is (0, 500]: both "expensive" (~mile 193) and "cheapest"
    # (~mile 418) fall inside it; "off corridor" is priced lowest of all
    # but excluded by the 5mi corridor threshold, so it must not be picked.
    make_station(lat=33.0, lng=-97.0, price=3.80, name="On corridor, expensive", city="C1")
    make_station(lat=33.0, lng=-95.0, price=2.10, name="Off corridor", city="C2")  # ~120mi away, excluded
    make_station(lat=36.5, lng=-97.0, price=2.90, name="On corridor, cheapest", city="C3")

    result = select_stops_for_route(ROUTE_GEOMETRY, total_distance_miles=900, start_coords=START_COORDS)

    assert len(result.fuel_stops) == 1
    assert result.fuel_stops[0].name == "On corridor, cheapest"


def test_sparse_window_widens_corridor_before_failing():
    # Only station reachable in the first window is ~17 miles off the
    # corridor -> must fail at 5mi and 15mi thresholds, succeed once
    # widened to 30mi. total_distance_miles is kept small enough that,
    # once this single station is chosen, the remaining distance to the
    # finish is within one more tank (no second stop required).
    make_station(lat=33.0, lng=-97.29, price=3.00, name="~17mi off corridor", city="C1")
    result = select_stops_for_route(ROUTE_GEOMETRY, total_distance_miles=600, start_coords=START_COORDS)
    assert len(result.fuel_stops) == 1
    assert result.fuel_stops[0].name == "~17mi off corridor"
