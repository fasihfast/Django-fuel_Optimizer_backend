
""" Entity class """

from django.db import models


class FuelStation(models.Model):
    """
    One row from the fuel-prices CSV, enriched with latitude/longitude so
    we can figure out which stations lie along a given route.

    """

    opis_truckstop_id = models.IntegerField(db_index=True)
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=120)
    state = models.CharField(max_length=10)
    rack_id = models.CharField(max_length=20, blank=True)
    retail_price = models.DecimalField(max_digits=8, decimal_places=4)

    # Filled in once by the `load_fuel_stations` management command via
    # geocoding. Null until geocoded (some obscure city names may fail
    # to geocode and are simply skipped).
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["latitude", "longitude"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state}) - ${self.retail_price}"
