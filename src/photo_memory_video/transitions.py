from __future__ import annotations

import numpy as np


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def smoothstep(value: float) -> float:
    value = clamp01(value)
    return value * value * (3 - 2 * value)


def blend_frames(a: np.ndarray, b: np.ndarray, alpha: float) -> np.ndarray:
    alpha = smoothstep(alpha)
    return (a.astype(np.float32) * (1.0 - alpha) + b.astype(np.float32) * alpha).clip(0, 255).astype(np.uint8)


def fade_to_color(frame: np.ndarray, color: tuple[int, int, int], alpha: float) -> np.ndarray:
    alpha = smoothstep(alpha)
    color_frame = np.empty_like(frame)
    color_frame[:, :] = color
    return blend_frames(frame, color_frame, alpha)
