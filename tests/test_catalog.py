"""Catalog scope and activity-specific availability."""

from custom_components.ned_energy_weather.catalog import CATALOG, scope


def test_scope_and_catalog():
    assert len(CATALOG) == 39
    assert {item.type_id for point, item in scope(7) if point == 7} == {1, 2}
    assert 0 not in CATALOG[28, 3].points
    assert CATALOG[24, 1].days == 0
    assert CATALOG[24, 2].days == 7
    assert CATALOG[54, 2].days == 1
    assert CATALOG[27, 1].days == 7
    assert CATALOG[27, 4].days == 1
