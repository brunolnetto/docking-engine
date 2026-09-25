import math

import pytest

from moldock.domain import DomainValidationError
from moldock.repositories.metadata_codec import decode_metadata, encode_metadata


def test_metadata_codec_round_trips_nested_supported_types():
    value = {
        ("pose", 1): (
            frozenset({"b", "a"}),
            {"score": -8.4, "ok": True, "note": None},
        ),
        7: ("x", 2),
    }

    payload = encode_metadata(value)

    assert decode_metadata(payload) == value


def test_metadata_codec_is_deterministic_for_frozensets():
    left = encode_metadata(frozenset({"c", "a", "b"}))
    right = encode_metadata(frozenset({"b", "c", "a"}))

    assert left == right


@pytest.mark.parametrize("value", [object(), {1, 2}, b"bytes"])
def test_metadata_codec_rejects_unsupported_types(value):
    with pytest.raises(DomainValidationError, match="unsupported score metadata type"):
        encode_metadata(value)


@pytest.mark.parametrize(
    "payload",
    [
        '{"__moldock_type__":"unknown","items":[]}',
        '{"items":[]}',
    ],
)
def test_metadata_codec_rejects_unknown_persisted_tags(payload):
    with pytest.raises(DomainValidationError, match="invalid persisted score metadata"):
        decode_metadata(payload)


def test_metadata_codec_decodes_plain_json_lists_as_tuples():
    assert decode_metadata('[1,["x",2]]') == (1, ("x", 2))


def test_metadata_codec_rejects_non_finite_numbers():
    with pytest.raises(ValueError):
        encode_metadata(math.nan)
