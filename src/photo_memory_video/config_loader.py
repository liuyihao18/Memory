from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
AUDIO_EXTENSIONS = {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav"}
DEFAULT_RESOLUTION = (1920, 1080)
DEFAULT_FPS = 30
DEFAULT_SCENE_DURATION = 6.0
DEFAULT_WALL_MAX_PER_PAGE = 6
LAYOUT_MODES = {"auto", "grid", "photo_wall"}
PHOTO_FITS = {"cover", "contain"}


class ConfigError(ValueError):
    """Raised when the video config is invalid."""


@dataclass(frozen=True)
class PhotoTransform:
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None
    rotation: float | None = None
    fit: str | None = None
    z_index: int | None = None


@dataclass(frozen=True)
class PhotoConfig:
    path: Path
    caption: str | None = None
    time: str | None = None
    description: str | None = None
    transform: PhotoTransform | None = None


@dataclass(frozen=True)
class WallLayoutConfig:
    max_per_page: int = DEFAULT_WALL_MAX_PER_PAGE
    rotation: float = 6.0
    overlap: float = 0.12
    style: str = "print"
    card_width: float | None = None
    spread: float = 1.0
    caption_safe: bool = True
    randomness: float = 0.0
    random_seed: int | None = None


@dataclass(frozen=True)
class SceneConfig:
    title: str | None
    description: str | None
    duration: float
    photos: tuple[PhotoConfig, ...]
    layout: str = "auto"
    wall: WallLayoutConfig = field(default_factory=WallLayoutConfig)


@dataclass(frozen=True)
class AudioConfig:
    path: Path | None = None
    volume: float = 0.35
    fade_in: float = 1.0
    fade_out: float = 2.0
    loop: bool = True


@dataclass(frozen=True)
class VideoConfig:
    title: str
    resolution: tuple[int, int] = DEFAULT_RESOLUTION
    fps: int = DEFAULT_FPS
    background_color: tuple[int, int, int] = (24, 22, 20)
    transition_duration: float = 0.8
    fade_duration: float = 0.6
    scene_zoom: bool = True
    font_path: Path | None = None
    audio: AudioConfig = field(default_factory=AudioConfig)


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
    scene_zoom = _parse_bool(raw.get("scene_zoom", True), "video.scene_zoom")
    font_path = _parse_optional_path(raw.get("font"), base_dir)
    audio = _parse_audio(raw.get("audio"), base_dir)

    return VideoConfig(
        title=title,
        resolution=resolution,
        fps=fps,
        background_color=background_color,
        transition_duration=transition_duration,
        fade_duration=fade_duration,
        scene_zoom=scene_zoom,
        font_path=font_path,
        audio=audio,
    )


def _parse_audio(value: Any, base_dir: Path) -> AudioConfig:
    if value is None:
        return AudioConfig()
    if not isinstance(value, Mapping):
        raise ConfigError("video.audio must be a mapping.")

    path = _parse_optional_audio_path(value.get("path"), base_dir)
    volume = _parse_non_negative_float(value.get("volume", 0.35), "video.audio.volume")
    if volume > 2.0:
        raise ConfigError("video.audio.volume must be between 0 and 2.")
    fade_in = _parse_non_negative_float(value.get("fade_in", 1.0), "video.audio.fade_in")
    fade_out = _parse_non_negative_float(value.get("fade_out", 2.0), "video.audio.fade_out")
    loop = _parse_bool(value.get("loop", True), "video.audio.loop")
    return AudioConfig(path=path, volume=volume, fade_in=fade_in, fade_out=fade_out, loop=loop)


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
    layout = _parse_layout(raw.get("layout"), f"scenes[{index}].layout")
    wall = _parse_wall(raw.get("wall"), index)
    photos = _parse_photos(raw.get("photos"), base_dir, index)
    return SceneConfig(
        title=_optional_str(raw.get("title")),
        description=_optional_str(raw.get("description")),
        duration=duration,
        photos=photos,
        layout=layout,
        wall=wall,
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
    transform = _parse_transform(raw.get("transform"), scene_index, photo_index)

    if path.is_dir():
        image_paths = sorted(child for child in path.iterdir() if child.suffix.lower() in IMAGE_EXTENSIONS and child.is_file())
        if not image_paths:
            raise ConfigError(f"Photo directory has no supported images: {path}")
        return [
            PhotoConfig(path=image_path, caption=caption, time=time, description=description, transform=transform)
            for image_path in image_paths
        ]

    if not path.exists():
        raise ConfigError(f"Photo does not exist: {path}")
    if path.suffix.lower() not in IMAGE_EXTENSIONS:
        raise ConfigError(f"Unsupported image type: {path}")
    return [PhotoConfig(path=path, caption=caption, time=time, description=description, transform=transform)]


def _parse_layout(value: Any, label: str) -> str:
    text = (_optional_str(value) or "auto").lower()
    if text not in LAYOUT_MODES:
        raise ConfigError(f"{label} must be one of: {', '.join(sorted(LAYOUT_MODES))}.")
    return text


def _parse_wall(value: Any, scene_index: int) -> WallLayoutConfig:
    if value is None:
        return WallLayoutConfig()
    if not isinstance(value, Mapping):
        raise ConfigError(f"scenes[{scene_index}].wall must be a mapping.")

    max_per_page = _parse_positive_int(value.get("max_per_page", DEFAULT_WALL_MAX_PER_PAGE), f"scenes[{scene_index}].wall.max_per_page")
    if max_per_page > 9:
        raise ConfigError(f"scenes[{scene_index}].wall.max_per_page must be <= 9.")
    rotation = _parse_non_negative_float(value.get("rotation", 6.0), f"scenes[{scene_index}].wall.rotation")
    if rotation > 20:
        raise ConfigError(f"scenes[{scene_index}].wall.rotation must be <= 20.")
    overlap = _parse_non_negative_float(value.get("overlap", 0.12), f"scenes[{scene_index}].wall.overlap")
    if overlap > 0.45:
        raise ConfigError(f"scenes[{scene_index}].wall.overlap must be <= 0.45.")
    style = (_optional_str(value.get("style")) or "print").lower()
    if style not in {"print", "clean"}:
        raise ConfigError(f"scenes[{scene_index}].wall.style must be 'print' or 'clean'.")
    card_width = _parse_optional_range(value.get("card_width"), f"scenes[{scene_index}].wall.card_width", 0.08, 0.95)
    spread = _parse_non_negative_float(value.get("spread", 1.0), f"scenes[{scene_index}].wall.spread")
    if spread < 0.6 or spread > 1.8:
        raise ConfigError(f"scenes[{scene_index}].wall.spread must be between 0.6 and 1.8.")
    caption_safe = _parse_bool(value.get("caption_safe", True), f"scenes[{scene_index}].wall.caption_safe")
    randomness = _parse_non_negative_float(value.get("randomness", 0.0), f"scenes[{scene_index}].wall.randomness")
    if randomness > 2.0:
        raise ConfigError(f"scenes[{scene_index}].wall.randomness must be <= 2.0.")
    random_seed = _parse_optional_int(value.get("random_seed"), f"scenes[{scene_index}].wall.random_seed")
    if random_seed is not None and random_seed < 0:
        raise ConfigError(f"scenes[{scene_index}].wall.random_seed must be >= 0.")
    return WallLayoutConfig(
        max_per_page=max_per_page,
        rotation=rotation,
        overlap=overlap,
        style=style,
        card_width=card_width,
        spread=spread,
        caption_safe=caption_safe,
        randomness=randomness,
        random_seed=random_seed,
    )


def _parse_transform(value: Any, scene_index: int, photo_index: int) -> PhotoTransform | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ConfigError(f"scenes[{scene_index}].photos[{photo_index}].transform must be a mapping.")

    transform = PhotoTransform(
        x=_parse_optional_range(value.get("x"), f"scenes[{scene_index}].photos[{photo_index}].transform.x", 0.0, 1.0),
        y=_parse_optional_range(value.get("y"), f"scenes[{scene_index}].photos[{photo_index}].transform.y", 0.0, 1.0),
        width=_parse_optional_range(value.get("width"), f"scenes[{scene_index}].photos[{photo_index}].transform.width", 0.08, 0.95),
        height=_parse_optional_range(value.get("height"), f"scenes[{scene_index}].photos[{photo_index}].transform.height", 0.08, 0.95),
        rotation=_parse_optional_range(value.get("rotation"), f"scenes[{scene_index}].photos[{photo_index}].transform.rotation", -45.0, 45.0),
        fit=_parse_optional_fit(value.get("fit"), f"scenes[{scene_index}].photos[{photo_index}].transform.fit"),
        z_index=_parse_optional_int(value.get("z_index"), f"scenes[{scene_index}].photos[{photo_index}].transform.z_index"),
    )
    if all(
        item is None
        for item in (
            transform.x,
            transform.y,
            transform.width,
            transform.height,
            transform.rotation,
            transform.fit,
            transform.z_index,
        )
    ):
        return None
    return transform


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


def _parse_optional_audio_path(value: Any, base_dir: Path) -> Path | None:
    text = _optional_str(value)
    if not text:
        return None
    path = _resolve_path(text, base_dir)
    if not path.exists():
        raise ConfigError(f"Audio file does not exist: {path}")
    if not path.is_file():
        raise ConfigError(f"Audio path is not a file: {path}")
    if path.suffix.lower() not in AUDIO_EXTENSIONS:
        raise ConfigError(f"Unsupported audio type: {path}")
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


def _parse_bool(value: Any, label: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "on", "1"}:
            return True
        if normalized in {"false", "no", "off", "0"}:
            return False
    raise ConfigError(f"{label} must be true or false.")


def _parse_optional_range(value: Any, label: str, minimum: float, maximum: float) -> float | None:
    if value is None or _optional_str(value) is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{label} must be a number.") from exc
    if number < minimum or number > maximum:
        raise ConfigError(f"{label} must be between {minimum} and {maximum}.")
    return number


def _parse_optional_int(value: Any, label: str) -> int | None:
    if value is None or _optional_str(value) is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{label} must be an integer.") from exc


def _parse_optional_fit(value: Any, label: str) -> str | None:
    text = _optional_str(value)
    if text is None:
        return None
    normalized = text.lower()
    if normalized not in PHOTO_FITS:
        raise ConfigError(f"{label} must be 'cover' or 'contain'.")
    return normalized


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
