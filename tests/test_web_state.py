from __future__ import annotations

from pathlib import Path

from PIL import Image

from photo_memory_video.config_loader import load_config
from photo_memory_video.web_state import preview_time_for_config, project_to_editor_state, scene_pages_state, state_to_config_data


def test_project_state_round_trip_keeps_scene_photos(tmp_path: Path) -> None:
    photo = tmp_path / "photos" / "001.jpg"
    photo.parent.mkdir(parents=True)
    Image.new("RGB", (120, 80), (90, 100, 110)).save(photo)
    config_path = tmp_path / "demo.yaml"
    config_path.write_text(
        """
video:
  title: "大学回忆"
  resolution: [640, 360]
  fps: 12
scenes:
  - title: "大一"
    description: "刚开始"
    duration: 3
    photos:
      - path: "photos/001.jpg"
        time: "2022.09"
        caption: "第一次班会"
        description: "那时候大家都还不熟。"
""",
        encoding="utf-8",
    )

    state = project_to_editor_state(load_config(config_path), tmp_path / "output" / "demo.mp4")
    state["scenes"][0]["photos"][0]["caption"] = "第一次社团活动"

    data = state_to_config_data(state)

    assert data["video"]["title"] == "大学回忆"
    assert data["video"]["resolution"] == [640, 360]
    assert data["scenes"][0]["title"] == "大一"
    assert data["scenes"][0]["photos"][0]["path"] == "photos/001.jpg"
    assert data["scenes"][0]["photos"][0]["caption"] == "第一次社团活动"


def test_preview_time_skips_initial_fade(tmp_path: Path) -> None:
    photo = tmp_path / "photos" / "001.jpg"
    photo.parent.mkdir(parents=True)
    Image.new("RGB", (120, 80), (90, 100, 110)).save(photo)
    config_path = tmp_path / "demo.yaml"
    config_path.write_text(
        """
video:
  fade_duration: 0.6
scenes:
  - duration: 3
    photos:
      - path: "photos/001.jpg"
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert abs(preview_time_for_config(config, 0) - 0.85) < 1e-9
    assert preview_time_for_config(config, 1.25) == 1.25


def test_scene_pages_state_reports_auto_pages(tmp_path: Path) -> None:
    for index in range(5):
        photo = tmp_path / "photos" / f"{index + 1:03}.jpg"
        photo.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (120, 80), (80 + index, 90, 100)).save(photo)
    config_path = tmp_path / "demo.yaml"
    config_path.write_text(
        """
scenes:
  - title: "分页"
    duration: 5
    photos:
      - path: "photos/001.jpg"
      - path: "photos/002.jpg"
      - path: "photos/003.jpg"
      - path: "photos/004.jpg"
      - path: "photos/005.jpg"
""",
        encoding="utf-8",
    )

    pages = scene_pages_state(load_config(config_path))

    assert [page["photoCount"] for page in pages] == [3, 2]
    assert pages[0]["pageCount"] == 2
    assert pages[1]["pageIndex"] == 1
