import json
import threading
from pathlib import Path
from typing import Any

from weather_risk.domain.errors import DomainValidationError
from weather_risk.domain.models import GeoLocation, Hub, Region
from weather_risk.domain.repositories import HubRepository


class HubDataError(Exception):
    """Raised when the hubs file is missing or malformed."""


class JsonHubRepository(HubRepository):
    """Read-only hub repository backed by a JSON file.

    The JSON file is the source of truth: every read checks the file and reloads
    it when it has changed, so added or edited hubs are served without a restart.
    The file is validated at construction (fail fast) and on every reload; a file
    that becomes invalid raises ``HubDataError`` instead of serving stale hubs.
    """

    def __init__(self, file_path: Path) -> None:
        self._file_path = file_path
        self._lock = threading.Lock()
        self._version: tuple[int, int] | None = None
        self._hubs: dict[str, Hub] = {}
        self._current()

    def list_all(self) -> list[Hub]:
        return sorted(self._current().values(), key=lambda hub: hub.id)

    def get_by_id(self, hub_id: str) -> Hub | None:
        return self._current().get(hub_id)

    def list_by_region(self, region: Region) -> list[Hub]:
        return [hub for hub in self.list_all() if hub.region is region]

    def _current(self) -> dict[str, Hub]:
        with self._lock:
            version = self._file_version()
            if version != self._version:
                self._hubs = self._load()
                self._version = version
            return self._hubs

    def _file_version(self) -> tuple[int, int]:
        try:
            stat = self._file_path.stat()
        except FileNotFoundError as exc:
            raise HubDataError(f"Hubs file not found: {self._file_path}") from exc
        return stat.st_mtime_ns, stat.st_size

    def _load(self) -> dict[str, Hub]:
        try:
            raw = json.loads(self._file_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise HubDataError(f"Hubs file not found: {self._file_path}") from exc
        except json.JSONDecodeError as exc:
            raise HubDataError(f"Hubs file is not valid JSON: {self._file_path}") from exc

        if not isinstance(raw, dict) or not isinstance(raw.get("hubs"), list):
            raise HubDataError("Hubs file must be an object with a 'hubs' list")

        hubs: dict[str, Hub] = {}
        for index, record in enumerate(raw["hubs"]):
            hub = self._to_domain(record, index)
            if hub.id in hubs:
                raise HubDataError(f"Duplicate hub id '{hub.id}'")
            hubs[hub.id] = hub
        return hubs

    @staticmethod
    def _to_domain(record: Any, index: int) -> Hub:
        try:
            location = record["location"]
            return Hub(
                id=record["id"],
                name=record["name"],
                state=record["state"],
                region=Region.parse(record["region"]),
                location=GeoLocation(
                    latitude=location["latitude"],
                    longitude=location["longitude"],
                ),
            )
        except (KeyError, TypeError, AttributeError) as exc:
            raise HubDataError(f"Hub record #{index} is missing or has invalid fields") from exc
        except DomainValidationError as exc:
            raise HubDataError(f"Hub record #{index} is invalid: {exc}") from exc
