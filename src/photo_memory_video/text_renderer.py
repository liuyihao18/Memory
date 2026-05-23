from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont

from .config_loader import PhotoConfig
from .layout import Rect


@dataclass(frozen=True)
class TextLine:
    text: str
    font: ImageFont.ImageFont
    fill: tuple[int, int, int, int]
    stroke_width: int


class TextRenderer:
    def __init__(self, font_path: Path | None = None) -> None:
        self.font_path = font_path

    def draw_scene_heading(self, image: Image.Image, title: str | None, description: str | None) -> Image.Image:
        if not title and not description:
            return image

        width, height = image.size
        margin = max(32, int(min(width, height) * 0.06))
        max_width = min(int(width * 0.62), width - margin * 2)
        title_size = max(30, int(height * 0.056))
        body_size = max(19, int(height * 0.026))
        parts: list[tuple[str, ImageFont.ImageFont, tuple[int, int, int, int], int]] = []
        if title:
            parts.append((title, self.font(title_size, bold=True), (255, 246, 230, 255), 2))
        if description:
            parts.append((description, self.font(body_size), (244, 226, 202, 245), 1))

        lines = self._fit_lines(parts, max_width=max_width, max_height=int(height * 0.24), min_size=15)
        return self._draw_panel(
            image,
            lines,
            x=margin,
            y=margin,
            max_width=max_width,
            anchor="top-left",
            background=(16, 14, 12, 112),
        )

    def draw_photo_text(self, image: Image.Image, rect: Rect, photo: PhotoConfig, compact: bool) -> Image.Image:
        if not photo.caption and not photo.time and not photo.description:
            return image

        canvas_w, canvas_h = image.size
        base = max(18, int(canvas_h * (0.033 if compact else 0.04)))
        small = max(15, int(base * 0.68))
        max_width = min(int(rect.width * 0.82), canvas_w - 64)
        max_height = int(rect.height * (0.36 if compact else 0.42))

        parts: list[tuple[str, ImageFont.ImageFont, tuple[int, int, int, int], int]] = []
        if photo.time:
            parts.append((photo.time, self.font(small), (232, 205, 174, 242), 1))
        if photo.caption:
            parts.append((photo.caption, self.font(base, bold=True), (255, 248, 236, 255), 2))
        if photo.description and not compact:
            parts.append((photo.description, self.font(small), (244, 228, 209, 242), 1))

        lines = self._fit_lines(parts, max_width=max_width, max_height=max_height, min_size=13)
        if not lines:
            return image

        inset = max(18, int(min(rect.width, rect.height) * 0.055))
        panel_w, panel_h = self._panel_size(lines)
        x = max(rect.x + inset, min(rect.right - inset - panel_w, rect.x + inset))
        y = rect.bottom - inset - panel_h
        if rect.height > canvas_h * 0.85:
            y = min(y, canvas_h - max(34, int(canvas_h * 0.07)) - panel_h)
        y = max(rect.y + inset, y)

        return self._draw_panel(
            image,
            lines,
            x=x,
            y=y,
            max_width=max_width,
            anchor="top-left",
            background=(18, 15, 12, 132),
        )

    def font(self, size: int, bold: bool = False) -> ImageFont.ImageFont:
        candidates = list(self._font_candidates(bold))
        for candidate in candidates:
            if candidate.exists():
                try:
                    return ImageFont.truetype(str(candidate), size=size)
                except OSError:
                    continue
        return ImageFont.load_default()

    def _font_candidates(self, bold: bool) -> Iterable[Path]:
        if self.font_path:
            yield self.font_path

        windows = Path("C:/Windows/Fonts")
        names = [
            "msyhbd.ttc" if bold else "msyh.ttc",
            "simhei.ttf",
            "Dengb.ttf" if bold else "Deng.ttf",
            "simsun.ttc",
            "NotoSansCJK-Regular.ttc",
            "NotoSansSC-Regular.otf",
        ]
        for name in names:
            yield windows / name

    def _fit_lines(
        self,
        parts: list[tuple[str, ImageFont.ImageFont, tuple[int, int, int, int], int]],
        max_width: int,
        max_height: int,
        min_size: int,
    ) -> list[TextLine]:
        current_parts = parts
        for _ in range(8):
            lines = self._wrap_parts(current_parts, max_width=max_width)
            _, height = self._panel_size(lines)
            if height <= max_height or self._smallest_font_size(current_parts) <= min_size:
                return self._trim_to_height(lines, max_height)
            current_parts = [
                (text, self.font(max(min_size, int(self._font_size(font) * 0.9)), bold=stroke > 1), fill, stroke)
                for text, font, fill, stroke in current_parts
            ]
        return self._trim_to_height(self._wrap_parts(current_parts, max_width=max_width), max_height)

    def _wrap_parts(
        self,
        parts: list[tuple[str, ImageFont.ImageFont, tuple[int, int, int, int], int]],
        max_width: int,
    ) -> list[TextLine]:
        scratch = Image.new("RGB", (16, 16))
        draw = ImageDraw.Draw(scratch)
        lines: list[TextLine] = []
        for text, font, fill, stroke in parts:
            for wrapped in self._wrap_text(text, font, max_width, draw):
                lines.append(TextLine(wrapped, font, fill, stroke))
        return lines

    def _wrap_text(self, text: str, font: ImageFont.ImageFont, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
        wrapped: list[str] = []
        for paragraph in str(text).splitlines() or [""]:
            line = ""
            for char in paragraph:
                candidate = line + char
                if self._text_width(draw, candidate, font) <= max_width or not line:
                    line = candidate
                else:
                    wrapped.append(line.rstrip())
                    line = char.lstrip()
            if line:
                wrapped.append(line.rstrip())
        return wrapped

    def _draw_panel(
        self,
        image: Image.Image,
        lines: list[TextLine],
        x: int,
        y: int,
        max_width: int,
        anchor: str,
        background: tuple[int, int, int, int],
    ) -> Image.Image:
        if not lines:
            return image

        panel_w, panel_h = self._panel_size(lines)
        if anchor == "bottom-left":
            y -= panel_h
        panel_w = min(panel_w, max_width + self._padding() * 2)

        base = image.convert("RGBA")
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        radius = max(8, int(min(image.size) * 0.012))
        draw.rounded_rectangle((x, y, x + panel_w, y + panel_h), radius=radius, fill=background)

        cursor_y = y + self._padding()
        for line in lines:
            draw.text(
                (x + self._padding(), cursor_y),
                line.text,
                font=line.font,
                fill=line.fill,
                stroke_width=line.stroke_width,
                stroke_fill=(0, 0, 0, 150),
            )
            cursor_y += self._line_height(line.font) + self._line_gap()

        return Image.alpha_composite(base, overlay).convert("RGB")

    def _trim_to_height(self, lines: list[TextLine], max_height: int) -> list[TextLine]:
        result: list[TextLine] = []
        for line in lines:
            candidate = result + [line]
            _, height = self._panel_size(candidate)
            if height > max_height and result:
                return result
            result = candidate
        return result

    def _panel_size(self, lines: list[TextLine]) -> tuple[int, int]:
        if not lines:
            return (0, 0)
        scratch = Image.new("RGB", (16, 16))
        draw = ImageDraw.Draw(scratch)
        width = max(self._text_width(draw, line.text, line.font) for line in lines)
        height = sum(self._line_height(line.font) for line in lines) + self._line_gap() * (len(lines) - 1)
        return (width + self._padding() * 2, height + self._padding() * 2)

    def _text_width(self, draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
        bbox = draw.textbbox((0, 0), text, font=font, stroke_width=1)
        return bbox[2] - bbox[0]

    def _line_height(self, font: ImageFont.ImageFont) -> int:
        bbox = font.getbbox("春Ag")
        return bbox[3] - bbox[1] + 4

    def _font_size(self, font: ImageFont.ImageFont) -> int:
        return int(getattr(font, "size", 18))

    def _smallest_font_size(self, parts: list[tuple[str, ImageFont.ImageFont, tuple[int, int, int, int], int]]) -> int:
        return min(self._font_size(font) for _, font, _, _ in parts)

    def _padding(self) -> int:
        return 16

    def _line_gap(self) -> int:
        return 6
