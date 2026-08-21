# API reference

## `POST /api/route/`

### Request

```json
{
  "start_location": "Los Angeles, CA",
  "finish_location": "Dallas, TX"
}
```

Both fields are free-text place names or addresses — anywhere in the USA.
`start_location` and `finish_location` must differ.

### Response — `200 OK`

```json
{
  "route": {
    "type": "LineString",
    "coordinates": [[-118.24, 34.05], "..."]
  },
  "total_distance_miles": 1437.8,
  "fuel_stops": [
    {
      "name": "RaceTrac #2626",
      "address": "I-20 Exit 472",
      "city": "Dallas",
      "state": "TX",
      "price_per_gallon": 2.864,
      "mile_marker": 238.6,
      "gallons_purchased": 23.86
    }
  ],
  "total_fuel_cost": 68.34
}
```

- `route` — GeoJSON LineString of the driving route, directly renderable
  on a map.
- `total_distance_miles` — total route distance.
- `fuel_stops` — ordered list of mandatory refueling stops. Empty for
  routes that fit in one tank (≤ 500 miles).
- `total_fuel_cost` — total USD spent on fuel across the trip.

### Error responses

All errors share one shape:

```json
{ "error": { "code": "GEOCODE_FAILED", "message": "Could not geocode start_location: 'Nowhereville'" } }
```

| HTTP status | `code` | When |
|---|---|---|
| 400 | `INVALID_INPUT` | Missing/blank field, or `start_location` equals `finish_location` |
| 422 | `GEOCODE_FAILED` | Nominatim couldn't resolve the given location |
| 422 | `ROUTE_NOT_FOUND` | OSRM found no drivable route between the two points (e.g. an island destination) |
| 422 | `NO_STATIONS_IN_RANGE` | A 500-mile segment of the route has no reachable fuel station, even after widening the search corridor |

## Trying it out

- Import `postman_collection.json` (repo root) into Postman for ready-made
  example requests covering all of the above.
- With `DEBUG=True` (the default), the endpoint is also directly browsable
  at `http://localhost:8000/api/route/` — no client needed, just a form.
- `http://localhost:8000/admin/` gives a searchable/filterable view over
  every geocoded fuel station, useful for sanity-checking data along a
  specific route.
