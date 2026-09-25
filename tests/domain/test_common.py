from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType

import pytest

from moldock.domain import DomainValidationError
from moldock.domain.common import canonical_json, content_id


class ExampleStatus(str, Enum):
    READY = "ready"


@dataclass(frozen=True)
class ExamplePayload:
    status: ExampleStatus
    created_at: datetime


def test_content_id_is_stable_across_mapping_order():
    left = content_id("exp", {"a": 1, "b": 2})
    right = content_id("exp", {"b": 2, "a": 1})

    assert left == right


def test_content_id_changes_when_payload_changes():
    assert content_id("exp", {"x": 1}) != content_id("exp", {"x": 2})


def test_content_id_supports_deeply_frozen_collections():
    frozen = MappingProxyType(
        {
            "nested": MappingProxyType({"flags": frozenset({"b", "a"})}),
            "values": (1, 2, 3),
        }
    )

    assert content_id("exp", frozen) == content_id(
        "exp",
        {
            "nested": {"flags": {"a", "b"}},
            "values": [1, 2, 3],
        },
    )


def test_canonical_json_serializes_dataclasses_enums_and_datetimes():
    created_at = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)

    encoded = canonical_json(
        ExamplePayload(status=ExampleStatus.READY, created_at=created_at)
    )

    assert encoded == '{"created_at":"2026-09-25T12:00:00+00:00","status":"ready"}'


@pytest.mark.parametrize("prefix", ["", " "])
def test_content_id_rejects_blank_prefix(prefix):
    with pytest.raises(DomainValidationError):
        content_id(prefix, {"x": 1})
