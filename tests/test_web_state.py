from __future__ import annotations

from pathlib import Path

from PIL import Image

from photo_memory_video.config_loader import load_config
from photo_memory_video.web import WebWorkspace
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
  scene_zoom: false
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
    assert data["video"]["scene_zoom"] is False
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


def test_web_state_round_trip_keeps_photo_wall_controls(tmp_path: Path) -> None:
    photo = tmp_path / "photos" / "001.jpg"
    photo.parent.mkdir(parents=True)
    Image.new("RGB", (120, 80), (90, 100, 110)).save(photo)
    config_path = tmp_path / "wall.yaml"
    config_path.write_text(
        """
scenes:
  - title: "照片墙"
    layout: photo_wall
    wall:
      max_per_page: 6
      rotation: 7
      overlap: 0.2
      card_width: 0.31
      spread: 1.25
      caption_safe: false
      randomness: 0.6
      random_seed: 5678
    duration: 3
    photos:
      - path: "photos/001.jpg"
        transform:
          width: 0.32
          rotation: -4
""",
        encoding="utf-8",
    )

    state = project_to_editor_state(load_config(config_path))
    state["scenes"][0]["photos"][0]["transform"]["rotation"] = 3
    data = state_to_config_data(state)

    assert data["scenes"][0]["layout"] == "photo_wall"
    assert data["scenes"][0]["wall"]["max_per_page"] == 6
    assert data["scenes"][0]["wall"]["card_width"] == 0.31
    assert data["scenes"][0]["wall"]["spread"] == 1.25
    assert data["scenes"][0]["wall"]["caption_safe"] is False
    assert data["scenes"][0]["wall"]["randomness"] == 0.6
    assert data["scenes"][0]["wall"]["random_seed"] == 5678
    assert data["scenes"][0]["photos"][0]["transform"]["width"] == 0.32
    assert data["scenes"][0]["photos"][0]["transform"]["rotation"] == 3


def test_web_workspace_can_materialize_photo_wall_auto_transforms(tmp_path: Path) -> None:
    for index in range(3):
        photo = tmp_path / "photos" / f"{index + 1:03}.jpg"
        photo.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (120 + index * 30, 90), (90, 100 + index, 110)).save(photo)
    config_path = tmp_path / "wall.yaml"
    config_path.write_text(
        """
video:
  resolution: [640, 360]
scenes:
  - title: "照片墙"
    layout: photo_wall
    wall:
      max_per_page: 6
      rotation: 7
      card_width: 0.28
    duration: 3
    photos:
      - path: "photos/001.jpg"
        transform:
          x: 0.12
          y: 0.12
          width: 0.42
          height: 0.3
          rotation: 17
          fit: cover
          z_index: 9
      - path: "photos/002.jpg"
      - path: "photos/003.jpg"
""",
        encoding="utf-8",
    )
    workspace = WebWorkspace(config_path, tmp_path / "output.mp4")
    state = project_to_editor_state(load_config(config_path))

    result = workspace.auto_photo_wall_transforms(state, scene_index=0, page_index=0)

    assert [item["photoIndex"] for item in result["transforms"]] == [0, 1, 2]
    assert result["transforms"][0]["transform"]["width"] == 0.42
    assert result["transforms"][0]["transform"]["height"] == 0.3
    assert result["transforms"][0]["transform"]["fit"] == "cover"
    assert result["transforms"][1]["transform"]["width"] == 0.28
    assert all(0 < item["transform"]["width"] < 1 for item in result["transforms"])
    assert result["transforms"][1]["transform"]["fit"] == "contain"
    assert result["transforms"][0]["transform"]["x"] != 0.12
    assert result["transforms"][0]["transform"]["rotation"] != 17
    assert result["transforms"][0]["transform"]["z_index"] == 0


