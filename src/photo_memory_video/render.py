from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from .config_loader import PhotoConfig, ProjectConfig, VideoConfig
from .layout import LayoutSlot, Rect, layout_for_count
from .text_renderer import TextRenderer
from .timeline import ScenePage, build_scene_pages
from .transitions import blend_frames, clamp01, fade_to_color, smoothstep


FrameFunction = Callable[[float], np.ndarray]
ProgressCallback = Callable[[float, str], None]


@dataclass(frozen=True)
class RenderedPage:
    start: float
    duration: float
    overlap_with_previous: float
    renderer: "PageRenderer"


class PageRenderer:
    def __init__(self, page: ScenePage, video: VideoConfig, text_renderer: TextRenderer | None = None) -> None:
        self.page = page
        self.video = video
        self.canvas_size = video.resolution
        self.text_renderer = text_renderer or TextRenderer(video.font_path)
        self.photos = page.photos
        self.images = [ImageOps.exif_transpose(Image.open(photo.path)).convert("RGB") for photo in self.photos]
        self.photo_sizes = [image.size for image in self.images]
        self.slots = layout_for_count(len(self.photos), self.canvas_size, self.photo_sizes)
        self.background = self._make_background()

    def make_frame(self, t: float) -> np.ndarray:
        progress = clamp01(t / max(self.page.duration, 0.001))
        canvas = self.background.copy()
        for index, (photo, image, slot) in enumerate(zip(self.photos, self.images, self.slots)):
            tile = self._render_photo(image, slot, progress, index)
            canvas = self._paste_tile(canvas, tile, slot, rounded=len(self.photos) > 1 or slot.fit == "contain")

            compact = len(self.photos) > 1
            canvas = self.text_renderer.draw_photo_text(canvas, slot.rect, photo, compact=compact)

        title = self._page_title()
        canvas = self.text_renderer.draw_scene_heading(canvas, title, self.page.description)
        return np.asarray(canvas.convert("RGB"), dtype=np.uint8)

    def close(self) -> None:
        for image in self.images:
            image.close()

    def _page_title(self) -> str | None:
        if not self.page.title:
            return None
        if self.page.page_count <= 1:
            return self.page.title
        return f"{self.page.title}  {self.page.page_index + 1}/{self.page.page_count}"

    def _make_background(self) -> Image.Image:
        base = Image.new("RGB", self.canvas_size, self.video.background_color)
        if not self.images:
            return base

        cover = self._cover_crop(self.images[0], Rect(0, 0, *self.canvas_size), progress=0.5, drift=0.0)
        cover = cover.filter(ImageFilter.GaussianBlur(radius=max(18, int(min(self.canvas_size) * 0.045))))
        cover = ImageEnhance.Color(cover).enhance(0.72)
        cover = ImageEnhance.Brightness(cover).enhance(0.58)
        tint = Image.new("RGB", self.canvas_size, self.video.background_color)
        background = Image.blend(cover, tint, 0.36)
        return self._add_vignette(background)

    def _add_vignette(self, image: Image.Image) -> Image.Image:
        width, height = image.size
        y = np.linspace(-1.0, 1.0, height)[:, None]
        x = np.linspace(-1.0, 1.0, width)[None, :]
        distance = np.sqrt(x * x + y * y)
        alpha = np.clip((distance - 0.42) / 0.92, 0, 1) * 120
        overlay = np.zeros((height, width, 4), dtype=np.uint8)
        overlay[:, :, 3] = alpha.astype(np.uint8)
        vignette = Image.fromarray(overlay)
        return Image.alpha_composite(image.convert("RGBA"), vignette).convert("RGB")

    def _render_photo(self, image: Image.Image, slot: LayoutSlot, progress: float, index: int) -> Image.Image:
        drift = -1.0 if index % 2 else 1.0
        if slot.fit == "contain":
            return self._contain_fit(image, slot.rect, progress, drift)
        return self._cover_crop(image, slot.rect, progress, drift)

    def _cover_crop(self, image: Image.Image, rect: Rect, progress: float, drift: float) -> Image.Image:
        zoom = 1.035 + smoothstep(progress) * 0.055
        scale = max(rect.width / image.width, rect.height / image.height) * zoom
        resized_w = max(rect.width, int(math.ceil(image.width * scale)))
        resized_h = max(rect.height, int(math.ceil(image.height * scale)))
        resized = image.resize((resized_w, resized_h), Image.Resampling.LANCZOS)

        extra_x = max(0, resized_w - rect.width)
        extra_y = max(0, resized_h - rect.height)
        pan = (smoothstep(progress) - 0.5) * 0.28 * drift
        crop_x = int(extra_x * (0.5 + pan))
        crop_y = int(extra_y * (0.5 - pan * 0.45))
        crop_x = max(0, min(extra_x, crop_x))
        crop_y = max(0, min(extra_y, crop_y))
        return resized.crop((crop_x, crop_y, crop_x + rect.width, crop_y + rect.height))

    def _contain_fit(self, image: Image.Image, rect: Rect, progress: float, drift: float) -> Image.Image:
        zoom = 1.0 + smoothstep(progress) * 0.035
        scale = min(rect.width / image.width, rect.height / image.height) * zoom
        resized_w = int(math.ceil(image.width * scale))
        resized_h = int(math.ceil(image.height * scale))
        resized = image.resize((resized_w, resized_h), Image.Resampling.LANCZOS)
        tile = Image.new("RGB", (rect.width, rect.height), self.video.background_color)
        x = (rect.width - resized_w) // 2
        y = (rect.height - resized_h) // 2
        if x < 0 or y < 0:
            crop_x = max(0, -x)
            crop_y = max(0, -y)
            resized = resized.crop((crop_x, crop_y, crop_x + rect.width, crop_y + rect.height))
            x = max(0, x)
            y = max(0, y)
        tile.paste(resized, (x, y))
        return tile

    def _paste_tile(self, canvas: Image.Image, tile: Image.Image, slot: LayoutSlot, rounded: bool) -> Image.Image:
        rect = slot.rect
        base = canvas.convert("RGBA")
        tile_rgba = tile.convert("RGBA")

        mask = Image.new("L", (rect.width, rect.height), 255)
        if rounded:
            mask = Image.new("L", (rect.width, rect.height), 0)
            mask_draw = ImageOps.expand(mask, 0)
            ImageDraw.Draw(mask_draw).rounded_rectangle(
                (0, 0, rect.width, rect.height),
                radius=max(10, int(min(rect.width, rect.height) * 0.025)),
                fill=255,
            )
            mask = mask_draw

        if rounded:
            shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
            shadow_mask = mask.filter(ImageFilter.GaussianBlur(radius=12))
            shadow.paste((0, 0, 0, 95), (rect.x + 8, rect.y + 10), shadow_mask)
            base = Image.alpha_composite(base, shadow)

        base.paste(tile_rgba, (rect.x, rect.y), mask)
        return base.convert("RGB")


