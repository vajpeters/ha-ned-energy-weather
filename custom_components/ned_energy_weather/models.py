"""Normalize NED records and serialize response values in UTC."""

import math
from dataclasses import dataclass
from datetime import UTC, datetime

from .const import UNITS


def timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Timestamp requires an offset")
    return parsed.astimezone(UTC)


def identifier(value: int | str) -> int:
    return int(value.rsplit("/", 1)[-1]) if isinstance(value, str) else int(value)


@dataclass(frozen=True)
class Record:
    type_id: int
    point_id: int
    activity_id: int
    classification: int
    granularity: int
    valid_from: datetime
    valid_to: datetime
    last_update: datetime | None
    values: tuple[float | None, ...]

    @classmethod
    def parse(cls, row: dict) -> "Record":
        values = []
        for key in UNITS:
            value = row.get("emissionfactor" if key == "emission_factor" else key)
            if value is not None:
                value = float(value) * (100 if key == "percentage" else 1)
                if not math.isfinite(value):
                    raise ValueError("Non-finite measurement")
            values.append(value)
        start = timestamp(row["validfrom"])
        end = timestamp(row["validto"])
        if end <= start:
            raise ValueError("Invalid interval")
        return cls(
            *(
                identifier(row[key])
                for key in ("type", "point", "activity", "classification", "granularity")
            ),
            start,
            end,
            timestamp(row["lastupdate"]) if row.get("lastupdate") else None,
            tuple(values),
        )

    def as_response(self) -> dict:
        return {
            "valid_from": self.valid_from.isoformat(),
            "valid_to": self.valid_to.isoformat(),
            "last_update": self.last_update.isoformat() if self.last_update else None,
            **dict(zip(UNITS, self.values, strict=True)),
        }
