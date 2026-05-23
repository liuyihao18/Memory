from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Sequence, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class Size:
    width: int
    height: int

    @property
    def aspect(self) -> float:
        return self.width / self.height


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    @property
    def aspect(self) -> float:
        return self.width / self.height

    def inset(self, value: int) -> "Rect":
        return Rect(self.x + value, self.y + value, self.width - value * 2, self.height - value * 2)


@dataclass(frozen=True)
class LayoutSlot:
    rect: Rect
    fit: str = "cover"


def paginate_items(items: Sequence[T], max_per_page: int = 4) -> list[tuple[T, ...]]:
    if max_per_page < 1:
        raise ValueError("max_per_page must be positive.")
    if len(items) <= max_per_page:
        return [tuple(items)]

    page_count = ceil(len(items) / max_per_page)
    base_size = len(items) // page_count
    extra = len(items) % page_count
    pages: list[tuple[T, ...]] = []
    cursor = 0
    for page_index in range(page_count):
        page_size = base_size + (1 if page_index < extra else 0)
        pages.append(tuple(items[cursor : cursor + page_size]))
        cursor += page_size
    return pages


def layout_for_count(
    count: int,
    canvas_size: tuple[int, int],
    photo_sizes: Sequence[tuple[int, int]] | None = None,
) -> list[LayoutSlot]:
    if count < 1:
        raise ValueError("count must be positive.")
    if count > 4:
        raise ValueError("layout_for_count supports up to 4 photos; paginate first.")

    width, height = canvas_size
    margin = max(42, int(min(width, height) * 0.065))
    gap = max(18, int(min(width, height) * 0.026))
    outer = Rect(margin, margin, width - margin * 2, height - margin * 2)

    if count == 1:
        fit = "cover"
        if photo_sizes:
            aspect = photo_sizes[0][0] / photo_sizes[0][1]
            if aspect < 1.1 or aspect > 2.35:
                fit = "contain"
        rect = Rect(0, 0, width, height) if fit == "cover" else outer
        return [LayoutSlot(rect=rect, fit=fit)]

    if count == 2:
        horizontal = _two_column_layout(outer, gap)
        vertical = _two_row_layout(outer, gap)
        if photo_sizes and _score_layout(photo_sizes, horizontal) < _score_layout(photo_sizes, vertical):
            return [LayoutSlot(rect=rect) for rect in vertical]
        return [LayoutSlot(rect=rect) for rect in horizontal]

    if count == 3:
        large_w = int((outer.width - gap) * 0.58)
        small_w = outer.width - gap - large_w
        small_h = (outer.height - gap) // 2
        rects = [
            Rect(outer.x, outer.y, large_w, outer.height),
            Rect(outer.x + large_w + gap, outer.y, small_w, small_h),
            Rect(outer.x + large_w + gap, outer.y + small_h + gap, small_w, outer.height - small_h - gap),
        ]
        return [LayoutSlot(rect=rect) for rect in rects]

    cell_w = (outer.width - gap) // 2
    cell_h = (outer.height - gap) // 2
    rects = [
        Rect(outer.x, outer.y, cell_w, cell_h),
        Rect(outer.x + cell_w + gap, outer.y, outer.width - cell_w - gap, cell_h),
        Rect(outer.x, outer.y + cell_h + gap, cell_w, outer.height - cell_h - gap),
        Rect(outer.x + cell_w + gap, outer.y + cell_h + gap, outer.width - cell_w - gap, outer.height - cell_h - gap),
    ]
    return [LayoutSlot(rect=rect) for rect in rects]


def _two_column_layout(outer: Rect, gap: int) -> list[Rect]:
    cell_w = (outer.width - gap) // 2
    return [
        Rect(outer.x, outer.y, cell_w, outer.height),
        Rect(outer.x + cell_w + gap, outer.y, outer.width - cell_w - gap, outer.height),
    ]


def _two_row_layout(outer: Rect, gap: int) -> list[Rect]:
    cell_h = (outer.height - gap) // 2
    return [
        Rect(outer.x, outer.y, outer.width, cell_h),
        Rect(outer.x, outer.y + cell_h + gap, outer.width, outer.height - cell_h - gap),
    ]


def _score_layout(photo_sizes: Sequence[tuple[int, int]], rects: Sequence[Rect]) -> float:
    return sum(_cover_visible_fraction(Size(*size), rect) for size, rect in zip(photo_sizes, rects)) / len(rects)


def _cover_visible_fraction(photo: Size, rect: Rect) -> float:
    scale = max(rect.width / photo.width, rect.height / photo.height)
    visible_width = rect.width / scale
    visible_height = rect.height / scale
    return min(1.0, (visible_width * visible_height) / (photo.width * photo.height))
