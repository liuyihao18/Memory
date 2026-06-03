from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from photo_memory_video.config_loader import ConfigError, load_config


def _image(path: Path, size: tuple[int, int] = (120, 80)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (120, 90, 70)).save(path)


def _file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"test")


def test_loads_yaml_and_resolves_relative_photo_paths(tmp_path: Path) -> None:
    _image(tmp_path / "photos" / "001.jpg")
    config_path = tmp_path / "demo.yaml"
    config_path.write_text(
        """
video:
  title: "大学回忆"
  resolution: [640, 360]
  fps: 12
  scene_zoom: false
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
    assert config.video.scene_zoom is False
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
      card_width: 0.36
      spread: 1.2
      caption_safe: false
      randomness: 0.7
      random_seed: 12345
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
    assert scene.wall.card_width == 0.36
    assert scene.wall.spread == 1.2
    assert scene.wall.caption_safe is False
    assert scene.wall.randomness == 0.7
    assert scene.wall.random_seed == 12345
    assert photo.transform is not None
    assert photo.transform.x == 0.42
    assert photo.transform.rotation == -5
    assert photo.transform.fit == "contain"


def test_loads_global_audio_config(tmp_path: Path) -> None:
    _image(tmp_path / "photos" / "001.jpg")
    _file(tmp_path / "music" / "bgm.mp3")
    config_path = tmp_path / "audio.yaml"
    config_path.write_text(
        """
video:
  audio:
    path: "music/bgm.mp3"
    volume: 0.42
    fade_in: 1.2
    fade_out: 2.4
    loop: false
scenes:
  - duration: 4
    photos:
      - path: "photos/001.jpg"
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.video.audio.path == (tmp_path / "music" / "bgm.mp3").resolve()
    assert config.video.audio.volume == 0.42
    assert config.video.audio.fade_in == 1.2
    assert config.video.audio.fade_out == 2.4
    assert config.video.audio.loop is False


@pytest.mark.parametrize(
    ("audio_yaml", "extra_file"),
    [
        ('path: "music/missing.mp3"', None),
        ('path: "music/bgm.txt"', "music/bgm.txt"),
        ('path: "music/bgm.mp3"\n    volume: 2.5', "music/bgm.mp3"),
    ],
)
def test_rejects_invalid_audio_config(tmp_path: Path, audio_yaml: str, extra_file: str | None) -> None:
    _image(tmp_path / "photos" / "001.jpg")
    if extra_file:
        _file(tmp_path / extra_file)
    config_path = tmp_path / "bad_audio.yaml"
    config_path.write_text(
        f"""
video:
  audio:
    {audio_yaml}
scenes:
  - duration: 4
    photos:
      - path: "photos/001.jpg"
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError):
        load_config(config_path)


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
