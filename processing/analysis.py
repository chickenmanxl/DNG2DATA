# Main data extraction script
import numpy as np


def compute_avg_rgb(img: np.ndarray, x0: int, y0: int, x1: int, y1: int):
    """
    img: HxWx3, uint8/uint16
    ROI is [y0:y1, x0:x1]
    Returns (R, G, B) as floats or None if empty.
    """
    if img.ndim != 3 or img.shape[2] != 3:
        raise ValueError("Expected HxWx3 image")
    x0, x1 = sorted((int(x0), int(x1)))
    y0, y1 = sorted((int(y0), int(y1)))
    if x1 <= x0 or y1 <= y0:
        return None

    roi = img[y0:y1, x0:x1, :]
    if roi.size == 0:
        return None

    # Use float64 for precision regardless of bit depth
    mean = roi.reshape(-1, 3).mean(axis=0, dtype=np.float64)
    # Return as RGB order
    return float(mean[0]), float(mean[1]), float(mean[2])
