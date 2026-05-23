from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from photo_memory_video.config_loader import ConfigError, load_config


def _image(path: Path, size: tuple[int, int] = (120, 80)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (120, 90, 70)).save(path)


def test_loads_yaml_and_resolves_relative_photo_paths(tmp_path: Path) -> None:
    _image(tmp_path / "photos" / "001.jpg")
    config_path = tmp_path / "demo.yaml"
    config_path.write_text(
        """
video:
  title: "大学回忆"
  resolution: [640, 360]
  fps: 12
scenes:
  - title: "大一"
    duration: 3
    photos:
      - path: "photos/001.jpg"
        caption: "第一次班会"
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.video.title == "大学回忆"
    assert config.video.resolution == (640, 360)
    assert config.video.fps == 12
    assert config.scenes[0].photos[0].path == (tmp_path / "photos" / "001.jpg").resolve()
    assert config.scenes[0].photos[0].caption == "第一次班会"


def test_expands_photo_directory(tmp_path: Path) -> None:
    _image(tmp_path / "photos" / "b.jpg")
    _image(tmp_path / "photos" / "a.png")
    (tmp_path / "photos" / "note.txt").write_text("skip", encoding="utf-8")
    config_path = tmp_path / "demo.yaml"
    config_path.write_text(
        """
scenes:
  - duration: 4
    photos:
      - path: "photos"
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert [photo.path.name for photo in config.scenes[0].photos] == ["a.png", "b.jpg"]


def test_rejects_missing_photo(tmp_path: Path) -> None:
    config_path = tmp_path / "bad.yaml"
    config_path.write_text(
        """
scenes:
  - duration: 4
    photos:
      - path: "missing.jpg"
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError):
        load_config(config_path)
