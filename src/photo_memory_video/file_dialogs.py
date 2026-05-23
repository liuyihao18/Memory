from __future__ import annotations

from pathlib import Path


def open_file_dialog(purpose: str) -> Path | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:
        raise RuntimeError(f"Cannot open file dialog: {exc}") from exc

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    root.update()
    try:
        if purpose == "output":
            selected = filedialog.asksaveasfilename(
                title="选择输出视频",
                defaultextension=".mp4",
                filetypes=[("MP4 video", "*.mp4"), ("All files", "*.*")],
            )
        else:
            selected = filedialog.askopenfilename(
                title="选择照片",
                filetypes=[
                    ("Image files", "*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff"),
                    ("All files", "*.*"),
                ],
            )
    finally:
        root.destroy()

    return Path(selected).resolve() if selected else None


def open_directory_dialog() -> Path | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:
        raise RuntimeError(f"Cannot open directory dialog: {exc}") from exc

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    root.update()
    try:
        selected = filedialog.askdirectory(title="选择照片目录")
    finally:
        root.destroy()

    return Path(selected).resolve() if selected else None
