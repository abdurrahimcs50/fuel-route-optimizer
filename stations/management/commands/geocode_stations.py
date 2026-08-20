import csv
import time
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from stations.models import FuelStation

DEFAULT_CSV_PATH = Path(settings.BASE_DIR) / "data" / "fuel-prices-for-be-assessment.csv"


class Command(BaseCommand):
    """One-time (or resumable) offline job: load the fuel price CSV into
    FuelStation rows and geocode each unique (city, state) pair via
    Nominatim, at 1 request/sec per its usage policy.

    Infrastructure only — never run as part of a live request.
    """

    help = "Load fuel-prices CSV into FuelStation rows and geocode by (city, state)."

    def add_arguments(self, parser):
        parser.add_argument("--csv-path", default=str(DEFAULT_CSV_PATH))
        parser.add_argument(
            "--sleep",
            type=float,
            default=1.0,
            help="Seconds to sleep between Nominatim requests (policy minimum: 1.0)",
        )

    def handle(self, *args, **options):
        csv_path = Path(options["csv_path"])
        sleep_seconds = options["sleep"]

        self._load_csv_if_empty(csv_path)

        pairs = list(
            FuelStation.objects.filter(lat__isnull=True)
            .exclude(geocode_source="failed")
            .values_list("city", "state")
            .distinct()
        )
        self.stdout.write(f"{len(pairs)} unique (city, state) pairs left to geocode.")

        session = requests.Session()
        session.headers.update({"User-Agent": settings.GEOCODING_USER_AGENT})

        geocoded, failed = 0, 0
        for i, (city, state) in enumerate(pairs, start=1):
            coords = self._geocode_city_state(session, city, state)
            if coords is None:
                FuelStation.objects.filter(city=city, state=state, lat__isnull=True).update(
                    geocode_source="failed"
                )
                failed += 1
                self.stdout.write(f"[{i}/{len(pairs)}] FAILED  {city}, {state}")
            else:
                lat, lng = coords
                FuelStation.objects.filter(city=city, state=state, lat__isnull=True).update(
                    lat=lat, lng=lng, geocode_source="city_state"
                )
                geocoded += 1
                self.stdout.write(f"[{i}/{len(pairs)}] OK      {city}, {state} -> {lat:.4f},{lng:.4f}")

            if i < len(pairs):
                time.sleep(sleep_seconds)

        self.stdout.write(
            self.style.SUCCESS(f"Done. Geocoded {geocoded} pairs, {failed} failed.")
        )

    def _load_csv_if_empty(self, csv_path: Path):
        if FuelStation.objects.exists():
            self.stdout.write("FuelStation table already populated, skipping CSV load.")
            return

        self.stdout.write(f"Loading {csv_path} ...")
        rows = []
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rows.append(
                    FuelStation(
                        opis_id=int(row["OPIS Truckstop ID"]),
                        name=row["Truckstop Name"].strip(),
                        address=row["Address"].strip(),
                        city=row["City"].strip(),
                        state=row["State"].strip().upper(),
                        price=row["Retail Price"].strip(),
                    )
                )
        with transaction.atomic():
            FuelStation.objects.bulk_create(rows, batch_size=1000)
        self.stdout.write(self.style.SUCCESS(f"Loaded {len(rows)} rows."))

    def _geocode_city_state(self, session, city, state):
        try:
            resp = session.get(
                f"{settings.GEOCODING_BASE_URL}/search",
                params={
                    "q": f"{city}, {state}, USA",
                    "format": "json",
                    "limit": 1,
                },
                timeout=10,
            )
            resp.raise_for_status()
            results = resp.json()
        except (requests.RequestException, ValueError):
            return None

        if not results:
            return None
        return float(results[0]["lat"]), float(results[0]["lon"])
