from __future__ import annotations

from dataclasses import dataclass
from math import ceil, sin
from typing import Any, Sequence, TypeVar


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
    rotation: float = 0.0
    z_index: int = 0
    frame: str = "none"


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


def photo_wall_layout(
    count: int,
    canvas_size: tuple[int, int],
    photo_sizes: Sequence[tuple[int, int]] | None = None,
    transforms: Sequence[Any | None] | None = None,
    rotation_limit: float = 6.0,
    overlap: float = 0.12,
    style: str = "print",
    card_width: float | None = None,
    spread: float = 1.0,
    caption_safe: bool = True,
    randomness: float = 0.0,
    random_seed: int | None = None,
) -> list[LayoutSlot]:
    if count < 1:
        raise ValueError("count must be positive.")

    width, height = canvas_size
    presets = _wall_presets(count)
    slots: list[LayoutSlot] = []
    auto_positions: list[bool] = []
    for index in range(count):
        transform = transforms[index] if transforms and index < len(transforms) else None
        center_x, center_y, width_fraction, rotation_unit = presets[index]
        center_x += _jitter(index, count, 1) * 0.018
        center_y += _jitter(index, count, 2) * 0.022
        random_strength = max(0.0, randomness)
        if random_strength > 0:
            center_x += _seeded_jitter(index, count, 11, random_seed) * 0.085 * random_strength
            center_y += _seeded_jitter(index, count, 12, random_seed) * 0.072 * random_strength
        center_x = _spread_value(center_x, spread)
        center_y = _spread_value(center_y, spread)
        if card_width is not None:
            width_fraction = card_width
        else:
            width_fraction *= 1.0 + min(0.45, max(0.0, overlap)) * 0.35
            if random_strength > 0 and not _has_transform_value(transform, "width"):
                width_fraction *= 1.0 + _seeded_jitter(index, count, 13, random_seed) * 0.14 * random_strength

        center_x = float(_transform_value(transform, "x", center_x))
        center_y = float(_transform_value(transform, "y", center_y))
        width_fraction = float(_transform_value(transform, "width", width_fraction))
        auto_rotation = rotation_unit * rotation_limit + _jitter(index, count, 3) * rotation_limit * 0.3
        if random_strength > 0:
            auto_rotation += _seeded_jitter(index, count, 14, random_seed) * rotation_limit * 0.65 * random_strength
        rotation = float(
            _transform_value(
                transform,
                "rotation",
                auto_rotation,
            )
        )

        card_w = max(80, int(width * width_fraction))
        if transform is not None and _transform_value(transform, "height", None) is not None:
            card_h = max(80, int(height * float(_transform_value(transform, "height", 0.3))))
        else:
            card_h = _card_height(card_w, photo_sizes[index] if photo_sizes and index < len(photo_sizes) else None, style)

        rect = _centered_safe_rect(center_x, center_y, card_w, card_h, width, height)
        fit = str(_transform_value(transform, "fit", "contain" if style == "print" else "cover"))
        z_index = int(_transform_value(transform, "z_index", index))
        slots.append(LayoutSlot(rect=rect, fit=fit, rotation=rotation, z_index=z_index, frame=style))
        auto_positions.append(not _has_transform_value(transform, "x") and not _has_transform_value(transform, "y"))
    if caption_safe:
        return _protect_caption_areas(slots, auto_positions, width, height, style)
    return slots