class ProjectRenderer:
    def __init__(self, config: ProjectConfig) -> None:
        self.config = config
        self.text_renderer = TextRenderer(config.video.font_path)
        self.pages = build_scene_pages(config)
        self.rendered_pages = self._build_rendered_pages()
        self.starts = [page.start for page in self.rendered_pages]
        self.duration = max((page.start + page.duration for page in self.rendered_pages), default=0.0)

    def make_frame(self, t: float) -> np.ndarray:
        if not self.rendered_pages:
            raise ValueError("No pages to render.")
        t = max(0.0, min(t, max(0.0, self.duration - 0.001)))
        index = max(0, bisect.bisect_right(self.starts, t) - 1)
        current = self.rendered_pages[index]
        local_t = t - current.start
        frame = current.renderer.make_frame(local_t)

        if index > 0 and current.overlap_with_previous > 0 and local_t < current.overlap_with_previous:
            previous = self.rendered_pages[index - 1]
            previous_frame = previous.renderer.make_frame(t - previous.start)
            frame = blend_frames(previous_frame, frame, local_t / current.overlap_with_previous)

        fade_duration = min(self.config.video.fade_duration, self.duration / 3) if self.duration else 0.0
        if fade_duration > 0 and t < fade_duration:
            black = tuple(max(0, channel - 16) for channel in self.config.video.background_color)
            frame = blend_frames(np.full_like(frame, black), frame, t / fade_duration)
        if fade_duration > 0 and self.duration - t < fade_duration:
            black = tuple(max(0, channel - 16) for channel in self.config.video.background_color)
            frame = fade_to_color(frame, black, 1 - (self.duration - t) / fade_duration)

        return frame

    def close(self) -> None:
        for page in self.rendered_pages:
            page.renderer.close()

    def _build_rendered_pages(self) -> list[RenderedPage]:
        rendered: list[RenderedPage] = []
        cursor = 0.0
        previous_duration = 0.0
        for index, page in enumerate(self.pages):
            overlap = 0.0
            if index > 0:
                overlap = min(self.config.video.transition_duration, previous_duration / 3, page.duration / 3)
                cursor -= overlap
            rendered.append(
                RenderedPage(
                    start=cursor,
                    duration=page.duration,
                    overlap_with_previous=overlap,
                    renderer=PageRenderer(page, self.config.video, self.text_renderer),
                )
            )
            cursor += page.duration
            previous_duration = page.duration
        return rendered


