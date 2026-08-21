# Fuel route optimizer

Django API that takes a start and finish location in the USA and returns
the route, cost-optimal fuel stops (500-mile vehicle range), and total
fuel cost, using the provided fuel price dataset.

Built for the Spotter AI Backend Django Engineer take-home assessment.

## Docs

- [`docs/architecture.md`](docs/architecture.md) — system design, request
  flow, and why the external API call count doesn't scale with route
  length or stop count.
- [`docs/algorithm.md`](docs/algorithm.md) — the fuel-stop selection
  algorithm, step by step.
- [`docs/api.md`](docs/api.md) — full API reference: request/response
  shapes and error codes.

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # no API keys needed — OSRM + Nominatim are free/keyless
python manage.py migrate
python manage.py geocode_stations   # one-time, ~65 min: geocode data/fuel-prices-for-be-assessment.csv
python manage.py runserver
```

## Usage

```bash
curl -X POST http://localhost:8000/api/route/ \
  -H "Content-Type: application/json" \
  -d '{"start_location": "Los Angeles, CA", "finish_location": "Dallas, TX"}'
```

A ready-to-import `postman_collection.json` is included at the repo root
with example requests (short route, long multi-stop route, cross-country,
and invalid-input cases). With `DEBUG=True` (the default), the API is also
browsable directly — visit `http://localhost:8000/api/route/` in a browser
for a form to submit requests without any client at all.

## Tests

```bash
pytest
```

`routing/tests/test_algorithm.py` covers the fuel-stop selection logic in
isolation (pure function, no DB/network). `routing/tests/test_candidates.py`
and `routing/tests/test_views.py` cover DB-backed corridor filtering and
the full request flow with external HTTP calls mocked.

## Demo

See the Loom walkthrough: _link to be added_
