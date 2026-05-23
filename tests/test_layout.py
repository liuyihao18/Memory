from __future__ import annotations

from photo_memory_video.layout import layout_for_count, paginate_items


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
