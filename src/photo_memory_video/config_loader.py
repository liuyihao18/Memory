from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
DEFAULT_RESOLUTION = (1920, 1080)
DEFAULT_FPS = 30
DEFAULT_SCENE_DURATION = 6.0


class ConfigError(ValueError):
    """Raised when the video config is invalid."""


@dataclass(frozen=True)
class PhotoConfig:
    path: Path
    caption: str | None = None
    time: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class SceneConfig:
    title: str | None
    description: str | None
    duration: float
    photos: tuple[PhotoConfig, ...]


@dataclass(frozen=True)
class VideoConfig:
    title: str
    resolution: tuple[int, int] = DEFAULT_RESOLUTION
    fps: int = DEFAULT_FPS
    background_color: tuple[int, int, int] = (24, 22, 20)
    transition_duration: float = 0.8
    fade_duration: float = 0.6
    font_path: Path | None = None


@dataclass(frozen=True)
class ProjectConfig:
    source_path: Path
    base_dir: Path
    video: VideoConfig
    scenes: tuple[SceneConfig, ...]


def load_config(path: str | Path) -> ProjectConfig:
    config_path = Path(path).expanduser().resolve()
    if not config_path.exists():
        raise ConfigError(f"Config file does not exist: {config_path}")

    raw = _read_config_file(config_path)
    return load_config_data(raw, config_path)


def load_config_data(raw: Mapping[str, Any], source_path: str | Path) -> ProjectConfig:
    config_path = Path(source_path).expanduser().resolve()
    if not isinstance(raw, Mapping):
        raise ConfigError("Config root must be a mapping.")
    video = _parse_video(raw.get("video") or {}, config_path.parent)
    scenes = _parse_scenes(raw.get("scenes"), config_path.parent)
    return ProjectConfig(source_path=config_path, base_dir=config_path.parent, video=video, scenes=scenes)


def _read_config_file(path: Path) -> Mapping[str, Any]:
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8")
    if suffix in {".yaml", ".yml"}:
        loaded = yaml.safe_load(text)
    elif suffix == ".json":
        loaded = json.loads(text)
    else:
        raise ConfigError("Config must be a YAML or JSON file.")

    if not isinstance(loaded, Mapping):
        raise ConfigError("Config root must be a mapping.")
    return loaded


def _parse_video(raw: Mapping[str, Any], base_dir: Path) -> VideoConfig:
    if not isinstance(raw, Mapping):
        raise ConfigError("video must be a mapping.")

    title = _optional_str(raw.get("title")) or "大学回忆"
    resolution = _parse_resolution(raw.get("resolution", DEFAULT_RESOLUTION))
    fps = _parse_positive_int(raw.get("fps", DEFAULT_FPS), "video.fps")
    background_color = _parse_color(raw.get("background_color", "#181614"))
    transition_duration = _parse_non_negative_float(raw.get("transition_duration", 0.8), "video.transition_duration")
    fade_duration = _parse_non_negative_float(raw.get("fade_duration", 0.6), "video.fade_duration")
    font_path = _parse_optional_path(raw.get("font"), base_dir)

    return VideoConfig(
        title=title,
        resolution=resolution,
        fps=fps,
        background_color=background_color,
        transition_duration=transition_duration,
        fade_duration=fade_duration,
        font_path=font_path,
    )


def _parse_scenes(raw: Any, base_dir: Path) -> tuple[SceneConfig, ...]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise ConfigError("scenes must be a non-empty list.")
    if not raw:
        raise ConfigError("scenes must contain at least one scene.")

    scenes: list[SceneConfig] = []
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise ConfigError(f"scenes[{index}] must be a mapping.")
        scenes.append(_parse_scene(item, base_dir, index))
    return tuple(scenes)


def _parse_scene(raw: Mapping[str, Any], base_dir: Path, index: int) -> SceneConfig:
    duration = _parse_positive_float(raw.get("duration", DEFAULT_SCENE_DURATION), f"scenes[{index}].duration")
    photos = _parse_photos(raw.get("photos"), base_dir, index)
    return SceneConfig(
        title=_optional_str(raw.get("title")),
        description=_optional_str(raw.get("description")),
        duration=duration,
        photos=photos,
    )