def render_video(config: ProjectConfig, output_path: str | Path, progress_callback: ProgressCallback | None = None) -> Path:
    try:
        VideoClip = _load_moviepy_video_clip()
    except ImportError as exc:
        raise RuntimeError("MoviePy is required to render video. Install dependencies with: python -m pip install -e .") from exc

    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if progress_callback:
        progress_callback(0.0, "准备渲染")
    renderer = ProjectRenderer(config)
    try:
        clip = _make_video_clip(VideoClip, renderer.make_frame, renderer.duration)
        try:
            clip.write_videofile(
                str(output),
                fps=config.video.fps,
                codec="libx264",
                audio=False,
                preset="medium",
                threads=4,
                logger=_make_progress_logger(progress_callback) if progress_callback else "bar",
            )
            if progress_callback:
                progress_callback(1.0, "渲染完成")
        finally:
            if hasattr(clip, "close"):
                clip.close()
    finally:
        renderer.close()
    return output


def render_preview_frame(config: ProjectConfig, output_path: str | Path, t: float = 0.0) -> Path:
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    renderer = ProjectRenderer(config)
    try:
        frame = renderer.make_frame(t)
        Image.fromarray(frame).save(output)
    finally:
        renderer.close()
    return output


def render_preview_page(
    config: ProjectConfig,
    output_path: str | Path,
    scene_index: int,
    page_index: int,
    progress: float = 0.35,
) -> Path:
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    renderer = ProjectRenderer(config)
    try:
        target = next(
            (
                rendered_page
                for rendered_page in renderer.rendered_pages
                if rendered_page.renderer.page.scene_index == scene_index
                and rendered_page.renderer.page.page_index == page_index
            ),
            None,
        )
        if target is None:
            raise ValueError(f"Preview page does not exist: scene {scene_index + 1}, page {page_index + 1}")
        local_t = clamp01(progress) * max(0.0, target.duration - 0.001)
        frame = target.renderer.make_frame(local_t)
        Image.fromarray(frame).save(output)
    finally:
        renderer.close()
    return output


def _load_moviepy_video_clip() -> type:
    try:
        from moviepy import VideoClip

        return VideoClip
    except ImportError:
        from moviepy.editor import VideoClip

        return VideoClip


def _make_video_clip(video_clip_type: type, make_frame: FrameFunction, duration: float):
    try:
        return video_clip_type(frame_function=make_frame, duration=duration)
    except TypeError:
        return video_clip_type(make_frame=make_frame, duration=duration)


def _make_progress_logger(progress_callback: ProgressCallback | None):
    from proglog import ProgressBarLogger

    class MoviePyProgressLogger(ProgressBarLogger):
        def __init__(self, callback: ProgressCallback | None) -> None:
            super().__init__()
            self.callback_fn = callback
            self.min_time_interval = 0.25

        def callback(self, **changes) -> None:  # type: ignore[override]
            message = changes.get("message")
            if self.callback_fn and isinstance(message, str) and message.strip():
                self.callback_fn(self._current_progress(), message.strip())

        def bars_callback(self, bar, attr, value, old_value=None) -> None:  # type: ignore[override]
            if not self.callback_fn or bar != "frame_index":
                return
            data = self.bars.get(bar, {})
            total = int(data.get("total") or 0)
            if total <= 0:
                self.callback_fn(0.0, "准备写入帧")
                return
            if attr == "index":
                done = max(0, min(int(value), total))
                progress = min(0.99, done / total)
                self.callback_fn(progress, f"渲染帧 {done}/{total}")
            elif attr == "total":
                self.callback_fn(0.0, f"准备渲染 {total} 帧")

        def _current_progress(self) -> float:
            data = self.bars.get("frame_index", {})
            total = int(data.get("total") or 0)
            index = int(data.get("index") or 0)
            if total <= 0:
                return 0.0
            return min(0.99, max(0.0, index / total))

    return MoviePyProgressLogger(progress_callback)
