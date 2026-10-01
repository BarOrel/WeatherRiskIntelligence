"""Deterministic cache key construction.

Values are converted to a canonical, JSON-serializable form (type-tagged where needed so that
e.g. ``"2024-01-01"`` and ``date(2024, 1, 1)`` differ), then hashed with SHA-256. Unsupported
types raise ``TypeError`` instead of falling back to ``repr()``/``hash()``, which can be unstable.
"""

import dataclasses
import datetime as dt
import hashlib
import json
import uuid
from collections.abc import Mapping
from decimal import Decimal
from enum import Enum
from typing import Any

from weather_risk.domain.models import GeoLocation, WeatherDateRange


def canonicalize(value: Any) -> Any:
    # Order matters: Enum before str/int (StrEnum/IntEnum), bool before int,
    # datetime before date.
    if isinstance(value, Enum):
        return ["enum", _qualified_name(type(value)), canonicalize(value.value)]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value + 0.0  # folds -0.0 into 0.0
    if isinstance(value, dt.datetime):
        return ["datetime", value.isoformat()]
    if isinstance(value, dt.date):
        return ["date", value.isoformat()]
    if isinstance(value, dt.time):
        return ["time", value.isoformat()]
    if isinstance(value, Decimal):
        return ["decimal", str(value)]
    if isinstance(value, uuid.UUID):
        return ["uuid", str(value)]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return [
            "dataclass",
            _qualified_name(type(value)),
            {f.name: canonicalize(getattr(value, f.name)) for f in dataclasses.fields(value)},
        ]
    if isinstance(value, tuple):
        return ["tuple", [canonicalize(item) for item in value]]
    if isinstance(value, list):
        return ["list", [canonicalize(item) for item in value]]
    if isinstance(value, Mapping):
        pairs = [[canonicalize(k), canonicalize(v)] for k, v in value.items()]
        return ["dict", sorted(pairs, key=lambda pair: _dumps(pair[0]))]
    if isinstance(value, (set, frozenset)):
        return ["set", sorted((canonicalize(item) for item in value), key=_dumps)]
    raise TypeError(
        f"Cannot build a deterministic cache key from {type(value).__qualname__}; "
        "pass a custom key_builder"
    )


def digest(value: Any) -> str:
    """SHA-256 of the canonical form of ``value``."""
    return hashlib.sha256(_dumps(canonicalize(value)).encode("utf-8")).hexdigest()


def join_key_parts(parts: Mapping[str, object]) -> str:
    """Readable key segment ``a=1&b=2``. Sorted by name, so adding a part later is safe."""
    for name, part in parts.items():
        if set("&=") & set(f"{name}{part}"):
            raise ValueError(f"Key part {name!r} contains a reserved character ('&' or '=')")
    return "&".join(f"{name}={parts[name]}" for name in sorted(parts))


def location_range_key(location: GeoLocation, date_range: WeatherDateRange) -> str:
    """Readable key for the common "data at a point over a date range" request."""
    return join_key_parts(
        {
            # "+ 0.0" folds -0.0 into 0.0 so equal coordinates give equal keys.
            "lat": f"{location.latitude + 0.0:.6f}",
            "lon": f"{location.longitude + 0.0:.6f}",
            "start": date_range.start.isoformat(),
            "end": date_range.end.isoformat(),
        }
    )


def _dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _qualified_name(cls: type) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"
