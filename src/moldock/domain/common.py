from __future__ import annotations

from collections.abc import Mapping, Set
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
import hashlib
import json
from types import MappingProxyType
from typing import Any


class DomainValidationError(ValueError):
    pass


def deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: deep_freeze(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(deep_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(deep_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(deep_freeze(item) for item in value)
    return value


def _canonicalize(value: Any) -> Any:
    if is_dataclass(value):
        return _canonicalize(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {
            str(key): _canonicalize(item)
            for key, item in sorted(value.items(), key=lambda kv: str(kv[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    if isinstance(value, Set) and not isinstance(value, (str, bytes, bytearray)):
        return sorted(_canonicalize(item) for item in value)
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        _canonicalize(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def content_id(prefix: str, value: Any) -> str:
    if not prefix or not prefix.strip():
        raise DomainValidationError("prefix must not be blank")

    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:24]}"