def _parse_photos(raw: Any, base_dir: Path, scene_index: int) -> tuple[PhotoConfig, ...]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise ConfigError(f"scenes[{scene_index}].photos must be a non-empty list.")
    if not raw:
        raise ConfigError(f"scenes[{scene_index}].photos must contain at least one photo.")

    photos: list[PhotoConfig] = []
    for photo_index, item in enumerate(raw):
        photos.extend(_expand_photo_entry(item, base_dir, scene_index, photo_index))
    if not photos:
        raise ConfigError(f"scenes[{scene_index}].photos did not resolve to any images.")
    return tuple(photos)


def _expand_photo_entry(item: Any, base_dir: Path, scene_index: int, photo_index: int) -> list[PhotoConfig]:
    if isinstance(item, (str, Path)):
        raw: Mapping[str, Any] = {"path": str(item)}
    elif isinstance(item, Mapping):
        raw = item
    else:
        raise ConfigError(f"scenes[{scene_index}].photos[{photo_index}] must be a path or mapping.")

    raw_path = _optional_str(raw.get("path"))
    if not raw_path:
        raise ConfigError(f"scenes[{scene_index}].photos[{photo_index}].path is required.")

    path = _resolve_path(raw_path, base_dir)
    caption = _optional_str(raw.get("caption"))
    time = _optional_str(raw.get("time"))
    description = _optional_str(raw.get("description"))

    if path.is_dir():
        image_paths = sorted(child for child in path.iterdir() if child.suffix.lower() in IMAGE_EXTENSIONS and child.is_file())
        if not image_paths:
            raise ConfigError(f"Photo directory has no supported images: {path}")
        return [PhotoConfig(path=image_path, caption=caption, time=time, description=description) for image_path in image_paths]

    if not path.exists():
        raise ConfigError(f"Photo does not exist: {path}")
    if path.suffix.lower() not in IMAGE_EXTENSIONS:
        raise ConfigError(f"Unsupported image type: {path}")
    return [PhotoConfig(path=path, caption=caption, time=time, description=description)]


def _resolve_path(value: str, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _parse_optional_path(value: Any, base_dir: Path) -> Path | None:
    text = _optional_str(value)
    if not text:
        return None
    path = _resolve_path(text, base_dir)
    if not path.exists():
        raise ConfigError(f"Font file does not exist: {path}")
    return path


def _parse_resolution(value: Any) -> tuple[int, int]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 2:
        raise ConfigError("video.resolution must be [width, height].")
    width = _parse_positive_int(value[0], "video.resolution[0]")
    height = _parse_positive_int(value[1], "video.resolution[1]")
    return (width, height)


def _parse_color(value: Any) -> tuple[int, int, int]:
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("#") and len(text) == 7:
            try:
                return tuple(int(text[i : i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]
            except ValueError as exc:
                raise ConfigError(f"Invalid color: {value}") from exc
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) == 3:
        channels = tuple(_parse_channel(channel, "video.background_color") for channel in value)
        return channels  # type: ignore[return-value]
    raise ConfigError("video.background_color must be '#RRGGBB' or [r, g, b].")


def _parse_channel(value: Any, label: str) -> int:
    number = _parse_positive_int(value, label, allow_zero=True)
    if number > 255:
        raise ConfigError(f"{label} channel must be <= 255.")
    return number


def _parse_positive_int(value: Any, label: str, allow_zero: bool = False) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{label} must be an integer.") from exc
    if number < 0 or (number == 0 and not allow_zero):
        raise ConfigError(f"{label} must be positive.")
    return number


def _parse_positive_float(value: Any, label: str) -> float:
    number = _parse_non_negative_float(value, label)
    if number <= 0:
        raise ConfigError(f"{label} must be positive.")
    return number


def _parse_non_negative_float(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{label} must be a number.") from exc
    if number < 0:
        raise ConfigError(f"{label} must be >= 0.")
    return number


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
