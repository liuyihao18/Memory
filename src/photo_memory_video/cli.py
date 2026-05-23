from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config_loader import ConfigError, load_config
from .render import render_preview_frame, render_video
from .web import run_web_ui


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="photo-memory-video", description="Generate warm memory videos from YAML.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    render_parser = subparsers.add_parser("render", help="Render a video from a YAML or JSON config.")
    render_parser.add_argument("--input", "-i", required=True, help="Path to YAML or JSON config.")
    render_parser.add_argument("--output", "-o", required=True, help="Output MP4 path.")
    render_parser.add_argument(
        "--preview-frame",
        help="Render a single preview frame PNG instead of an MP4. Useful for checking layout quickly.",
    )

    web_parser = subparsers.add_parser("web", help="Start the local browser UI for arranging a video.")
    web_parser.add_argument("--input", "-i", required=True, help="Path to YAML or JSON config.")
    web_parser.add_argument("--output", "-o", help="Default output MP4 path.")
    web_parser.add_argument("--host", default="127.0.0.1", help="Bind host. Defaults to 127.0.0.1.")
    web_parser.add_argument("--port", type=int, default=8765, help="Bind port. Defaults to 8765.")
    web_parser.add_argument("--open-browser", action="store_true", help="Open the UI in the default browser.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "render":
        try:
            config = load_config(Path(args.input))
            if args.preview_frame:
                preview = render_preview_frame(config, Path(args.preview_frame))
                print(f"Preview frame written to {preview}")
            else:
                output = render_video(config, Path(args.output))
                print(f"Video written to {output}")
            return 0
        except (ConfigError, RuntimeError, OSError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    if args.command == "web":
        try:
            run_web_ui(
                input_path=Path(args.input),
                output_path=Path(args.output) if args.output else None,
                host=args.host,
                port=args.port,
                open_browser=args.open_browser,
            )
            return 0
        except (ConfigError, RuntimeError, OSError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    parser.print_help()
    return 1
