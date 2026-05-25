from __future__ import annotations

from photo_memory_video.layout import photo_wall_layout, layout_for_count, paginate_items


def test_layout_boxes_stay_inside_canvas() -> None:
    for count in range(1, 5):
        slots = layout_for_count(count, (1920, 1080), [(1600, 1000)] * count)
        assert len(slots) == count
        for slot in slots:
            assert slot.rect.x >= 0
            assert slot.rect.y >= 0
            assert slot.rect.right <= 1920
            assert slot.rect.bottom <= 1080
            assert slot.rect.width > 0
            assert slot.rect.height > 0


def test_paginate_balances_five_or_more_photos() -> None:
    assert [len(page) for page in paginate_items(tuple(range(5)), max_per_page=4)] == [3, 2]
    assert [len(page) for page in paginate_items(tuple(range(9)), max_per_page=4)] == [3, 3, 3]


def test_photo_wall_layout_adds_rotation_and_frames() -> None:
    slots = photo_wall_layout(5, (1920, 1080), [(1200, 800)] * 5, rotation_limit=8)

    assert len(slots) == 5
    assert any(abs(slot.rotation) > 0.5 for slot in slots)
    assert {slot.frame for slot in slots} == {"print"}
    for slot in slots:
        assert slot.rect.x >= 0
        assert slot.rect.y >= 0
        assert slot.rect.right <= 1920
        assert slot.rect.bottom <= 1080


def test_photo_wall_card_width_sets_auto_card_size() -> None:
    slots = photo_wall_layout(3, (1000, 600), [(1200, 800)] * 3, card_width=0.28)

    assert [slot.rect.width for slot in slots] == [280, 280, 280]


def test_photo_wall_spread_changes_auto_positions() -> None:
    compact = photo_wall_layout(4, (1000, 600), [(1200, 800)] * 4, spread=0.75, caption_safe=False)
    loose = photo_wall_layout(4, (1000, 600), [(1200, 800)] * 4, spread=1.35, caption_safe=False)

    compact_distance = sum(abs((slot.rect.x + slot.rect.width / 2) / 1000 - 0.5) for slot in compact)
    loose_distance = sum(abs((slot.rect.x + slot.rect.width / 2) / 1000 - 0.5) for slot in loose)

    assert loose_distance > compact_distance


def test_photo_wall_random_seed_is_reproducible() -> None:
    first = photo_wall_layout(
        5,
        (1000, 600),
        [(1200, 800)] * 5,
        randomness=0.8,
        random_seed=123,
        caption_safe=False,
    )
    second = photo_wall_layout(
        5,
        (1000, 600),
        [(1200, 800)] * 5,
        randomness=0.8,
        random_seed=123,
        caption_safe=False,
    )
    other = photo_wall_layout(
        5,
        (1000, 600),
        [(1200, 800)] * 5,
        randomness=0.8,
        random_seed=456,
        caption_safe=False,
    )

    assert _slot_signature(first) == _slot_signature(second)
    assert _slot_signature(first) != _slot_signature(other)


def test_photo_wall_random_seed_is_ignored_without_randomness() -> None:
    first = photo_wall_layout(
        5,
        (1000, 600),
        [(1200, 800)] * 5,
        randomness=0,
        random_seed=123,
        caption_safe=False,
    )
    other = photo_wall_layout(
        5,
        (1000, 600),
        [(1200, 800)] * 5,
        randomness=0,
        random_seed=456,
        caption_safe=False,
    )

    assert _slot_signature(first) == _slot_signature(other)


def test_photo_wall_caption_safe_reduces_bottom_caption_overlap() -> None:
    sizes = [(900, 650)] * 6
    unsafe = photo_wall_layout(6, (1280, 720), sizes, card_width=0.34, caption_safe=False)
    safe = photo_wall_layout(6, (1280, 720), sizes, card_width=0.34, caption_safe=True)

    assert _caption_overlap_score(safe) < _caption_overlap_score(unsafe)
    for slot in safe:
        assert slot.rect.x >= 0
        assert slot.rect.y >= 0
        assert slot.rect.right <= 1280
        assert slot.rect.bottom <= 720


def _slot_signature(slots) -> list[tuple[int, int, int, int, float]]:
    return [(slot.rect.x, slot.rect.y, slot.rect.width, slot.rect.height, round(slot.rotation, 4)) for slot in slots]


def _caption_overlap_score(slots) -> int:
    score = 0
    for owner_index, owner in enumerate(slots):
        caption = _caption_rect(owner.rect)
        for other_index, other in enumerate(slots):
            if owner_index != other_index:
                score += _overlap_area(caption, other.rect)
    return score


def _caption_rect(rect) -> tuple[int, int, int, int]:
    caption_h = max(18, int(rect.height * 0.18))
    return (rect.x, rect.bottom - caption_h, rect.right, rect.bottom)


def _overlap_area(first: tuple[int, int, int, int], second) -> int:
    width = max(0, min(first[2], second.right) - max(first[0], second.x))
    height = max(0, min(first[3], second.bottom) - max(first[1], second.y))
    return width * height
