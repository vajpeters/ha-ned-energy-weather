"""NED public catalog, keyed by type and activity rather than type alone."""

from dataclasses import dataclass

from .const import CLASSIFICATIONS, GRANULARITIES, PROVINCES


@dataclass(frozen=True)
class Dataset:
    type_id: int
    activity: int
    name: str
    category: str
    days: int = 0
    emissions: bool = False
    points: tuple[int, ...] = (0,)
    granularities: tuple[int, ...] = tuple(GRANULARITIES.values())

    @property
    def classifications(self) -> tuple[int, ...]:
        return (CLASSIFICATIONS["actual"], CLASSIFICATIONS["forecast"]) if self.days else (2,)

    @property
    def fields(self) -> tuple[str, ...]:
        base = ("capacity", "volume", "percentage")
        return (*base, "emission", "emission_factor") if self.emissions else base


POWER = "electricity_production"
RENEWABLE = "renewable_energy"
GAS = "gas_consumption"
FLOW = "network_flow"
PROVINCIAL = (0, *PROVINCES)
CATALOG = {
    (item.type_id, item.activity): item
    for item in (
        Dataset(1, 1, "Onshore wind", POWER, 7, points=PROVINCIAL),
        Dataset(2, 1, "Solar", POWER, 7, points=PROVINCIAL),
        Dataset(
            17,
            1,
            "Offshore wind by wind farm",
            POWER,
            7,
            points=(0, 28, 29, 30, 31, 33, 34, 35, 36),
        ),
        Dataset(18, 1, "Gas-fired electricity", POWER, 7, True),
        Dataset(19, 1, "Coal-fired electricity", POWER, 7, True),
        Dataset(20, 1, "Nuclear", POWER, 7),
        Dataset(21, 1, "Waste-fired electricity", POWER, 7, True),
        Dataset(22, 1, "Offshore wind B", POWER),
        Dataset(25, 1, "Biomass electricity", POWER, 7),
        Dataset(26, 1, "Other electricity", POWER, 7),
        Dataset(27, 1, "Electricity production", POWER, 7, True),
        Dataset(35, 1, "Combined heat and power", POWER, 7, True),
        Dataset(51, 1, "Offshore wind", POWER, 7),
        Dataset(59, 2, "Electricity consumption", "electricity_consumption", 7),
        Dataset(24, 1, "Biomethane production", "heat_production"),
        Dataset(0, 1, "Total renewable energy", RENEWABLE),
        Dataset(3, 1, "Biogas energy", RENEWABLE, points=(0, *range(15, 28))),
        Dataset(4, 1, "Heat pumps", RENEWABLE),
        Dataset(8, 1, "Biomass co-firing", RENEWABLE),
        Dataset(9, 1, "Geothermal", RENEWABLE),
        Dataset(10, 1, "Other renewable generation", RENEWABLE),
        Dataset(11, 1, "Waste energy", RENEWABLE),
        Dataset(12, 1, "Bio-oil", RENEWABLE),
        Dataset(13, 1, "Biomass heat", RENEWABLE),
        Dataset(14, 1, "Wood combustion", RENEWABLE),
        Dataset(50, 1, "Solar thermal", RENEWABLE),
        Dataset(24, 2, "Biomethane consumption", GAS, 7),
        Dataset(28, 2, "Non-renewable gas consumption", GAS, emissions=True),
        Dataset(53, 2, "Industrial gas consumption", GAS, 7, True),
        Dataset(54, 2, "Power plant gas consumption", GAS, 1, True),
        Dataset(55, 2, "Local distribution gas consumption", GAS, 7, True),
        Dataset(56, 2, "Total gas consumption", GAS, emissions=True),
        Dataset(27, 3, "Electricity import", FLOW, 1, points=(0, *range(37, 42))),
        Dataset(27, 4, "Electricity export", FLOW, 1, points=(0, *range(37, 42))),
        Dataset(28, 3, "Gas import", FLOW, points=(*range(42, 64), 80, 81)),
        Dataset(28, 4, "Gas export", FLOW, points=tuple(range(42, 64))),
        Dataset(28, 5, "Gas storage injection", FLOW, points=tuple(range(64, 80))),
        Dataset(28, 6, "Gas storage withdrawal", FLOW, points=tuple(range(64, 80))),
        Dataset(28, 7, "Gas storage level", "energy_storage", points=(0, 64, 65, 66, 70, 71)),
    )
}


def scope(province: int) -> tuple[tuple[int, Dataset], ...]:
    """Return configured areas and their catalog combinations."""
    return tuple(
        (point, item)
        for point in (0, province)
        for item in CATALOG.values()
        if point in item.points
    )
