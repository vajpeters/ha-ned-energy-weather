"""Contract tests for JSON-LD decoding, request errors and DST."""

import asyncio
import json
from datetime import date
from unittest.mock import Mock

import pytest

from custom_components.ned_energy_weather.api import (
    AuthError,
    NedClient,
    RateLimitError,
    ResponseError,
    TimeoutError,
)
from custom_components.ned_energy_weather.models import Record

QUERY = {
    "points": (0,),
    "types": (2,),
    "activity": 1,
    "classification": 2,
    "granularity": 5,
    "start": date(2026, 10, 25),
    "end": date(2026, 10, 26),
}


class Response:
    def __init__(self, payload, status=200, headers=None):
        self.payload = payload
        self.status = status
        self.headers = headers or {}
        self.content = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def iter_chunked(self, _):
        yield json.dumps(self.payload).encode()


async def test_pagination_and_dst(record):
    second = record(start="2026-10-25T02:00:00+01:00", end="2026-10-25T03:00:00+01:00")
    session = Mock()
    session.get.side_effect = [
        Response(
            {
                "hydra:member": [record()],
                "hydra:view": {
                    "hydra:next": "/v1/utilizations?page=2",
                },
            }
        ),
        Response({"member": [second]}),
    ]
    rows = await NedClient(session, "test-token").fetch(**QUERY)
    assert [row.valid_from.hour for row in rows] == [0, 1]
    assert rows[0].as_response()["volume"] is None
    assert rows[0].as_response()["percentage"] == pytest.approx(5.9684)
    assert session.get.call_args_list[0].kwargs["allow_redirects"] is False
    assert session.get.call_args_list[0].kwargs["headers"]["X-AUTH-TOKEN"] == "test-token"
    assert session.get.call_args_list[1].args[0].query["page"] == "2"


async def test_empty_and_amsterdam_day(record):
    session = Mock()
    session.get.return_value = Response({"member": []})
    client = NedClient(session, "test-token")
    assert await client.fetch(**{**QUERY, "granularity": 6}) == ()
    assert dict(session.get.call_args.kwargs["params"])["granularitytimezone"] == "1"
    row = Record.parse(
        record(granularity=6, start="2026-10-25T00:00:00+02:00", end="2026-10-26T00:00:00+01:00")
    )
    assert (row.valid_to - row.valid_from).total_seconds() == 25 * 3600


@pytest.mark.parametrize(
    ("status", "error"), [(401, AuthError), (403, AuthError), (429, RateLimitError)]
)
async def test_errors(status, error):
    session = Mock()
    session.get.return_value = Response({}, status, {"Retry-After": "60"})
    with pytest.raises(error, match="NED") as exc:
        await NedClient(session, "test-token").fetch(**QUERY)
    assert "test-token" not in str(exc.value)


async def test_retry_after_temporary_failure(record, monkeypatch):
    session = Mock()
    session.get.side_effect = [
        Response({}, 429, {"Retry-After": "1"}),
        Response({"member": [record()]}),
    ]
    rows = await NedClient(session, "test-token").fetch(**QUERY)
    assert len(rows) == 1
    assert session.get.call_count == 2


async def test_timeout_retry(monkeypatch):
    async def no_wait(_):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_wait)
    session = Mock()
    session.get.side_effect = asyncio.TimeoutError
    with pytest.raises(TimeoutError):
        await NedClient(session, "test-token").fetch(**QUERY)
    assert session.get.call_count == 3


async def test_refuses_cross_origin_pagination():
    session = Mock()
    session.get.return_value = Response({"member": [], "view": {"next": "https://other.invalid/"}})
    with pytest.raises(ResponseError, match="pagination"):
        await NedClient(session, "test-token").fetch(**QUERY)
    assert session.get.call_count == 1


async def test_collection_filters_and_numeric_strings(record):
    session = Mock()
    sample = {**record(point=7), "capacity": "438626", "volume": "73104"}
    session.get.return_value = Response({"hydra:member": [sample], "hydra:totalItems": 1})
    rows = await NedClient(session, "test-token").fetch(
        **{**QUERY, "points": (0, 7), "types": (1, 2)}
    )
    params = session.get.call_args.kwargs["params"]
    assert [value for key, value in params if key == "point[]"] == ["0", "7"]
    assert [value for key, value in params if key == "type[]"] == ["1", "2"]
    assert dict(params)["itemsPerPage"] == "200"
    assert rows[0].as_response()["capacity"] == 438626
    assert rows[0].as_response()["volume"] == 73104
