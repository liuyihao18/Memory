from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from .config_loader import PhotoConfig, ProjectConfig, VideoConfig
from .layout import LayoutSlot, Rect, layout_for_count, photo_wall_layout, photo_wall_reference_size
from .photo_card import card_label_font_size, photo_card_metrics
from .text_renderer import TextRenderer
from .timeline import ScenePage, build_scene_pages
from .transitions import blend_frames, clamp01, fade_to_color, smoothstep


FrameFunction = Callable[[float], np.ndarray]
ProgressCallback = Callable[[float, str], None]
SCENE_ZOOM_AMOUNT = 0.025
PHOTO_CARD_SUPERSAMPLE = 2
TILE_SHADOW_ALPHA = 70
PHOTO_CARD_SHADOW_ALPHA = 84


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
        self.output_size = video.resolution
        self.canvas_size = photo_wall_reference_size(video.resolution) if page.layout == "photo_wall" else video.resolution
        self.text_renderer = text_renderer or TextRenderer(video.font_path)
        self.photos = page.photos
        self.images = [ImageOps.exif_transpose(Image.open(photo.path)).convert("RGB") for photo in self.photos]
        self.photo_sizes = [image.size for image in self.images]
        self.slots = self._build_slots()
        self.background = self._make_background()
        self._photo_layer: Image.Image | None = None
        self._heading_layer: Image.Image | None = None

    def make_frame(self, t: float) -> np.ndarray:
        progress = clamp01(t / max(self.page.duration, 0.001))
        photo_layer = self._cached_photo_layer()
        canvas = self._apply_scene_zoom(photo_layer, progress) if self.video.scene_zoom else photo_layer
        canvas = Image.alpha_composite(canvas.convert("RGBA"), self._cached_heading_layer()).convert("RGB")
        if canvas.size != self.output_size:
            canvas = canvas.resize(self.output_size, Image.Resampling.LANCZOS)
        return np.asarray(canvas, dtype=np.uint8)

    def _cached_photo_layer(self) -> Image.Image:
        if self._photo_layer is None:
            self._photo_layer = self._render_photo_layer()
        return self._photo_layer

    def _cached_heading_layer(self) -> Image.Image:
        if self._heading_layer is None:
            self._heading_layer = self._render_heading_layer()
        return self._heading_layer

    def _render_photo_layer(self) -> Image.Image:
        canvas = self.background.copy()
        draw_items = sorted(zip(self.photos, self.images, self.slots), key=lambda item: item[2].z_index)
        for photo, image, slot in draw_items:
            if slot.frame in {"print", "clean"}:
                canvas = self._paste_photo_card(canvas, image, slot, photo)
                continue

            tile = self._render_photo(image, slot)
            canvas = self._paste_tile(canvas, tile, slot, rounded=len(self.photos) > 1 or slot.fit == "contain")

            compact = len(self.photos) > 1
            canvas = self.text_renderer.draw_photo_text(canvas, slot.rect, photo, compact=compact)
        return canvas

    def _render_heading_layer(self) -> Image.Image:
        layer = Image.new("RGBA", self.canvas_size, (0, 0, 0, 0))
        title = self._page_title()
        return self.text_renderer.draw_scene_heading(layer, title, self.page.description).convert("RGBA")

    def close(self) -> None:
        for image in self.images:
            image.close()

    def _build_slots(self) -> list[LayoutSlot]:
        if self.page.layout == "photo_wall":
            return photo_wall_layout(
                len(self.photos),
                self.canvas_size,
                self.photo_sizes,
                transforms=[photo.transform for photo in self.photos],
                rotation_limit=self.page.wall.rotation,
                overlap=self.page.wall.overlap,
                style=self.page.wall.style,
                card_width=self.page.wall.card_width,
                spread=self.page.wall.spread,
                caption_safe=self.page.wall.caption_safe,
                randomness=self.page.wall.randomness,
                random_seed=self.page.wall.random_seed,
            )
        return layout_for_count(len(self.photos), self.canvas_size, self.photo_sizes)

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

        cover = self._cover_crop(self.images[0], Rect(0, 0, *self.canvas_size))
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

    def _render_photo(self, image: Image.Image, slot: LayoutSlot) -> Image.Image:
        if slot.fit == "contain":
            return self._contain_fit(image, slot.rect)
        return self._cover_crop(image, slot.rect)

    def _cover_crop(self, image: Image.Image, rect: Rect) -> Image.Image:
        scale = max(rect.width / image.width, rect.height / image.height)
        resized_w = max(rect.width, int(math.ceil(image.width * scale)))
        resized_h = max(rect.height, int(math.ceil(image.height * scale)))
        resized = image.resize((resized_w, resized_h), Image.Resampling.LANCZOS)

        extra_x = max(0, resized_w - rect.width)
        extra_y = max(0, resized_h - rect.height)
        crop_x = extra_x // 2
        crop_y = extra_y // 2
        crop_x = max(0, min(extra_x, crop_x))
        crop_y = max(0, min(extra_y, crop_y))
        return resized.crop((crop_x, crop_y, crop_x + rect.width, crop_y + rect.height))

    def _contain_fit(
        self,
        image: Image.Image,
        rect: Rect,
        background_color: tuple[int, int, int] | None = None,
    ) -> Image.Image:
        scale = min(rect.width / image.width, rect.height / image.height)
        resized_w = int(math.ceil(image.width * scale))
        resized_h = int(math.ceil(image.height * scale))
        resized = image.resize((resized_w, resized_h), Image.Resampling.LANCZOS)
        tile = Image.new("RGB", (rect.width, rect.height), background_color or self.video.background_color)
        if resized_w > rect.width:
            crop_x = max(0, (resized_w - rect.width) // 2)
            resized = resized.crop((crop_x, 0, crop_x + rect.width, resized_h))
        if resized_h > rect.height:
            crop_y = max(0, (resized.height - rect.height) // 2)
            resized = resized.crop((0, crop_y, resized.width, crop_y + rect.height))
        x = max(0, (rect.width - resized.width) // 2)
        y = max(0, (rect.height - resized.height) // 2)
        tile.paste(resized, (x, y))
        return tile

    def _apply_scene_zoom(self, image: Image.Image, progress: float) -> Image.Image:
        zoom = 1.0 + smoothstep(progress) * SCENE_ZOOM_AMOUNT
        if zoom <= 1.0001:
            return image
        width, height = image.size
        source_w = width / zoom
        source_h = height / zoom
        left = (width - source_w) / 2
        top = (height - source_h) / 2
        return image.resize(
            image.size,
            Image.Resampling.LANCZOS,
            box=(left, top, left + source_w, top + source_h),
        )

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
            shadow_mask = mask.filter(ImageFilter.GaussianBlur(radius=max(12, int(min(rect.width, rect.height) * 0.035))))
            shadow.paste((0, 0, 0, TILE_SHADOW_ALPHA), (rect.x + 7, rect.y + 9), shadow_mask)
            base = Image.alpha_composite(base, shadow)

        base.paste(tile_rgba, (rect.x, rect.y), mask)
        return base.convert("RGB")

    def _paste_photo_card(
        self,
        canvas: Image.Image,
        image: Image.Image,
        slot: LayoutSlot,
        photo: PhotoConfig,
    ) -> Image.Image:
        sample = PHOTO_CARD_SUPERSAMPLE
        rect = slot.rect
        scaled_slot = LayoutSlot(
            rect=Rect(0, 0, rect.width * sample, rect.height * sample),
            fit=slot.fit,
            rotation=slot.rotation,
            z_index=slot.z_index,
            frame=slot.frame,
        )
        card = self._render_photo_card(image, scaled_slot, photo, render_scale=sample)
        rotated = card.rotate(slot.rotation, resample=Image.Resampling.BICUBIC, expand=True)
        rotated = rotated.resize(
            (max(1, int(round(rotated.width / sample))), max(1, int(round(rotated.height / sample)))),
            Image.Resampling.LANCZOS,
        )
        rect = slot.rect
        x = rect.x + rect.width // 2 - rotated.width // 2
        y = rect.y + rect.height // 2 - rotated.height // 2

        base = canvas.convert("RGBA")
        alpha = rotated.getchannel("A")
        shadow = Image.new("RGBA", rotated.size, (0, 0, 0, PHOTO_CARD_SHADOW_ALPHA))
        shadow.putalpha(alpha.filter(ImageFilter.GaussianBlur(radius=max(14, int(min(rect.width, rect.height) * 0.045)))))
        base.paste(shadow, (x + 8, y + 12), shadow)
        base.paste(rotated, (x, y), rotated)
        return base.convert("RGB")

    def _render_photo_card(
        self,
        image: Image.Image,
        slot: LayoutSlot,
        photo: PhotoConfig,
        render_scale: int = 1,
    ) -> Image.Image:
        rect = slot.rect
        card = Image.new("RGBA", (rect.width, rect.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(card)
        radius = max(8, int(min(rect.width, rect.height) * 0.022))
        fill = (246, 240, 229, 255) if slot.frame == "print" else (250, 247, 240, 244)
        outline = (255, 255, 255, 180) if slot.frame == "clean" else (226, 215, 198, 255)
        draw.rounded_rectangle(
            (0, 0, rect.width - 1, rect.height - 1),
            radius=radius,
            fill=fill,
            outline=outline,
            width=max(1, 2 * render_scale),
        )

        has_label = bool(photo.caption or photo.time)
        metrics = photo_card_metrics(rect, slot.frame, has_label, render_scale)
        photo_rect = Rect(0, 0, metrics.photo_rect.width, metrics.photo_rect.height)
        tile = (
            self._contain_fit(image, photo_rect, background_color=(236, 230, 218))
            if slot.fit == "contain"
            else self._cover_crop(image, photo_rect)
        )
        tile = tile.convert("RGBA")

        photo_mask = Image.new("L", (metrics.photo_rect.width, metrics.photo_rect.height), 0)
        ImageDraw.Draw(photo_mask).rounded_rectangle(
            (0, 0, metrics.photo_rect.width, metrics.photo_rect.height),
            radius=max(6, int(min(metrics.photo_rect.width, metrics.photo_rect.height) * 0.018)),
            fill=255,
        )
        card.paste(tile, (metrics.photo_rect.x, metrics.photo_rect.y), photo_mask)

        if metrics.label_rect:
            self._draw_card_label(card, photo, metrics.label_rect, metrics.label_font_size, slot.frame)
        return card

    def _draw_card_label(
        self,
        card: Image.Image,
        photo: PhotoConfig,
        rect: Rect,
        font_size: int,
        frame: str,
    ) -> None:
        draw = ImageDraw.Draw(card)
        text = " · ".join(part for part in (photo.time, photo.caption) if part)
        if not text:
            return
        font = self.text_renderer.font(font_size, bold=bool(photo.caption))
        fill = (58, 48, 38, 245) if frame == "print" else (255, 247, 235, 245)
        if frame == "clean":
            radius = max(4, int(min(rect.width, rect.height) * 0.18))
            draw.rounded_rectangle((rect.x, rect.y, rect.right - 1, rect.bottom - 1), radius=radius, fill=(0, 0, 0, 118))
            text_x = rect.x + max(6, int(rect.height * 0.25))
            max_width = max(1, rect.width - (text_x - rect.x) * 2)
        else:
            text_x = rect.x
            max_width = rect.width
        text = self._ellipsize(text, font, max_width, draw)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_h = bbox[3] - bbox[1]
        draw.text((text_x, rect.y + max(0, (rect.height - text_h) // 2 - 1)), text, font=font, fill=fill)

    def _ellipsize(self, text: str, font, max_width: int, draw: ImageDraw.ImageDraw) -> str:
        if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
            return text
        suffix = "..."
        current = text
        while current:
            candidate = current.rstrip() + suffix
            if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
                return candidate
            current = current[:-1]
        return suffix


def _card_label_font_size(height: int, render_scale: int = 1) -> int:
    return card_label_font_size(height, render_scale)


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
    target_page = next(
        (
            page
            for page in build_scene_pages(config)
            if page.scene_index == scene_index and page.page_index == page_index
        ),
        None,
    )
    if target_page is None:
        raise ValueError(f"Preview page does not exist: scene {scene_index + 1}, page {page_index + 1}")
    renderer = PageRenderer(target_page, config.video)
    try:
        local_t = clamp01(progress) * max(0.0, target_page.duration - 0.001)
        frame = renderer.make_frame(local_t)
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
