# Fuel-stop selection algorithm

`routing/algorithm.py::select_fuel_stops()` — a pure function, fully
covered by `routing/tests/test_algorithm.py`.

## Inputs

- `total_distance_miles` — the route's total distance (from OSRM).
- `candidate_stations` — stations already positioned along the route,
  each with a `mile_marker` (distance from the start) and `price`. This
  positioning is computed separately in `routing/candidates.py`; the
  algorithm itself has no idea what a route geometry even is.
- `default_price` — used only for the short-route case below.
- `vehicle_range_miles` (500) and `mpg` (10) — the assignment's fixed
  constraints.

## Short routes (≤ 500 miles)

No stop is required — the vehicle is assumed to start full. `total_fuel_cost`
is still computed, using `default_price` (the cheapest station within 50
miles of the start location, or the dataset-wide average price as a
fallback) multiplied by `total_distance_miles / mpg`.

## Long routes (> 500 miles)

Walk forward from mile 0. At each point where more than one tank of range
remains to the finish:

1. Take the window of candidates reachable from the current position
   within the next 500 miles.
2. Pick the **lowest-price** candidate in that window. Ties are broken by
   picking the farthest one — maximizing distance covered before the next
   decision point, rather than an arbitrary pick.
3. Refuel to full: gallons purchased = distance traveled since the last
   stop, divided by 10 mpg.
4. Advance the current position to the chosen station and repeat.

The loop ends once the remaining distance to the finish fits within one
tank — no stop is needed for the final leg.

If a window has no reachable candidates at all, the caller
(`routing/candidates.py`) retries with a progressively wider search
corridor (5 → 15 → 30 miles) before giving up and returning a
`NO_STATIONS_IN_RANGE` error.

## Why cheapest-in-window, not global optimization

This is a greedy strategy, not a full dynamic-programming solve. A
theoretically optimal strategy would sometimes buy only enough fuel to
reach a cheaper station just out of range rather than always filling up —
that can beat this approach in specific pathological station layouts.
Cheapest-in-window with full refill was chosen because:

- It directly satisfies the actual requirement: pick the cheapest
  reachable option, not the nearest one.
- It's easy to reason about and verify: gallons purchased always equals
  distance traveled since the last stop, and total cost is simply the sum
  across stops.
- It's linear in the number of candidates per window, which is already
  small after corridor filtering.

## Rounding

Gallons are rounded to 2 decimal places *before* computing cost per stop,
and the reported `total_fuel_cost` is the sum of those already-rounded
per-stop costs. This keeps the numbers in the response internally
consistent — multiplying the displayed `gallons_purchased` by
`price_per_gallon` for any stop reproduces that stop's contribution to
`total_fuel_cost` exactly, rather than drifting by a fraction of a cent
against a higher-precision number never shown to the client.