def test_web_workspace_page_elements_return_auto_photo_wall_geometry(tmp_path: Path) -> None:
    for index in range(2):
        photo = tmp_path / "photos" / f"{index + 1:03}.jpg"
        photo.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (140 + index * 20, 100), (90, 110, 120)).save(photo)
    config_path = tmp_path / "wall.yaml"
    config_path.write_text(
        """
video:
  resolution: [640, 360]
scenes:
  - layout: photo_wall
    duration: 3
    photos:
      - path: "photos/001.jpg"
        caption: "first"
      - path: "photos/002.jpg"
        time: "2020"
""",
        encoding="utf-8",
    )
    workspace = WebWorkspace(config_path, tmp_path / "output.mp4")
    state = project_to_editor_state(load_config(config_path))

    result = workspace.photo_wall_page_elements(state, scene_index=0, page_index=0)

    assert result["editable"] is True
    assert result["canvas"] == {"width": 640, "height": 360}
    assert result["wall"]["spread"] == 1.0
    assert result["wall"]["caption_safe"] is True
    assert result["wall"]["randomness"] == 0.0
    assert result["wall"]["random_seed"] is None
    assert [item["photoIndex"] for item in result["photos"]] == [0, 1]
    assert result["photos"][0]["caption"] == "first"
    assert result["photos"][1]["time"] == "2020"
    assert result["photos"][0]["mediaUrl"].startswith("/media?path=")
    assert all(0 < item["x"] < 1 and 0 < item["y"] < 1 for item in result["photos"])
    assert all(0 < item["width"] < 1 and 0 < item["height"] < 1 for item in result["photos"])
    assert all(item["fit"] == "contain" for item in result["photos"])
    card = result["photos"][0]["card"]
    assert card["label"] is not None
    assert card["photo"]["height"] < 0.86
    assert 0.04 < card["labelFontSize"] < 0.09


def test_web_workspace_page_elements_apply_existing_transform(tmp_path: Path) -> None:
    photo = tmp_path / "photos" / "001.jpg"
    photo.parent.mkdir(parents=True)
    Image.new("RGB", (120, 90), (90, 100, 110)).save(photo)
    config_path = tmp_path / "wall.yaml"
    config_path.write_text(
        """
video:
  resolution: [640, 360]
scenes:
  - layout: photo_wall
    duration: 3
    photos:
      - path: "photos/001.jpg"
        transform:
          x: 0.22
          y: 0.33
          width: 0.25
          rotation: 11
          fit: cover
          z_index: 7
""",
        encoding="utf-8",
    )
    workspace = WebWorkspace(config_path, tmp_path / "output.mp4")
    state = project_to_editor_state(load_config(config_path))

    result = workspace.photo_wall_page_elements(state, scene_index=0, page_index=0)
    item = result["photos"][0]

    assert abs(item["x"] - 0.22) < 0.01
    assert abs(item["y"] - 0.33) < 0.01
    assert item["width"] == 0.25
    assert item["rotation"] == 11
    assert item["fit"] == "cover"
    assert item["z_index"] == 7


def test_web_workspace_page_elements_card_metrics_are_resolution_stable(tmp_path: Path) -> None:
    for index in range(2):
        photo = tmp_path / "photos" / f"{index + 1:03}.jpg"
        photo.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (120 + index * 20, 180), (90, 100, 110)).save(photo)
    config_path = tmp_path / "wall.yaml"
    config_path.write_text(
        """
video:
  resolution: [1280, 720]
scenes:
  - layout: photo_wall
    duration: 3
    photos:
      - path: "photos/001.jpg"
        caption: "first"
      - path: "photos/002.jpg"
        caption: "second"
""",
        encoding="utf-8",
    )
    workspace = WebWorkspace(config_path, tmp_path / "output.mp4")
    state = project_to_editor_state(load_config(config_path))

    low = workspace.photo_wall_page_elements(state, scene_index=0, page_index=0)["photos"][0]["card"]
    state["video"]["resolution"] = [1920, 1080]
    high = workspace.photo_wall_page_elements(state, scene_index=0, page_index=0)["photos"][0]["card"]

    assert low == high


def test_web_workspace_page_elements_reject_non_photo_wall(tmp_path: Path) -> None:
    photo = tmp_path / "photos" / "001.jpg"
    photo.parent.mkdir(parents=True)
    Image.new("RGB", (120, 90), (90, 100, 110)).save(photo)
    config_path = tmp_path / "grid.yaml"
    config_path.write_text(
        """
video:
  resolution: [640, 360]
scenes:
  - layout: grid
    duration: 3
    photos:
      - path: "photos/001.jpg"
""",
        encoding="utf-8",
    )
    workspace = WebWorkspace(config_path, tmp_path / "output.mp4")
    state = project_to_editor_state(load_config(config_path))

    result = workspace.photo_wall_page_elements(state, scene_index=0, page_index=0)

    assert result["editable"] is False
    assert result["photos"] == []
    assert "reason" in result
