import csv
import time
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from stations.models import FuelStation

DEFAULT_CSV_PATH = Path(settings.BASE_DIR) / "data" / "fuel-prices-for-be-assessment.csv"

# The assignment is explicitly USA-only (CLAUDE.md, spec.md), but the CSV
# contains ~620 rows with Canadian province codes (ON, BC, AB, ...). These
# must never be geocoded or offered as candidate stations: querying
# Nominatim for e.g. "Edmonton, AB, USA" doesn't fail cleanly — it can
# return a bogus but syntactically valid *US* match (this actually
# happened: "Edmonton, AB" geocoded to a point in Kentucky). Filtering by
# state code up front is the only reliable fix; a post-hoc bounding-box
# sanity check would not have caught that case, since the bad match still
# landed inside the US.
US_STATE_CODES = frozenset(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN "
    "MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA "
    "WA WV WI WY DC".split()
)


class RateLimitedError(Exception):
    """Nominatim returned 429 (or another 5xx-ish backoff signal). This is
    never the same thing as "not found" — retrying later should work, so
    the caller must not mark these rows geocode_source="failed" (that
    would exclude a real, geocodable place forever). The whole run stops
    on this rather than ploughing through remaining pairs while blocked."""


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
        parser.add_argument(
            "--fix-only",
            action="store_true",
            help="Apply data-integrity fixes (currently: non-US row exclusion) and exit "
            "without geocoding anything. Safe to run any time, makes no network calls.",
        )

    def handle(self, *args, **options):
        csv_path = Path(options["csv_path"])
        sleep_seconds = options["sleep"]

        self._load_csv_if_empty(csv_path)
        self._exclude_non_us_rows()

        if options["fix_only"]:
            self.stdout.write("--fix-only: exiting without geocoding.")
            return

        pairs = list(
            FuelStation.objects.filter(lat__isnull=True)
            .exclude(geocode_source__in=["failed", "non_us"])
            .values_list("city", "state")
            .distinct()
        )
        self.stdout.write(f"{len(pairs)} unique (city, state) pairs left to geocode.")

        session = requests.Session()
        session.headers.update({"User-Agent": settings.GEOCODING_USER_AGENT})

        geocoded, failed = 0, 0
        for i, (city, state) in enumerate(pairs, start=1):
            try:
                coords = self._geocode_city_state(session, city, state)
            except RateLimitedError:
                self.stdout.write(
                    self.style.ERROR(
                        f"[{i}/{len(pairs)}] Nominatim returned 429 (rate limited). "
                        f"Stopping here — {len(pairs) - i + 1} pairs left untouched, "
                        f"safe to resume later with the same command."
                    )
                )
                break

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

    def _exclude_non_us_rows(self):
        """Idempotent, self-correcting: run on every invocation, not just
        once, so it also resets any rows that got bad coordinates from a
        past run (before this filter existed) — not just rows that were
        never geocoded yet."""
        non_us = FuelStation.objects.exclude(state__in=US_STATE_CODES)
        already_bad = non_us.filter(lat__isnull=False).count()
        count = non_us.update(lat=None, lng=None, geocode_source="non_us")
        if already_bad:
            self.stdout.write(
                self.style.WARNING(
                    f"Reset {already_bad} non-US rows that had bogus coordinates "
                    f"from a prior run; {count} non-US rows excluded total."
                )
            )
        else:
            self.stdout.write(f"{count} non-US rows excluded (not geocoded, not candidates).")

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
        except requests.RequestException:
            # Network-level failure (timeout, connection error): treat as
            # transient, same as a rate limit — don't mark "failed", don't
            # keep hammering a server that might be having trouble.
            raise RateLimitedError

        if resp.status_code == 429 or resp.status_code >= 500:
            raise RateLimitedError

        try:
            resp.raise_for_status()
            results = resp.json()
        except (requests.RequestException, ValueError):
            return None

        if not results:
            return None
        return float(results[0]["lat"]), float(results[0]["lon"])
