import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from weather_risk.domain.models import Region
from weather_risk.infrastructure.persistence import HubDataError, JsonHubRepository

WriteHubs = Callable[[Any], Path]
HubRecord = Callable[..., dict[str, Any]]


class TestSeedData:
    def test_loads_all_initial_hubs(self, seed_hubs_file: Path) -> None:
        repository = JsonHubRepository(seed_hubs_file)

        assert [hub.name for hub in repository.list_all()] == [
            "Chicago",
            "Dallas",
            "Denver",
            "Houston",
            "Miami",
            "Minneapolis",
        ]

    def test_get_by_id(self, seed_hubs_file: Path) -> None:
        hub = JsonHubRepository(seed_hubs_file).get_by_id("miami")

        assert hub is not None
        assert hub.state == "FL"
        assert hub.region is Region.SOUTH
        assert hub.location.latitude == pytest.approx(25.7617)

    def test_get_by_id_returns_none_for_unknown_hub(self, seed_hubs_file: Path) -> None:
        assert JsonHubRepository(seed_hubs_file).get_by_id("atlantis") is None

    @pytest.mark.parametrize(
        ("region", "expected_ids"),
        [
            (Region.SOUTH, ["dallas", "houston", "miami"]),
            (Region.MIDWEST, ["chicago", "minneapolis"]),
            (Region.WEST, ["denver"]),
            (Region.NORTHEAST, []),
        ],
    )
    def test_list_by_region(
        self, seed_hubs_file: Path, region: Region, expected_ids: list[str]
    ) -> None:
        hubs = JsonHubRepository(seed_hubs_file).list_by_region(region)

        assert [hub.id for hub in hubs] == expected_ids


class TestInvalidData:
    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(HubDataError, match="not found"):
            JsonHubRepository(tmp_path / "missing.json")

    def test_invalid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "hubs.json"
        path.write_text("{not json", encoding="utf-8")

        with pytest.raises(HubDataError, match="not valid JSON"):
            JsonHubRepository(path)

    @pytest.mark.parametrize("payload", [[], {}, {"hubs": {}}])
    def test_wrong_top_level_shape(self, write_hubs_file: WriteHubs, payload: Any) -> None:
        with pytest.raises(HubDataError, match="'hubs' list"):
            JsonHubRepository(write_hubs_file(payload))

    def test_missing_field(self, write_hubs_file: WriteHubs, hub_record: HubRecord) -> None:
        record = hub_record()
        del record["state"]

        with pytest.raises(HubDataError, match="#0"):
            JsonHubRepository(write_hubs_file({"hubs": [record]}))

    @pytest.mark.parametrize(
        "overrides",
        [
            {"region": "atlantis"},
            {"location": {"latitude": 123, "longitude": 0}},
            {"id": "Not A Slug"},
        ],
    )
    def test_domain_validation_failure(
        self, write_hubs_file: WriteHubs, hub_record: HubRecord, overrides: dict[str, Any]
    ) -> None:
        with pytest.raises(HubDataError, match="invalid"):
            JsonHubRepository(write_hubs_file({"hubs": [hub_record(**overrides)]}))

    def test_duplicate_ids(self, write_hubs_file: WriteHubs, hub_record: HubRecord) -> None:
        payload = {"hubs": [hub_record(), hub_record(name="Dallas Again")]}

        with pytest.raises(HubDataError, match="Duplicate hub id 'dallas'"):
            JsonHubRepository(write_hubs_file(payload))

    def test_empty_hub_list_is_allowed(self, write_hubs_file: WriteHubs) -> None:
        assert JsonHubRepository(write_hubs_file({"hubs": []})).list_all() == []


def rewrite(write_hubs_file: WriteHubs, payload: Any) -> None:
    """Rewrite the hubs file and move its mtime forward, as a real edit would."""
    path = write_hubs_file(payload)
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))


class TestReloadOnChange:
    def test_added_hub_is_served_without_a_new_repository(
        self, write_hubs_file: WriteHubs, hub_record: HubRecord
    ) -> None:
        repository = JsonHubRepository(write_hubs_file({"hubs": [hub_record()]}))
        assert repository.get_by_id("atlanta") is None

        atlanta = hub_record(id="atlanta", name="Atlanta", state="GA")
        rewrite(write_hubs_file, {"hubs": [hub_record(), atlanta]})

        assert [hub.id for hub in repository.list_all()] == ["atlanta", "dallas"]
        assert repository.get_by_id("atlanta") is not None
        assert len(repository.list_by_region(Region.SOUTH)) == 2

    def test_edited_and_removed_hubs_are_reflected(
        self, write_hubs_file: WriteHubs, hub_record: HubRecord
    ) -> None:
        repository = JsonHubRepository(write_hubs_file({"hubs": [hub_record()]}))

        rewrite(write_hubs_file, {"hubs": [hub_record(name="Dallas-Fort Worth")]})
        hub = repository.get_by_id("dallas")
        assert hub is not None
        assert hub.name == "Dallas-Fort Worth"

        rewrite(write_hubs_file, {"hubs": []})
        assert repository.list_all() == []

    def test_unchanged_file_is_not_reparsed(
        self, write_hubs_file: WriteHubs, hub_record: HubRecord, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repository = JsonHubRepository(write_hubs_file({"hubs": [hub_record()]}))
        loads: list[None] = []
        original = repository._load
        monkeypatch.setattr(repository, "_load", lambda: loads.append(None) or original())

        repository.list_all()
        repository.get_by_id("dallas")

        assert loads == []

    def test_file_that_becomes_invalid_raises(
        self, write_hubs_file: WriteHubs, hub_record: HubRecord
    ) -> None:
        repository = JsonHubRepository(write_hubs_file({"hubs": [hub_record()]}))

        rewrite(write_hubs_file, {"hubs": [hub_record(), hub_record()]})

        with pytest.raises(HubDataError, match="Duplicate hub id 'dallas'"):
            repository.list_all()

    def test_file_that_is_deleted_raises(
        self, write_hubs_file: WriteHubs, hub_record: HubRecord
    ) -> None:
        path = write_hubs_file({"hubs": [hub_record()]})
        repository = JsonHubRepository(path)

        path.unlink()

        with pytest.raises(HubDataError, match="not found"):
            repository.get_by_id("dallas")