def _wall_presets(count: int) -> list[tuple[float, float, float, float]]:
    presets: dict[int, list[tuple[float, float, float, float]]] = {
        1: [(0.50, 0.54, 0.56, -0.15)],
        2: [(0.39, 0.53, 0.40, -0.75), (0.63, 0.48, 0.40, 0.65)],
        3: [(0.36, 0.54, 0.40, -0.72), (0.64, 0.41, 0.34, 0.55), (0.62, 0.67, 0.32, 0.25)],
        4: [(0.31, 0.38, 0.32, -0.70), (0.62, 0.35, 0.34, 0.45), (0.39, 0.67, 0.34, 0.35), (0.70, 0.66, 0.30, -0.48)],
        5: [(0.28, 0.37, 0.30, -0.70), (0.54, 0.32, 0.32, 0.42), (0.75, 0.43, 0.27, -0.35), (0.38, 0.68, 0.32, 0.38), (0.65, 0.69, 0.31, -0.50)],
        6: [(0.24, 0.34, 0.27, -0.78), (0.49, 0.31, 0.30, 0.42), (0.74, 0.36, 0.27, -0.40), (0.30, 0.67, 0.30, 0.38), (0.56, 0.70, 0.29, -0.55), (0.78, 0.68, 0.25, 0.55)],
    }
    if count <= 6:
        return presets[count]

    cols = ceil(count**0.5)
    rows = ceil(count / cols)
    result: list[tuple[float, float, float, float]] = []
    for index in range(count):
        row = index // cols
        col = index % cols
        x = (col + 0.5) / cols
        y = (row + 0.5) / rows
        result.append((0.16 + x * 0.68, 0.22 + y * 0.60, 0.23, -0.6 if index % 2 == 0 else 0.55))
    return result


def _card_height(card_w: int, photo_size: tuple[int, int] | None, style: str) -> int:
    aspect = 1.35
    if photo_size and photo_size[0] > 0 and photo_size[1] > 0:
        aspect = max(0.68, min(1.7, photo_size[0] / photo_size[1]))
    caption_factor = 1.14 if style == "print" else 1.0
    return max(80, int((card_w / aspect) * caption_factor))


def _spread_value(value: float, spread: float) -> float:
    return 0.5 + (value - 0.5) * max(0.2, spread)


def _protect_caption_areas(
    slots: list[LayoutSlot],
    auto_positions: list[bool],
    canvas_w: int,
    canvas_h: int,
    style: str,
) -> list[LayoutSlot]:
    if len(slots) <= 1 or not any(auto_positions):
        return slots

    rects = [slot.rect for slot in slots]
    for _ in range(18):
        moved = False
        for owner_index, owner_rect in enumerate(rects):
            caption_rect = _caption_safe_rect(owner_rect, style)
            for other_index, other_rect in enumerate(rects):
                if owner_index == other_index or not _rects_overlap(caption_rect, other_rect):
                    continue
                overlap_y = min(caption_rect.bottom, other_rect.bottom) - max(caption_rect.y, other_rect.y)
                if overlap_y <= 0:
                    continue
                direction = -1 if _center_y(other_rect) < _center_y(caption_rect) else 1
                push = max(2, int(overlap_y * 0.55) + 2)
                moved = _move_pair_apart(rects, auto_positions, other_index, owner_index, 0, direction * push, canvas_w, canvas_h) or moved

        for first in range(len(rects)):
            for second in range(first + 1, len(rects)):
                overlap_x = min(rects[first].right, rects[second].right) - max(rects[first].x, rects[second].x)
                overlap_y = min(rects[first].bottom, rects[second].bottom) - max(rects[first].y, rects[second].y)
                if overlap_x <= 0 or overlap_y <= 0:
                    continue
                if min(overlap_x, overlap_y) < min(rects[first].width, rects[first].height, rects[second].width, rects[second].height) * 0.08:
                    continue
                if overlap_x < overlap_y:
                    direction = -1 if _center_x(rects[first]) < _center_x(rects[second]) else 1
                    moved = _move_pair_apart(rects, auto_positions, first, second, direction * max(2, int(overlap_x * 0.22)), 0, canvas_w, canvas_h) or moved
                else:
                    direction = -1 if _center_y(rects[first]) < _center_y(rects[second]) else 1
                    moved = _move_pair_apart(rects, auto_positions, first, second, 0, direction * max(2, int(overlap_y * 0.22)), canvas_w, canvas_h) or moved
        if not moved:
            break

    return [
        LayoutSlot(rect=rect, fit=slot.fit, rotation=slot.rotation, z_index=slot.z_index, frame=slot.frame)
        for slot, rect in zip(slots, rects)
    ]


