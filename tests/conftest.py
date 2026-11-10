"""Documented JSON-LD utilization records with synthetic test measurements."""

import pytest


@pytest.fixture
def record():
    def make(
        point=0,
        type_id=2,
        activity=1,
        classification=2,
        granularity=5,
        start="2026-10-25T02:00:00+02:00",
        end="2026-10-25T02:00:00+01:00",
    ):
        return {
            "@type": "Utilization",
            "point": f"/v1/points/{point}",
            "type": f"/v1/types/{type_id}",
            "activity": f"/v1/activities/{activity}",
            "classification": f"/v1/classifications/{classification}",
            "granularity": f"/v1/granularities/{granularity}",
            "validfrom": start,
            "validto": end,
            "capacity": 438626,
            "percentage": 0.059684,
        }

    return make
