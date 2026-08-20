# Fuel route optimizer

Django API that takes a start and finish location in the USA and returns
the route, cost-optimal fuel stops (500-mile vehicle range), and total
fuel cost, using the provided fuel price dataset.

Built for the Spotter AI Backend Django Engineer take-home assessment.

## Development workflow

This repo follows spec-driven development. See `CLAUDE.md` for the full
workflow, and `.specs/001-fuel-route-api/spec.md` for the current feature
spec.

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # no API keys needed — OSRM + Nominatim are free/keyless; see plan.md
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
