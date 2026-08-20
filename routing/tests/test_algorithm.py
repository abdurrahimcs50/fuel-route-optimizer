"""Pure-function tests for the greedy fuel-stop selector: no Django, no
DB, no network. Runs under plain pytest.
"""

import pytest

from routing.algorithm import (
    NoStationsInRangeError,
    StationCandidate,
    select_fuel_stops,
)


def station(id, mile_marker, price, name=None):
    return StationCandidate(
        id=id,
        name=name or f"Station {id}",
        address="123 Main St",
        city="Anytown",
        state="TX",
        price=price,
        mile_marker=mile_marker,
    )


def test_short_route_needs_no_stops():
    result = select_fuel_stops(
        total_distance_miles=300,
        candidate_stations=[station(1, 100, 3.00)],
        default_price=3.50,
    )
    assert result.fuel_stops == []
    # 300 miles / 10 mpg * $3.50 = $105.00
    assert result.total_fuel_cost == pytest.approx(105.00)


def test_route_exactly_at_range_needs_no_stops():
    result = select_fuel_stops(
        total_distance_miles=500,
        candidate_stations=[station(1, 250, 3.00)],
        default_price=3.20,
    )
    assert result.fuel_stops == []
    assert result.total_fuel_cost == pytest.approx(500 / 10 * 3.20)


def test_long_route_picks_cheapest_in_window_not_nearest():
    # 900 mile route: one window (0, 500]. A "nearest station" strategy
    # would pick the station at mile 50; cost-optimal must pick the $2.90
    # station at mile 480 instead.
    candidates = [
        station(1, 50, 3.50),   # nearest, but expensive
        station(2, 480, 2.90),  # farther, cheapest in window
        station(3, 495, 3.10),
    ]
    result = select_fuel_stops(
        total_distance_miles=900, candidate_stations=candidates, default_price=3.00
    )
    assert len(result.fuel_stops) == 1
    stop = result.fuel_stops[0]
    assert stop.mile_marker == 480
    assert stop.price_per_gallon == 2.90
    assert stop.gallons_purchased == pytest.approx(48.0)  # 480/10
    assert result.total_fuel_cost == pytest.approx(48.0 * 2.90)


def test_multi_leg_route_chains_stops_correctly():
    # 1100 miles total, two mandatory stops.
    candidates = [
        station(1, 480, 3.00),   # window 1: (0, 500]
        station(2, 900, 2.50),   # window 2: (480, 980]
        station(3, 950, 2.80),
    ]
    result = select_fuel_stops(
        total_distance_miles=1100, candidate_stations=candidates, default_price=3.00
    )
    assert [s.mile_marker for s in result.fuel_stops] == [480, 900]
    gallons_leg1 = 480 / 10
    gallons_leg2 = (900 - 480) / 10
    expected_cost = gallons_leg1 * 3.00 + gallons_leg2 * 2.50
    assert result.total_fuel_cost == pytest.approx(expected_cost)
    # final leg (900 -> 1100 = 200mi) is within range, no third stop needed


def test_tie_break_prefers_farthest_station():
    candidates = [
        station(1, 200, 3.00),
        station(2, 480, 3.00),  # same price, farther -> should win
    ]
    result = select_fuel_stops(
        total_distance_miles=900, candidate_stations=candidates, default_price=3.00
    )
    assert result.fuel_stops[0].mile_marker == 480


def test_no_stations_in_window_raises():
    candidates = [station(1, 600, 3.00)]  # outside the first (0, 500] window
    with pytest.raises(NoStationsInRangeError) as exc_info:
        select_fuel_stops(
            total_distance_miles=1000, candidate_stations=candidates, default_price=3.00
        )
    assert exc_info.value.window_start == 0
    assert exc_info.value.window_end == 500


def test_gallons_and_cost_are_arithmetically_correct():
    candidates = [station(1, 500, 4.00)]
    result = select_fuel_stops(
        total_distance_miles=800, candidate_stations=candidates, default_price=3.00
    )
    stop = result.fuel_stops[0]
    assert stop.gallons_purchased == pytest.approx(50.0)  # 500 miles / 10 mpg
    assert result.total_fuel_cost == pytest.approx(200.0)  # 50 gal * $4.00
