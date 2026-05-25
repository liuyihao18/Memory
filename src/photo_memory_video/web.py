from __future__ import annotations

import json
import mimetypes
import threading
import time
import uuid
import webbrowser
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Literal, Mapping
from urllib.parse import parse_qs, quote, unquote, urlparse

import yaml
from PIL import Image, ImageOps

from .config_loader import (
    ConfigError,
    IMAGE_EXTENSIONS,
    PhotoTransform,
    ProjectConfig,
    load_config,
    load_config_data,
)
from .file_dialogs import open_directory_dialog, open_file_dialog
from .layout import photo_wall_layout
from .render import render_preview_frame, render_preview_page, render_video
from .timeline import ScenePage, build_scene_pages
from .web_state import (
    find_page_state,
    optional_text,
    parse_float,
    parse_int,
    photo_state,
    preview_time_for_config,
    project_to_editor_state,
    scene_pages_state,
    selected_path_state,
    state_to_config_data,
)


STATIC_DIR = Path(__file__).resolve().parent / "web_static"
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm"}


class WebError(Exception):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class RenderJob:
    id: str
    output_path: Path
    status: str = "queued"
    progress: float = 0.0
    message: str = "等待渲染"
    error: str | None = None
    url: str | None = None
    updated_at: float = field(default_factory=time.time)
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def update(self, progress: float | None = None, message: str | None = None, status: str | None = None) -> None:
        with self.lock:
            if progress is not None:
                self.progress = max(0.0, min(1.0, progress))
            if message:
                self.message = message
            if status:
                self.status = status
            self.updated_at = time.time()

    def complete(self, url: str) -> None:
        with self.lock:
            self.status = "done"
            self.progress = 1.0
            self.message = "渲染完成"
            self.url = url
            self.updated_at = time.time()

    def fail(self, error: str) -> None:
        with self.lock:
            self.status = "failed"
            self.error = error
            self.message = error
            self.updated_at = time.time()

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "id": self.id,
                "status": self.status,
                "progress": self.progress,
                "message": self.message,
                "error": self.error,
                "path": str(self.output_path),
                "url": self.url,
                "updatedAt": self.updated_at,
            }


