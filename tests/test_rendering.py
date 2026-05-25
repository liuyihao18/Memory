from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops

from photo_memory_video.config_loader import PhotoConfig, load_config
from photo_memory_video.layout import Rect
from photo_memory_video.render import PHOTO_CARD_SUPERSAMPLE, ProjectRenderer, _card_label_font_size, render_preview_page
from photo_memory_video.text_renderer import TextRenderer


def _image(path: Path, size: tuple[int, int], color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)


def _gradient_image(path: Path, size: tuple[int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", size)
    width, height = size
    for y in range(height):
        for x in range(width):
            image.putpixel((x, y), ((x * 255) // width, (y * 255) // height, ((x + y) * 255) // (width + height)))
    image.save(path)


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


def test_photo_wall_preview_renders_rotated_cards(tmp_path: Path) -> None:
    for index in range(5):
        _image(tmp_path / "photos" / f"{index + 1:03}.jpg", (140 + index * 10, 100), (60 + index * 20, 100, 120))
    config_path = tmp_path / "wall.yaml"
    config_path.write_text(
        """
video:
  resolution: [320, 180]
  fps: 2
scenes:
  - title: "照片墙"
    layout: photo_wall
    wall:
      max_per_page: 5
      rotation: 8
    duration: 2
    photos:
      - path: "photos/001.jpg"
        caption: "第一张"
      - path: "photos/002.jpg"
      - path: "photos/003.jpg"
      - path: "photos/004.jpg"
      - path: "photos/005.jpg"
""",
        encoding="utf-8",
    )
    config = load_config(config_path)
    output = tmp_path / "wall_preview.png"

    render_preview_page(config, output, scene_index=0, page_index=0)

    assert output.exists()
    assert Image.open(output).size == (320, 180)


def test_contain_fit_keeps_background_when_zoom_crops_one_axis(tmp_path: Path) -> None:
    _image(tmp_path / "photos" / "001.jpg", (100, 200), (200, 80, 60))
    config_path = tmp_path / "demo.yaml"
    config_path.write_text(
        """
video:
  resolution: [320, 180]
scenes:
  - duration: 1
    photos:
      - path: "photos/001.jpg"
""",
        encoding="utf-8",
    )
    renderer = ProjectRenderer(load_config(config_path))
    try:
        page_renderer = renderer.rendered_pages[0].renderer
        tile = page_renderer._contain_fit(Image.new("RGB", (100, 200), (200, 80, 60)), Rect(0, 0, 300, 200), background_color=(236, 230, 218))
    finally:
        renderer.close()

    assert tile.getpixel((0, 100)) == (236, 230, 218)
    assert tile.getpixel((299, 100)) == (236, 230, 218)


def test_photo_fit_uses_static_center_crop(tmp_path: Path) -> None:
    photo_path = tmp_path / "photos" / "001.jpg"
    _gradient_image(photo_path, (140, 100))
    config_path = tmp_path / "demo.yaml"
    config_path.write_text(
        """
video:
  resolution: [320, 180]
scenes:
  - duration: 1
    photos:
      - path: "photos/001.jpg"
""",
        encoding="utf-8",
    )
    renderer = ProjectRenderer(load_config(config_path))
    try:
        page_renderer = renderer.rendered_pages[0].renderer
        with Image.open(photo_path) as source:
            image = source.convert("RGB")
        cover = page_renderer._cover_crop(image, Rect(0, 0, 120, 80))
        contain = page_renderer._contain_fit(image, Rect(0, 0, 120, 120))
    finally:
        renderer.close()

    assert cover.size == (120, 80)
    assert contain.size == (120, 120)
    assert cover.getpixel((60, 40)) == image.resize((120, 86), Image.Resampling.LANCZOS).getpixel((60, 43))


def test_page_renderer_applies_scene_level_zoom(tmp_path: Path) -> None:
    _gradient_image(tmp_path / "photos" / "001.jpg", (320, 180))
    config_path = tmp_path / "demo.yaml"
    config_path.write_text(
        """
video:
  resolution: [320, 180]
  fade_duration: 0
  transition_duration: 0
scenes:
  - duration: 2
    photos:
      - path: "photos/001.jpg"
""",
        encoding="utf-8",
    )
    renderer = ProjectRenderer(load_config(config_path))
    try:
        first = Image.fromarray(renderer.make_frame(0.0))
        late = Image.fromarray(renderer.make_frame(1.8))
    finally:
        renderer.close()

    assert ImageChops.difference(first, late).getbbox() is not None


def test_scene_zoom_can_be_disabled(tmp_path: Path) -> None:
    _gradient_image(tmp_path / "photos" / "001.jpg", (320, 180))
    config_path = tmp_path / "demo.yaml"
    config_path.write_text(
        """
video:
  resolution: [320, 180]
  fade_duration: 0
  transition_duration: 0
  scene_zoom: false
scenes:
  - duration: 2
    photos:
      - path: "photos/001.jpg"
""",
        encoding="utf-8",
    )
    renderer = ProjectRenderer(load_config(config_path))
    try:
        first = Image.fromarray(renderer.make_frame(0.0))
        late = Image.fromarray(renderer.make_frame(1.8))
    finally:
        renderer.close()

    assert ImageChops.difference(first, late).getbbox() is None


def test_page_renderer_lazily_caches_static_layers(tmp_path: Path) -> None:
    _gradient_image(tmp_path / "photos" / "001.jpg", (320, 180))
    config_path = tmp_path / "demo.yaml"
    config_path.write_text(
        """
video:
  resolution: [320, 180]
  scene_zoom: false
scenes:
  - title: "cache"
    duration: 2
    photos:
      - path: "photos/001.jpg"
""",
        encoding="utf-8",
    )
    renderer = ProjectRenderer(load_config(config_path))
    try:
        page_renderer = renderer.rendered_pages[0].renderer
        assert page_renderer._photo_layer is None
        assert page_renderer._heading_layer is None
        renderer.make_frame(0.0)
        assert page_renderer._photo_layer is not None
        assert page_renderer._heading_layer is not None
        photo_layer = page_renderer._photo_layer
        heading_layer = page_renderer._heading_layer
        renderer.make_frame(1.0)
        assert page_renderer._photo_layer is photo_layer
        assert page_renderer._heading_layer is heading_layer
    finally:
        renderer.close()


def test_card_label_font_size_scales_with_supersampling() -> None:
    assert _card_label_font_size(60, 1) == 25
    assert _card_label_font_size(60 * PHOTO_CARD_SUPERSAMPLE, PHOTO_CARD_SUPERSAMPLE) == 50
    assert _card_label_font_size(200, PHOTO_CARD_SUPERSAMPLE) == 56
