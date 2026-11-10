"""Entity identity across reloads and provinces."""

from custom_components.ned_energy_weather.sensor import unique_id


def test_unique_id():
    assert unique_id(0, 2, 1, "capacity") == "0_2_1_capacity"
    assert unique_id(7, 2, 1, "capacity") != unique_id(8, 2, 1, "capacity")
    assert unique_id(0, 27, 1, "capacity") != unique_id(0, 27, 3, "capacity")