def _caption_safe_rect(rect: Rect, style: str) -> Rect:
    caption_h = max(18, int(rect.height * (0.18 if style == "print" else 0.16)))
    return Rect(rect.x, rect.bottom - caption_h, rect.width, caption_h)


def _move_pair_apart(
    rects: list[Rect],
    auto_positions: list[bool],
    first: int,
    second: int,
    dx: int,
    dy: int,
    canvas_w: int,
    canvas_h: int,
) -> bool:
    moved = False
    if auto_positions[first] and auto_positions[second]:
        moved = _move_rect(rects, first, dx // 2, dy // 2, canvas_w, canvas_h) or moved
        moved = _move_rect(rects, second, -(dx - dx // 2), -(dy - dy // 2), canvas_w, canvas_h) or moved
    elif auto_positions[first]:
        moved = _move_rect(rects, first, dx, dy, canvas_w, canvas_h) or moved
    elif auto_positions[second]:
        moved = _move_rect(rects, second, -dx, -dy, canvas_w, canvas_h) or moved
    return moved


def _move_rect(rects: list[Rect], index: int, dx: int, dy: int, canvas_w: int, canvas_h: int) -> bool:
    if dx == 0 and dy == 0:
        return False
    rect = rects[index]
    moved = _clamp_rect(Rect(rect.x + dx, rect.y + dy, rect.width, rect.height), canvas_w, canvas_h)
    if moved == rect:
        return False
    rects[index] = moved
    return True


def _clamp_rect(rect: Rect, canvas_w: int, canvas_h: int) -> Rect:
    margin = max(18, int(min(canvas_w, canvas_h) * 0.035))
    x = max(margin, min(canvas_w - margin - rect.width, rect.x))
    y = max(margin, min(canvas_h - margin - rect.height, rect.y))
    return Rect(x, y, rect.width, rect.height)


def _rects_overlap(first: Rect, second: Rect) -> bool:
    return first.x < second.right and first.right > second.x and first.y < second.bottom and first.bottom > second.y


def _center_x(rect: Rect) -> float:
    return rect.x + rect.width / 2


def _center_y(rect: Rect) -> float:
    return rect.y + rect.height / 2


def _centered_safe_rect(center_x: float, center_y: float, card_w: int, card_h: int, canvas_w: int, canvas_h: int) -> Rect:
    margin = max(18, int(min(canvas_w, canvas_h) * 0.035))
    card_w = min(card_w, canvas_w - margin * 2)
    card_h = min(card_h, canvas_h - margin * 2)
    x = int(center_x * canvas_w - card_w / 2)
    y = int(center_y * canvas_h - card_h / 2)
    x = max(margin, min(canvas_w - margin - card_w, x))
    y = max(margin, min(canvas_h - margin - card_h, y))
    return Rect(x, y, card_w, card_h)


def _transform_value(transform: Any | None, name: str, default: Any) -> Any:
    if transform is None:
        return default
    value = getattr(transform, name, None)
    return default if value is None else value


def _has_transform_value(transform: Any | None, name: str) -> bool:
    return transform is not None and getattr(transform, name, None) is not None


def _jitter(index: int, count: int, salt: int) -> float:
    value = sin((index + 1) * 12.9898 + count * 78.233 + salt * 37.719) * 43758.5453
    return (value % 1.0) - 0.5


def _seeded_jitter(index: int, count: int, salt: int, seed: int | None) -> float:
    seed_value = 0 if seed is None else seed
    value = sin((index + 1) * 127.1 + count * 311.7 + salt * 74.7 + seed_value * 0.017) * 43758.5453
    return (value % 1.0) - 0.5


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
