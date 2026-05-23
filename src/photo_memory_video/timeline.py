from __future__ import annotations

from dataclasses import dataclass

from .config_loader import PhotoConfig, ProjectConfig
from .layout import paginate_items


@dataclass(frozen=True)
class ScenePage:
    scene_index: int
    page_index: int
    page_count: int
    title: str | None
    description: str | None
    duration: float
    photos: tuple[PhotoConfig, ...]


def build_scene_pages(config: ProjectConfig) -> tuple[ScenePage, ...]:
    pages: list[ScenePage] = []
    for scene_index, scene in enumerate(config.scenes):
        photo_pages = paginate_items(scene.photos, max_per_page=4)
        page_duration = scene.duration / len(photo_pages)
        for page_index, photos in enumerate(photo_pages):
            pages.append(
                ScenePage(
                    scene_index=scene_index,
                    page_index=page_index,
                    page_count=len(photo_pages),
                    title=scene.title,
                    description=scene.description,
                    duration=page_duration,
                    photos=photos,
                )
            )
    return tuple(pages)
