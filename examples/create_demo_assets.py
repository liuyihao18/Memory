from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
PHOTO_DIR = ROOT / "photos"


def find_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/Deng.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def make_demo_photo(path: Path, size: tuple[int, int], title: str, colors: tuple[str, str]) -> None:
    image = Image.new("RGB", size, colors[0])
    draw = ImageDraw.Draw(image)
    for y in range(size[1]):
        t = y / max(size[1] - 1, 1)
        top = tuple(int(colors[0].lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
        bottom = tuple(int(colors[1].lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
        color = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        draw.line([(0, y), (size[0], y)], fill=color)

    font = find_font(max(size) // 16)
    small_font = find_font(max(size) // 32)
    draw.rectangle((0, size[1] * 0.68, size[0], size[1]), fill=(0, 0, 0, 76))
    draw.text((size[0] * 0.08, size[1] * 0.72), title, font=font, fill=(255, 248, 235))
    draw.text((size[0] * 0.08, size[1] * 0.84), "demo photo", font=small_font, fill=(245, 226, 198))
    image.save(path, quality=92)


def main() -> None:
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    specs = [
        ("001.jpg", (1600, 1000), "第一次班会", ("#6f7f85", "#c9a678")),
        ("002.jpg", (1200, 1600), "社团活动", ("#49545a", "#b78d73")),
        ("003.jpg", (1600, 900), "操场傍晚", ("#445f73", "#d49b72")),
        ("004.jpg", (1400, 1000), "毕业前夜", ("#2f3543", "#8b6f76")),
        ("005.jpg", (1000, 1400), "图书馆", ("#63594f", "#d0b389")),
        ("006.jpg", (1600, 1100), "夏天行李箱", ("#596b52", "#d1b46a")),
    ]
    for filename, size, title, colors in specs:
        make_demo_photo(PHOTO_DIR / filename, size, title, colors)
    print(f"created {len(specs)} demo photos in {PHOTO_DIR}")


if __name__ == "__main__":
    main()
