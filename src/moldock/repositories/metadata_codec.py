from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from moldock.domain import DomainValidationError


_TAG = "__moldock_type__"
_ITEMS = "items"


def encode_metadata(value: Any) -> str:
    return json.dumps(
        _encode(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def decode_metadata(payload: str) -> Any:
    return _decode(json.loads(payload))


def _encode(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            _TAG: "mapping",
            _ITEMS: [
                [_encode(key), _encode(item)]
                for key, item in value.items()
            ],
        }
    if isinstance(value, tuple):
        return {
            _TAG: "tuple",
            _ITEMS: [_encode(item) for item in value],
        }
    if isinstance(value, frozenset):
        encoded_items = [_encode(item) for item in value]
        encoded_items.sort(
            key=lambda item: json.dumps(
                item,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
        )
        return {
            _TAG: "frozenset",
            _ITEMS: encoded_items,
        }
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise DomainValidationError(
        f"unsupported score metadata type: {type(value).__name__}"
    )


def _decode(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_decode(item) for item in value)
    if not isinstance(value, dict):
        return value

    kind = value.get(_TAG)
    if kind == "mapping":
        return {
            _decode(key): _decode(item)
            for key, item in value[_ITEMS]
        }
    if kind == "tuple":
        return tuple(_decode(item) for item in value[_ITEMS])
    if kind == "frozenset":
        return frozenset(_decode(item) for item in value[_ITEMS])
    raise DomainValidationError(
        "invalid persisted score metadata encoding"
    )
