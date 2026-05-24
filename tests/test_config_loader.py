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


def test_loads_photo_wall_layout_and_transform(tmp_path: Path) -> None:
    _image(tmp_path / "photos" / "001.jpg")
    config_path = tmp_path / "wall.yaml"
    config_path.write_text(
        """
scenes:
  - title: "照片墙"
    layout: photo_wall
    wall:
      max_per_page: 6
      rotation: 8
      overlap: 0.18
    photos:
      - path: "photos/001.jpg"
        caption: "第一张"
        transform:
          x: 0.42
          y: 0.58
          width: 0.34
          rotation: -5
          fit: contain
""",
        encoding="utf-8",
    )

    config = load_config(config_path)
    scene = config.scenes[0]
    photo = scene.photos[0]

    assert scene.layout == "photo_wall"
    assert scene.wall.max_per_page == 6
    assert scene.wall.rotation == 8
    assert photo.transform is not None
    assert photo.transform.x == 0.42
    assert photo.transform.rotation == -5
    assert photo.transform.fit == "contain"


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
