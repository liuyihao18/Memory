from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .config_loader import ConfigError, ProjectConfig
from .timeline import build_scene_pages


def project_to_editor_state(config: ProjectConfig, output_path: Path | None = None) -> dict[str, Any]:
    return {
        "configPath": str(config.source_path),
        "outputPath": str(output_path) if output_path else str(config.base_dir / "output" / f"{config.source_path.stem}.mp4"),
        "video": {
            "title": config.video.title,
            "resolution": list(config.video.resolution),
            "fps": config.video.fps,
            "background_color": rgb_to_hex(config.video.background_color),
            "transition_duration": config.video.transition_duration,
            "fade_duration": config.video.fade_duration,
            "font": display_path(config.video.font_path, config.base_dir) if config.video.font_path else "",
        },
        "scenes": [
            {
                "title": scene.title or "",
                "description": scene.description or "",
                "duration": scene.duration,
                "photos": [
                    {
                        **photo_state(photo.path, config.base_dir),
                        "caption": photo.caption or "",
                        "time": photo.time or "",
                        "description": photo.description or "",
                    }
                    for photo in scene.photos
                ],
            }
            for scene in config.scenes
        ],
    }


def state_to_config_data(state: Mapping[str, Any]) -> dict[str, Any]:
    video = state.get("video")
    scenes = state.get("scenes")
    if not isinstance(video, Mapping):
        raise ConfigError("state.video must be a mapping.")
    if not isinstance(scenes, list) or not scenes:
        raise ConfigError("state.scenes must be a non-empty list.")

    data: dict[str, Any] = {
        "video": compact_mapping(
            {
                "title": optional_text(video.get("title")) or "大学回忆",
                "resolution": parse_resolution(video.get("resolution")),
                "fps": parse_int(video.get("fps"), "video.fps"),
                "background_color": optional_text(video.get("background_color")) or "#181614",
                "transition_duration": parse_float(video.get("transition_duration"), "video.transition_duration"),
                "fade_duration": parse_float(video.get("fade_duration"), "video.fade_duration"),
                "font": optional_text(video.get("font")),
            }
        ),
        "scenes": [],
    }

    for scene_index, raw_scene in enumerate(scenes):
        if not isinstance(raw_scene, Mapping):
            raise ConfigError(f"scenes[{scene_index}] must be a mapping.")
        raw_photos = raw_scene.get("photos")
        if not isinstance(raw_photos, list) or not raw_photos:
            raise ConfigError(f"scenes[{scene_index}].photos must be a non-empty list.")
        scene = compact_mapping(
            {
                "title": optional_text(raw_scene.get("title")),
                "description": optional_text(raw_scene.get("description")),
                "duration": parse_float(raw_scene.get("duration"), f"scenes[{scene_index}].duration"),
                "photos": [photo_to_config(photo, scene_index, photo_index) for photo_index, photo in enumerate(raw_photos)],
            }
        )
        data["scenes"].append(scene)
    return data


def photo_to_config(raw_photo: Any, scene_index: int, photo_index: int) -> dict[str, Any]:
    if not isinstance(raw_photo, Mapping):
        raise ConfigError(f"scenes[{scene_index}].photos[{photo_index}] must be a mapping.")
    path = optional_text(raw_photo.get("path"))
    if not path:
        raise ConfigError(f"scenes[{scene_index}].photos[{photo_index}].path is required.")
    return compact_mapping(
        {
            "path": path,
            "time": optional_text(raw_photo.get("time")),
            "caption": optional_text(raw_photo.get("caption")),
            "description": optional_text(raw_photo.get("description")),
        }
    )


def scene_pages_state(config: ProjectConfig) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    for page in build_scene_pages(config):
        pages.append(
            {
                "sceneIndex": page.scene_index,
                "pageIndex": page.page_index,
                "pageCount": page.page_count,
                "duration": page.duration,
                "photoCount": len(page.photos),
                "photos": [display_path(photo.path, config.base_dir) for photo in page.photos],
                "title": page.title or "",
            }
        )
    return pages


def find_page_state(pages: list[dict[str, Any]], scene_index: int, page_index: int) -> dict[str, Any]:
    for page in pages:
        if page["sceneIndex"] == scene_index and page["pageIndex"] == page_index:
            return page
    raise ConfigError(f"Preview page does not exist: scene {scene_index + 1}, page {page_index + 1}")


def photo_state(path: Path, base_dir: Path) -> dict[str, Any]:
    resolved = path.resolve()
    return {
        "path": display_path(resolved, base_dir),
        "resolvedPath": str(resolved),
        "mediaUrl": f"/media?path={quote_path(resolved)}",
    }


def selected_path_state(path: Path, base_dir: Path) -> dict[str, Any]:
    resolved = path.resolve()
    return {
        "path": display_path(resolved, base_dir),
        "resolvedPath": str(resolved),
    }


def display_path(path: Path | None, base_dir: Path) -> str:
    if path is None:
        return ""
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(base_dir.resolve())).replace("\\", "/")
    except ValueError:
        return str(resolved)


def preview_time_for_config(config: ProjectConfig, requested_time: float | None = None) -> float:
    if requested_time is not None and requested_time > 0:
        return requested_time
    first_scene_duration = config.scenes[0].duration if config.scenes else 1.0
    after_fade = max(0.5, config.video.fade_duration + 0.25)
    return min(after_fade, max(0.0, first_scene_duration - 0.05))


def compact_mapping(values: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value not in (None, "")}


def optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_resolution(value: Any) -> list[int]:
    if not isinstance(value, list) or len(value) != 2:
        raise ConfigError("video.resolution must be [width, height].")
    return [parse_int(value[0], "video.resolution[0]"), parse_int(value[1], "video.resolution[1]")]


def parse_int(value: Any, label: str, allow_zero: bool = False) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{label} must be an integer.") from exc
    if number < 0 or (number == 0 and not allow_zero):
        raise ConfigError(f"{label} must be positive.")
    return number


def parse_float(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{label} must be a number.") from exc
    if number < 0:
        raise ConfigError(f"{label} must be >= 0.")
    return number


def rgb_to_hex(color: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*color)


def quote_path(path: Path) -> str:
    from urllib.parse import quote

    return quote(str(path))
