import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from weather_risk.infrastructure.config.settings import PROJECT_ROOT


@pytest.fixture
def seed_hubs_file() -> Path:
    return PROJECT_ROOT / "data" / "hubs.json"


@pytest.fixture
def write_hubs_file(tmp_path: Path) -> Callable[[Any], Path]:
    def _write(payload: Any) -> Path:
        path = tmp_path / "hubs.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    return _write


@pytest.fixture
def hub_record() -> Callable[..., dict[str, Any]]:
    """Factory for a raw JSON hub record, with field overrides."""

    def _record(**overrides: Any) -> dict[str, Any]:
        record = {
            "id": "dallas",
            "name": "Dallas",
            "state": "TX",
            "region": "south",
            "location": {"latitude": 32.7767, "longitude": -96.7970},
        }
        record.update(overrides)
        return record

    return _record


@pytest.fixture(autouse=True)
def _conversations_in_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never write to the real data/weather_risk.db; SQLite tests use tmp files."""
    monkeypatch.setenv("WRI_CONVERSATION__STORE", "memory")