class WebWorkspace:
    def __init__(self, config_path: Path, output_path: Path | None = None) -> None:
        self.config_path = config_path.expanduser().resolve()
        self.base_dir = self.config_path.parent
        self.output_path = (output_path or self.base_dir / "output" / f"{self.config_path.stem}.mp4").expanduser().resolve()
        self.preview_path = self.base_dir / "output" / "web_preview.png"
        self.render_jobs: dict[str, RenderJob] = {}
        self.render_jobs_lock = threading.Lock()

    def load_state(self) -> dict[str, Any]:
        config = load_config(self.config_path)
        return project_to_editor_state(config, self.output_path)

    def save_state(self, state: Mapping[str, Any]) -> dict[str, Any]:
        data = state_to_config_data(state)
        load_config_data(data, self.config_path)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        return self.load_state()

    def preview_state(
        self,
        state: Mapping[str, Any],
        t: float | None = None,
        scene_index: int | None = None,
        page_index: int | None = None,
    ) -> dict[str, Any]:
        data = state_to_config_data(state)
        config = load_config_data(data, self.config_path)
        pages = scene_pages_state(config)
        if scene_index is not None or page_index is not None:
            selected_scene = max(0, scene_index or 0)
            selected_page = max(0, page_index or 0)
            page = find_page_state(pages, selected_scene, selected_page)
            render_preview_page(config, self.preview_path, selected_scene, selected_page)
            preview_payload: dict[str, Any] = {
                "sceneIndex": selected_scene,
                "pageIndex": selected_page,
                "page": page,
            }
        else:
            preview_t = preview_time_for_config(config, t)
            render_preview_frame(config, self.preview_path, t=preview_t)
            preview_payload = {"time": preview_t}
        return {
            "path": str(self.preview_path),
            "url": self.media_url(self.preview_path),
            "pages": pages,
            **preview_payload,
            "updatedAt": time.time(),
        }

    def render_state(self, state: Mapping[str, Any], output_path: str | None = None) -> dict[str, Any]:
        data = state_to_config_data(state)
        config = load_config_data(data, self.config_path)
        output = self.resolve_path(output_path) if output_path else self.output_path
        render_video(config, output)
        self.output_path = output
        return {
            "path": str(output),
            "url": self.media_url(output),
            "updatedAt": time.time(),
        }

    def start_render_state(self, state: Mapping[str, Any], output_path: str | None = None) -> dict[str, Any]:
        data = state_to_config_data(state)
        config = load_config_data(data, self.config_path)
        output = self.resolve_path(output_path) if output_path else self.output_path
        job = RenderJob(id=uuid.uuid4().hex, output_path=output)
        with self.render_jobs_lock:
            self.render_jobs[job.id] = job
        thread = threading.Thread(target=self._run_render_job, args=(job, config, output), daemon=True)
        thread.start()
        return job.snapshot()

    def render_job_status(self, job_id: str) -> dict[str, Any]:
        with self.render_jobs_lock:
            job = self.render_jobs.get(job_id)
        if not job:
            raise WebError(HTTPStatus.NOT_FOUND, "Render job not found.")
        return job.snapshot()

    def auto_photo_wall_transforms(
        self,
        state: Mapping[str, Any],
        scene_index: int,
        page_index: int,
    ) -> dict[str, Any]:
        config, pages, target_page = self._page_from_state(state, scene_index, page_index)
        if target_page.layout != "photo_wall":
            raise WebError(HTTPStatus.BAD_REQUEST, "Auto transforms are only available for photo_wall layout.")

        elements = self._photo_wall_elements(config, pages, target_page, transform_mode="size")
        return {
            "sceneIndex": scene_index,
            "pageIndex": page_index,
            "transforms": [
                {
                    "photoIndex": element["photoIndex"],
                    "transform": self._auto_transform_payload(
                        target_page.photos[index].transform,
                        target_page.wall.card_width,
                        element,
                    ),
                }
                for index, element in enumerate(elements)
            ],
        }

    def photo_wall_page_elements(
        self,
        state: Mapping[str, Any],
        scene_index: int,
        page_index: int,
    ) -> dict[str, Any]:
        config, pages, target_page = self._page_from_state(state, scene_index, page_index)
        canvas_w, canvas_h = config.video.resolution
        payload: dict[str, Any] = {
            "sceneIndex": scene_index,
            "pageIndex": page_index,
            "canvas": {"width": canvas_w, "height": canvas_h},
            "editable": target_page.layout == "photo_wall",
            "photos": [],
        }
        if target_page.layout != "photo_wall":
            payload["reason"] = "只有照片墙布局支持图形编辑。"
            return payload

        payload["wall"] = {
            "max_per_page": target_page.wall.max_per_page,
            "rotation": target_page.wall.rotation,
            "overlap": target_page.wall.overlap,
            "style": target_page.wall.style,
            "card_width": target_page.wall.card_width,
            "spread": target_page.wall.spread,
            "caption_safe": target_page.wall.caption_safe,
            "randomness": target_page.wall.randomness,
            "random_seed": target_page.wall.random_seed,
        }
        payload["photos"] = self._photo_wall_elements(config, pages, target_page, transform_mode="current")
        return payload

    def _page_from_state(
        self,
        state: Mapping[str, Any],
        scene_index: int,
        page_index: int,
    ) -> tuple[ProjectConfig, tuple[ScenePage, ...], ScenePage]:
        data = state_to_config_data(state)
        config = load_config_data(data, self.config_path)
        pages = build_scene_pages(config)
        target_page = next(
            (
                page
                for page in pages
                if page.scene_index == scene_index and page.page_index == page_index
            ),
            None,
        )
        if target_page is None:
            raise WebError(HTTPStatus.BAD_REQUEST, f"Preview page does not exist: scene {scene_index + 1}, page {page_index + 1}")
        return config, pages, target_page

    def _photo_wall_elements(
        self,
        config: ProjectConfig,
        pages: tuple[ScenePage, ...],
        page: ScenePage,
        transform_mode: Literal["current", "size", "none"],
    ) -> list[dict[str, Any]]:
        canvas_w, canvas_h = config.video.resolution
        photo_sizes = []
        for photo in page.photos:
            with Image.open(photo.path) as image:
                photo_sizes.append(ImageOps.exif_transpose(image).size)
        if transform_mode == "current":
            transforms = [photo.transform for photo in page.photos]
        elif transform_mode == "size":
            transforms = [self._size_transform(photo.transform) for photo in page.photos]
        elif transform_mode == "none":
            transforms = [None] * len(page.photos)
        else:
            raise ValueError(f"Unsupported photo wall transform mode: {transform_mode}")
        slots = photo_wall_layout(
            len(page.photos),
            config.video.resolution,
            photo_sizes,
            transforms=transforms,
            rotation_limit=page.wall.rotation,
            overlap=page.wall.overlap,
            style=page.wall.style,
            card_width=page.wall.card_width,
            spread=page.wall.spread,
            caption_safe=page.wall.caption_safe,
            randomness=page.wall.randomness,
            random_seed=page.wall.random_seed,
        )
        photo_offset = sum(
            len(candidate.photos)
            for candidate in pages
            if candidate.scene_index == page.scene_index and candidate.page_index < page.page_index
        )
        elements: list[dict[str, Any]] = []
        for index, (photo, slot) in enumerate(zip(page.photos, slots)):
            photo_payload = photo_state(photo.path, config.base_dir)
            elements.append(
                {
                    **photo_payload,
                    "photoIndex": photo_offset + index,
                    "caption": photo.caption or "",
                    "time": photo.time or "",
                    "fit": slot.fit,
                    "frame": slot.frame,
                    "x": round((slot.rect.x + slot.rect.width / 2) / canvas_w, 4),
                    "y": round((slot.rect.y + slot.rect.height / 2) / canvas_h, 4),
                    "width": round(slot.rect.width / canvas_w, 4),
                    "height": round(slot.rect.height / canvas_h, 4),
                    "rotation": round(slot.rotation, 2),
                    "z_index": slot.z_index,
                }
            )
        return elements

    @staticmethod
    def _size_transform(transform: PhotoTransform | None) -> PhotoTransform | None:
        if transform is None:
            return None
        if transform.width is None and transform.height is None and transform.fit is None:
            return None
        return PhotoTransform(width=transform.width, height=transform.height, fit=transform.fit)

    @staticmethod
    def _auto_transform_payload(
        existing: PhotoTransform | None,
        card_width: float | None,
        element: Mapping[str, Any],
    ) -> dict[str, Any]:
        width = existing.width if existing and existing.width is not None else card_width
        payload = {
            "x": element["x"],
            "y": element["y"],
            "width": width if width is not None else element["width"],
            "rotation": element["rotation"],
            "fit": existing.fit if existing and existing.fit is not None else element["fit"],
            "z_index": element["z_index"],
        }
        if existing and existing.height is not None:
            payload["height"] = existing.height
        return payload

    def _run_render_job(self, job: RenderJob, config: ProjectConfig, output: Path) -> None:
        try:
            job.update(progress=0.01, message="开始渲染", status="running")
            render_video(config, output, progress_callback=lambda progress, message: job.update(progress, message, "running"))
            self.output_path = output
            job.complete(self.media_url(output))
        except Exception as exc:  # pragma: no cover - exercised by the running server.
            job.fail(str(exc))

    def list_images(self, directory: str) -> list[dict[str, Any]]:
        path = self.resolve_path(directory)
        if not path.exists() or not path.is_dir():
            raise WebError(HTTPStatus.BAD_REQUEST, f"Directory does not exist: {path}")
        images = sorted(child for child in path.iterdir() if child.is_file() and child.suffix.lower() in IMAGE_EXTENSIONS)
        return [photo_state(child, self.base_dir) for child in images]

    def choose_file(self, purpose: str = "photo") -> dict[str, Any]:
        path = open_file_dialog(purpose)
        if not path:
            return {"path": "", "resolvedPath": "", "mediaUrl": ""}
        if purpose == "photo":
            return photo_state(path, self.base_dir)
        return selected_path_state(path, self.base_dir)

    def choose_directory(self) -> dict[str, Any]:
        path = open_directory_dialog()
        if not path:
            return {"path": "", "resolvedPath": ""}
        return selected_path_state(path, self.base_dir)

    def resolve_path(self, value: str | None) -> Path:
        if not value:
            raise WebError(HTTPStatus.BAD_REQUEST, "Path is required.")
        path = Path(unquote(value)).expanduser()
        if not path.is_absolute():
            path = self.base_dir / path
        return path.resolve()

    def media_url(self, path: str | Path) -> str:
        return f"/media?path={quote(str(Path(path).resolve()))}&v={int(time.time() * 1000)}"


