# Architecture

## Overview

The service answers one question per request: given a start and finish
location in the USA, what's the driving route, which fuel stops minimize
cost along the way (respecting a 500-mile vehicle range), and what's the
total fuel spend at 10 miles per gallon?

Two Django apps:

- **`stations`** — owns the `FuelStation` model and the offline
  `geocode_stations` management command that populates it from the
  provided CSV.
- **`routing`** — owns everything in the live request path: calling
  external services, querying candidate stations, running the selection
  algorithm, and the API surface itself.

## Request flow

```
POST /api/route/
  │
  ├─ 1. Geocode start_location   (Nominatim)
  ├─ 2. Geocode finish_location  (Nominatim)
  ├─ 3. Fetch route geometry     (OSRM)
  │
  ├─ 4. Bounding-box query for candidate stations (indexed DB query, local)
  ├─ 5. KD-tree + point-to-segment projection to assign each candidate
  │      a mile marker along the route (in-process, local)
  ├─ 6. Greedy cheapest-in-window stop selection (pure function, local)
  │
  └─ Response: route geometry, distance, fuel stops, total cost
```

Steps 1-3 are the only network calls in the request path — exactly three,
regardless of route length or how many fuel stops end up selected. Steps
4-6 never touch the network; they only read from the database and do
in-process computation.

## Why the external call count doesn't scale

Fuel station coordinates are never looked up live. Every station in the
CSV is geocoded once, offline, before the server ever handles a request
(see `stations/management/commands/geocode_stations.py`). At request
time, station lookups are a single indexed bounding-box query against
the whole table, followed by in-process filtering — no per-station or
per-segment network calls are possible by construction, because nothing
in that path makes an HTTP request at all.

## Data model

`FuelStation` (app: `stations`):

| Field | Purpose |
|---|---|
| `name`, `address`, `city`, `state`, `price` | From the source CSV |
| `lat`, `lng` | Filled in by `geocode_stations`; null until geocoded |
| `geocode_source` | `city_state` (geocoded), `failed` (genuinely not found), `non_us` (excluded — see below), or null (not yet processed) |

Indexed on `(lat, lng)` for the bounding-box query, and `(city, state)`
for the offline geocoding job's grouping step.

**Non-US rows**: the CSV includes a number of rows with Canadian province
codes rather than US state codes, despite this being a USA-only service.
Those rows are explicitly excluded from geocoding (see
`geocode_stations.py`'s `US_STATE_CODES` allowlist) — they are never
candidates for a fuel stop.

## Fuel-stop selection algorithm

Implemented as a pure function (`routing/algorithm.py`, no ORM, no
network) so it can be unit tested in isolation. Given a total route
distance and a list of candidate stations already positioned along the
route (mile marker + price), it walks the route in windows no larger than
the vehicle's 500-mile range, and in each window picks the **lowest-price**
station reachable, refueling to full there before continuing. This
directly targets the requirement that stops be cost-optimal, not simply
the nearest station.

Candidate positioning (which stations are "on this route" and where) is a
separate concern, handled in `routing/candidates.py`: an indexed
bounding-box query narrows ~8,000 stations down to a small candidate set
near the route, then a KD-tree plus point-to-segment projection assigns
each candidate an exact mile marker and a perpendicular distance from the
route ("corridor distance"). Candidates farther than a threshold (5 miles,
widening to 15 and 30 if a window would otherwise have no reachable
station) are excluded.

## Error handling

All request-path failures are mapped to a small set of documented error
codes (`routing/exceptions.py`) returned as `{"error": {"code", "message"}}`
with an appropriate 4xx status: `INVALID_INPUT` (bad request body),
`GEOCODE_FAILED` (start or finish couldn't be resolved),
`ROUTE_NOT_FOUND` (no drivable route between the two points), and
`NO_STATIONS_IN_RANGE` (a route segment has no reachable fuel station even
after widening the search corridor).
