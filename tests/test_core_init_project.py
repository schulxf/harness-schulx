from pathlib import Path

from harness_core.defaults import DEFAULT_HUB_CONFIG
from harness_core.init_project import initialize_harness_project
from harness_core.paths import config_path, harness_root
from harness_core.storage import read_json


def test_initialize_harness_project_creates_layout_and_config(tmp_path: Path) -> None:
    sensors = initialize_harness_project(
        tmp_path,
        name="Projeto Teste",
        sensors=["python -m pytest"],
        force=False,
        runner_version="test-version",
    )

    assert sensors == ["python -m pytest"]
    hroot = harness_root(tmp_path)
    assert (hroot / "tasks").is_dir()
    assert (hroot / "dashboard" / "hub").is_dir()
    assert (hroot / "inbox" / "telegram" / "media").is_dir()
    config = read_json(config_path(tmp_path), {})
    assert config["project_name"] == "Projeto Teste"
    assert config["runner_version"] == "test-version"
    assert config["default_sensors"] == ["python -m pytest"]
    assert config["hub"] == DEFAULT_HUB_CONFIG
    assert read_json(hroot / "tasks" / "index.json", []) == []


def test_initialize_harness_project_preserves_existing_config_without_force(tmp_path: Path) -> None:
    initialize_harness_project(
        tmp_path,
        name="Primeiro",
        sensors=[],
        force=False,
        runner_version="v1",
    )
    initialize_harness_project(
        tmp_path,
        name="Segundo",
        sensors=[],
        force=False,
        runner_version="v2",
    )

    assert read_json(config_path(tmp_path), {})["project_name"] == "Primeiro"


def test_initialize_harness_project_rewrites_config_with_force(tmp_path: Path) -> None:
    initialize_harness_project(
        tmp_path,
        name="Primeiro",
        sensors=[],
        force=False,
        runner_version="v1",
    )
    initialize_harness_project(
        tmp_path,
        name="Segundo",
        sensors=[],
        force=True,
        runner_version="v2",
    )

    config = read_json(config_path(tmp_path), {})
    assert config["project_name"] == "Segundo"
    assert config["runner_version"] == "v2"