def run_web_ui(
    input_path: str | Path,
    output_path: str | Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = False,
) -> None:
    workspace = WebWorkspace(Path(input_path), Path(output_path) if output_path else None)
    handler_type = make_handler(workspace)
    server = ThreadingHTTPServer((host, port), handler_type)
    url = f"http://{host}:{server.server_port}"
    print(f"Photo Memory Video web UI: {url}")
    print(f"Editing config: {workspace.config_path}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping web UI.")
    finally:
        server.server_close()


def make_handler(workspace: WebWorkspace) -> type[BaseHTTPRequestHandler]:
    class PhotoMemoryRequestHandler(BaseHTTPRequestHandler):
        server_version = "PhotoMemoryVideoWeb/0.1"

        def do_GET(self) -> None:
            self.handle_request("GET")

        def do_POST(self) -> None:
            self.handle_request("POST")

        def log_message(self, format: str, *args: Any) -> None:
            return

        def handle_request(self, method: str) -> None:
            try:
                parsed = urlparse(self.path)
                if method == "GET" and parsed.path == "/":
                    self.send_static_file(STATIC_DIR / "index.html")
                elif method == "GET" and parsed.path.startswith("/static/"):
                    self.send_static_file(STATIC_DIR / parsed.path.removeprefix("/static/"))
                elif method == "GET" and parsed.path == "/api/project":
                    self.send_json(workspace.load_state())
                elif method == "GET" and parsed.path == "/media":
                    query = parse_qs(parsed.query)
                    self.send_media(query.get("path", [""])[0])
                elif method == "POST" and parsed.path == "/api/project":
                    body = self.read_json()
                    self.send_json({"ok": True, "state": workspace.save_state(body.get("state") or body)})
                elif method == "POST" and parsed.path == "/api/preview":
                    body = self.read_json()
                    requested_time = None if body.get("time") is None else parse_float(body.get("time"), "time")
                    requested_scene = None if body.get("sceneIndex") is None else parse_int(body.get("sceneIndex"), "sceneIndex", allow_zero=True)
                    requested_page = None if body.get("pageIndex") is None else parse_int(body.get("pageIndex"), "pageIndex", allow_zero=True)
                    self.send_json(
                        {
                            "ok": True,
                            "preview": workspace.preview_state(
                                body.get("state") or body,
                                requested_time,
                                requested_scene,
                                requested_page,
                            ),
                        }
                    )
                elif method == "POST" and parsed.path == "/api/render":
                    body = self.read_json()
                    self.send_json({"ok": True, "video": workspace.render_state(body.get("state") or body, optional_text(body.get("outputPath")))})
                elif method == "POST" and parsed.path == "/api/render/start":
                    body = self.read_json()
                    self.send_json({"ok": True, "job": workspace.start_render_state(body.get("state") or body, optional_text(body.get("outputPath")))})
                elif method == "GET" and parsed.path == "/api/render/status":
                    query = parse_qs(parsed.query)
                    self.send_json({"ok": True, "job": workspace.render_job_status(query.get("id", [""])[0])})
                elif method == "POST" and parsed.path == "/api/layout/auto-transform":
                    body = self.read_json()
                    requested_scene = parse_int(body.get("sceneIndex"), "sceneIndex", allow_zero=True)
                    requested_page = parse_int(body.get("pageIndex"), "pageIndex", allow_zero=True)
                    self.send_json(
                        {
                            "ok": True,
                            "layout": workspace.auto_photo_wall_transforms(
                                body.get("state") or body,
                                requested_scene,
                                requested_page,
                            ),
                        }
                    )
                elif method == "POST" and parsed.path == "/api/layout/page-elements":
                    body = self.read_json()
                    requested_scene = parse_int(body.get("sceneIndex"), "sceneIndex", allow_zero=True)
                    requested_page = parse_int(body.get("pageIndex"), "pageIndex", allow_zero=True)
                    self.send_json(
                        {
                            "ok": True,
                            "layout": workspace.photo_wall_page_elements(
                                body.get("state") or body,
                                requested_scene,
                                requested_page,
                            ),
                        }
                    )
                elif method == "POST" and parsed.path == "/api/list-images":
                    body = self.read_json()
                    self.send_json({"ok": True, "photos": workspace.list_images(optional_text(body.get("directory")) or "")})
                elif method == "POST" and parsed.path == "/api/choose-file":
                    body = self.read_json()
                    self.send_json({"ok": True, "selection": workspace.choose_file(optional_text(body.get("purpose")) or "photo")})
                elif method == "POST" and parsed.path == "/api/choose-directory":
                    self.send_json({"ok": True, "selection": workspace.choose_directory()})
                else:
                    raise WebError(HTTPStatus.NOT_FOUND, "Not found.")
            except WebError as exc:
                self.send_error_json(exc.status, exc.message)
            except (ConfigError, RuntimeError, ValueError, OSError) as exc:
                self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))

        def read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return {}
            try:
                payload = self.rfile.read(length).decode("utf-8")
                loaded = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise WebError(HTTPStatus.BAD_REQUEST, "Invalid JSON body.") from exc
            if not isinstance(loaded, dict):
                raise WebError(HTTPStatus.BAD_REQUEST, "JSON body must be an object.")
            return loaded

        def send_json(self, payload: Mapping[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def send_error_json(self, status: HTTPStatus, message: str) -> None:
            self.send_json({"ok": False, "error": message}, status=status)

        def send_static_file(self, path: Path) -> None:
            root = STATIC_DIR.resolve()
            target = path.resolve()
            if not target.is_file() or root not in target.parents and target != root:
                raise WebError(HTTPStatus.NOT_FOUND, "Static file not found.")
            self.send_file(target)

        def send_media(self, raw_path: str) -> None:
            path = workspace.resolve_path(raw_path)
            if not path.is_file():
                raise WebError(HTTPStatus.NOT_FOUND, "Media file not found.")
            if path.suffix.lower() not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
                raise WebError(HTTPStatus.BAD_REQUEST, "Unsupported media type.")
            self.send_file(path)

        def send_file(self, path: Path) -> None:
            content = path.read_bytes()
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    return PhotoMemoryRequestHandler
