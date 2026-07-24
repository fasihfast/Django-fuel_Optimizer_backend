"""
Usage:
    python manage.py load_fuel_stations                 # full load (~8,000 rows)
    python manage.py load_fuel_stations --limit 300      # quick smoke tes

"""
import csv
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.management.base import BaseCommand

from routing.models import FuelStation
from routing.services.geocode import geocode_city_state


class Command(BaseCommand):
    help = "Load the fuel prices CSV into the database, geocoding each unique city/state once."

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv",
            default=str(settings.BASE_DIR / "data" / "fuel-prices.csv"),
            help="Path to the fuel prices CSV file.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Only process the first N rows - useful for a quick smoke test.",
        )

    def handle(self, *args, **options):
        csv_path = options["csv"]
        limit = options["limit"]

        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if limit:
            rows = rows[:limit]

        self.stdout.write(f"Loaded {len(rows)} rows from {csv_path}")

        # Reuse any city/state pair we've already geocoded, from this run
        # or a previous one, so re-running this command is cheap.
        geocode_cache = {}
        already_geocoded = (
            FuelStation.objects.exclude(latitude__isnull=True)
            .values("city", "state", "latitude", "longitude")
            .distinct()
        )
        for row in already_geocoded:
            geocode_cache[(row["city"], row["state"])] = (row["latitude"], row["longitude"])

        created, updated, newly_geocoded, unresolved = 0, 0, 0, 0

        for row in rows:
            city = row["City"].strip()
            state = row["State"].strip()
            key = (city, state)

            if key not in geocode_cache:
                result = geocode_city_state(city, state)
                geocode_cache[key] = (result["latitude"], result["longitude"]) if result else (None, None)
                newly_geocoded += 1
                if newly_geocoded % 25 == 0:
                    self.stdout.write(f"  ...geocoded {newly_geocoded} new locations so far")

            lat, lon = geocode_cache[key]
            if lat is None:
                unresolved += 1

            try:
                price = Decimal(row["Retail Price"])
            except InvalidOperation:
                continue

            _, was_created = FuelStation.objects.update_or_create(
                opis_truckstop_id=int(row["OPIS Truckstop ID"]),
                defaults={
                    "name": row["Truckstop Name"].strip(),
                    "address": row["Address"].strip(),
                    "city": city,
                    "state": state,
                    "rack_id": row["Rack ID"].strip(),
                    "retail_price": price,
                    "latitude": lat,
                    "longitude": lon,
                },
            )
            created += 1 if was_created else 0
            updated += 0 if was_created else 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. {created} created, {updated} updated, "
                f"{newly_geocoded} new locations geocoded this run, "
                f"{unresolved} stations left without coordinates (geocoding found no match)."
            )
        )
