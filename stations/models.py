from django.db import models


class FuelStation(models.Model):
    """One row per CSV row in data/fuel-prices-for-be-assessment.csv.

    Duplicate truckstops in the source data (same name/address, different
    OPIS id) are kept as separate rows rather than de-duplicated.
    """

    opis_id = models.IntegerField()
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    price = models.DecimalField(max_digits=6, decimal_places=3)

    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)
    geocode_source = models.CharField(max_length=20, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["lat", "lng"], name="station_lat_lng_idx"),
            models.Index(fields=["city", "state"], name="station_city_state_idx"),
        ]

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state})"
