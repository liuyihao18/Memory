from __future__ import annotations

from dataclasses import dataclass

from .layout import Rect


PRINT_CARD_PAD_RATIO = 0.038
CLEAN_CARD_PAD_RATIO = 0.026
PRINT_LABEL_HEIGHT_RATIO = 0.115
CLEAN_LABEL_HEIGHT_RATIO = 0.16
CLEAN_LABEL_HORIZONTAL_PAD_RATIO = 0.025
CLEAN_LABEL_BOTTOM_PAD_RATIO = 0.035
LABEL_FONT_RATIO = 0.54
LABEL_FONT_MIN_HEIGHT_RATIO = 0.44
LABEL_FONT_MAX_HEIGHT_RATIO = 0.62
LABEL_FONT_MIN_WIDTH_RATIO = 0.042
LABEL_FONT_MAX_WIDTH_RATIO = 0.08
LABEL_FONT_MIN = 20


@dataclass(frozen=True)
class PhotoCardMetrics:
    photo_rect: Rect
    label_rect: Rect | None
    label_font_size: int


def photo_card_metrics(
    card_rect: Rect,
    frame: str,
    has_label: bool,
    render_scale: int = 1,
) -> PhotoCardMetrics:
    scale = max(1, int(render_scale))
    pad_ratio = PRINT_CARD_PAD_RATIO if frame == "print" else CLEAN_CARD_PAD_RATIO
    pad = max(8 * scale, int(min(card_rect.width, card_rect.height) * pad_ratio))

    if frame == "print":
        label_h = max(0, int(card_rect.height * PRINT_LABEL_HEIGHT_RATIO)) if has_label else 0
        photo_rect = Rect(
            pad,
            pad,
            max(1, card_rect.width - pad * 2),
            max(1, card_rect.height - pad * 2 - label_h),
        )
        label_rect = (
            Rect(pad, card_rect.height - pad - label_h, photo_rect.width, label_h)
            if label_h > 0
            else None
        )
        label_width = label_rect.width if label_rect else None
        return PhotoCardMetrics(
            photo_rect=photo_rect,
            label_rect=label_rect,
            label_font_size=card_label_font_size(label_h, scale, label_width),
        )

    photo_rect = Rect(
        pad,
        pad,
        max(1, card_rect.width - pad * 2),
        max(1, card_rect.height - pad * 2),
    )
    if not has_label:
        return PhotoCardMetrics(photo_rect=photo_rect, label_rect=None, label_font_size=0)

    label_h = max(22 * scale, int(card_rect.height * CLEAN_LABEL_HEIGHT_RATIO))
    label_pad_x = max(8 * scale, int(card_rect.width * CLEAN_LABEL_HORIZONTAL_PAD_RATIO))
    label_bottom = max(8 * scale, int(card_rect.height * CLEAN_LABEL_BOTTOM_PAD_RATIO))
    label_rect = Rect(
        label_pad_x,
        max(pad, card_rect.height - label_bottom - label_h),
        max(1, card_rect.width - label_pad_x * 2),
        label_h,
    )
    return PhotoCardMetrics(
        photo_rect=photo_rect,
        label_rect=label_rect,
        label_font_size=card_label_font_size(label_h, scale, label_rect.width),
    )


def photo_card_metrics_payload(metrics: PhotoCardMetrics, card_rect: Rect) -> dict[str, object]:
    payload: dict[str, object] = {
        "photo": _rect_payload(metrics.photo_rect, card_rect),
        "label": None,
        "labelFontSize": _ratio(metrics.label_font_size, card_rect.height),
    }
    if metrics.label_rect:
        payload["label"] = _rect_payload(metrics.label_rect, card_rect)
    return payload


def card_label_font_size(label_height: int, render_scale: int = 1, label_width: int | None = None) -> int:
    scale = max(1, int(render_scale))
    if label_height <= 0:
        return 0
    absolute_min = LABEL_FONT_MIN * scale
    min_size = max(absolute_min, int(label_height * LABEL_FONT_MIN_HEIGHT_RATIO))
    max_size = max(absolute_min, int(label_height * LABEL_FONT_MAX_HEIGHT_RATIO))
    if label_width is not None:
        min_size = max(min_size, int(label_width * LABEL_FONT_MIN_WIDTH_RATIO))
        max_size = max(absolute_min, min(max_size, int(label_width * LABEL_FONT_MAX_WIDTH_RATIO)))
    if min_size > max_size:
        min_size = max_size
    size = int(label_height * LABEL_FONT_RATIO)
    return max(min_size, min(max_size, size))


def _rect_payload(rect: Rect, card_rect: Rect) -> dict[str, float]:
    return {
        "x": _ratio(rect.x, card_rect.width),
        "y": _ratio(rect.y, card_rect.height),
        "width": _ratio(rect.width, card_rect.width),
        "height": _ratio(rect.height, card_rect.height),
    }


def _ratio(value: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(value / total, 4)
