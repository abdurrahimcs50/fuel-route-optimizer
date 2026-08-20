"""Fuel-stop selection: a pure function, no Django ORM, no network calls.

Mile-marker assignment and corridor filtering happen upstream in
candidates.py (which needs the DB and route geometry); this module only
does the greedy walk-and-pick over an already-filtered, already-positioned
list of candidates. That split is what makes this the part of the codebase
that's cheap to unit test thoroughly.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class StationCandidate:
    id: int
    name: str
    address: str
    city: str
    state: str
    price: float
    mile_marker: float


@dataclass(frozen=True)
class FuelStop:
    name: str
    address: str
    city: str
    state: str
    price_per_gallon: float
    mile_marker: float
    gallons_purchased: float


@dataclass(frozen=True)
class SelectionResult:
    fuel_stops: list[FuelStop]
    total_fuel_cost: float


class NoStationsInRangeError(Exception):
    """Raised when a >500mi route has a window with zero reachable
    candidates at the corridor threshold the caller filtered with. The
    caller (candidates.py/views.py) is expected to retry with a wider
    corridor before giving up."""

    def __init__(self, window_start: float, window_end: float):
        self.window_start = window_start
        self.window_end = window_end
        super().__init__(
            f"No fuel station candidates in range [{window_start:.1f}, {window_end:.1f}] miles"
        )


def select_fuel_stops(
    total_distance_miles: float,
    candidate_stations: list[StationCandidate],
    default_price: float,
    vehicle_range_miles: float = 500,
    mpg: float = 10,
) -> SelectionResult:
    """Greedily pick the cheapest reachable station in each ``vehicle_range_miles``
    window, refueling to full at every mandatory stop.

    - Routes that fit in one tank (``total_distance_miles <= vehicle_range_miles``)
      need no stops; ``total_fuel_cost`` still uses ``default_price`` per the
      spec's short-trip behavior (see plan.md's Risks section for why).
    - Otherwise walks forward from mile 0, and at each point where more than
      one tank of range remains to the finish, picks the lowest-price
      candidate within the next ``vehicle_range_miles`` (ties broken by the
      farthest mile marker, to push the next decision point out as far as
      possible on cheap fuel).
    - Raises NoStationsInRangeError if a window has no candidates at all —
      the caller decides whether to retry with a wider corridor or surface
      NO_STATIONS_IN_RANGE to the client.
    """
    if total_distance_miles <= vehicle_range_miles:
        total_cost = round((total_distance_miles / mpg) * default_price, 2)
        return SelectionResult(fuel_stops=[], total_fuel_cost=total_cost)

    stations_by_marker = sorted(candidate_stations, key=lambda s: s.mile_marker)

    fuel_stops: list[FuelStop] = []
    position = 0.0
    total_cost = 0.0

    while total_distance_miles - position > vehicle_range_miles:
        window_end = position + vehicle_range_miles
        window = [s for s in stations_by_marker if position < s.mile_marker <= window_end]
        if not window:
            raise NoStationsInRangeError(position, window_end)

        chosen = min(window, key=lambda s: (s.price, -s.mile_marker))
        # Round gallons to the same precision reported in the response,
        # then cost from *that* rounded figure — so a client re-deriving
        # cost from the displayed gallons x price gets the same total we
        # report, instead of drifting by a rounding fraction of a cent.
        gallons = round((chosen.mile_marker - position) / mpg, 2)
        cost = gallons * chosen.price

        fuel_stops.append(
            FuelStop(
                name=chosen.name,
                address=chosen.address,
                city=chosen.city,
                state=chosen.state,
                price_per_gallon=chosen.price,
                mile_marker=round(chosen.mile_marker, 1),
                gallons_purchased=gallons,
            )
        )
        total_cost += cost
        position = chosen.mile_marker

    return SelectionResult(fuel_stops=fuel_stops, total_fuel_cost=round(total_cost, 2))
