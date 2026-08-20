import pytest

from stations.models import FuelStation

pytestmark = pytest.mark.django_db


def test_fuel_station_str():
    station = FuelStation.objects.create(
        opis_id=7,
        name="WOODSHED OF BIG CABIN",
        address="I-44, EXIT 283 & US-69",
        city="Big Cabin",
        state="OK",
        price="3.007",
    )
    assert str(station) == "WOODSHED OF BIG CABIN (Big Cabin, OK)"
    assert station.lat is None
    assert station.lng is None
