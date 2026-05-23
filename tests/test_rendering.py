from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops

from photo_memory_video.config_loader import PhotoConfig, load_config
from photo_memory_video.layout import Rect
from photo_memory_video.render import ProjectRenderer, render_preview_page
from photo_memory_video.text_renderer import TextRenderer


def _image(path: Path, size: tuple[int, int], color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)


def test_text_renderer_draws_chinese_caption(tmp_path: Path) -> None:
    base = Image.new("RGB", (640, 360), (24, 22, 20))
    before = base.copy()
    photo = PhotoConfig(path=tmp_path / "unused.jpg", caption="第一次参加社团活动", time="2022.11")

    rendered = TextRenderer().draw_photo_text(base, Rect(0, 0, 640, 360), photo, compact=False)

    assert ImageChops.difference(before, rendered).getbbox() is not None


def test_project_renderer_makes_rgb_frame(tmp_path: Path) -> None:
    _image(tmp_path / "photos" / "001.jpg", (320, 220), (120, 90, 70))
    _image(tmp_path / "photos" / "002.jpg", (220, 320), (70, 100, 120))
    config_path = tmp_path / "demo.yaml"
    config_path.write_text(
        """
video:
  resolution: [320, 180]
  fps: 2
  transition_duration: 0.2
  fade_duration: 0.1
scenes:
  - title: "大一"
    duration: 1
    photos:
      - path: "photos/001.jpg"
        caption: "第一张"
      - path: "photos/002.jpg"
        caption: "第二张"
""",
        encoding="utf-8",
    )
    config = load_config(config_path)
    renderer = ProjectRenderer(config)
    try:
        frame = renderer.make_frame(0.5)
    finally:
        renderer.close()

    assert frame.shape == (180, 320, 3)
    assert frame.dtype.name == "uint8"


def test_render_preview_page_targets_auto_paginated_page(tmp_path: Path) -> None:
    for index in range(5):
        _image(tmp_path / "photos" / f"{index + 1:03}.jpg", (120, 80), (50 + index * 20, 90, 110))
    config_path = tmp_path / "demo.yaml"
    config_path.write_text(
        """
video:
  resolution: [320, 180]
  fps: 2
scenes:
  - title: "分页场景"
    duration: 4
    photos:
      - path: "photos/001.jpg"
      - path: "photos/002.jpg"
      - path: "photos/003.jpg"
      - path: "photos/004.jpg"
      - path: "photos/005.jpg"
""",
        encoding="utf-8",
    )
    config = load_config(config_path)
    output = tmp_path / "preview_page_2.png"

    render_preview_page(config, output, scene_index=0, page_index=1)

    assert output.exists()
    assert Image.open(output).size == (320, 180)
