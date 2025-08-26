# Main data extraction script
import numpy as np
from typing import List
import json
from PIL import Image, ImageDraw
import pandas as pd
from .regions import Region

def _polygon_mask(points, shape):
    """Create a boolean mask for a polygon."""
    h, w = shape
    img = Image.new("1", (w, h), 0)
    draw = ImageDraw.Draw(img)
    draw.polygon(points, outline=1, fill=1)
    return np.array(img, dtype=bool)


def compute_region_stats(img: np.ndarray, region: Region):
    """Compute mean and std RGB for a Region."""
    if img.ndim != 3 or img.shape[2] != 3:
        raise ValueError("Expected HxWx3 image")

    if region.shape == "rect":
        x = int(region.params.get("x", 0))
        y = int(region.params.get("y", 0))
        w = int(region.params.get("w", 0))
        h = int(region.params.get("h", 0))
        roi = img[y:y + h, x:x + w, :]
        flat = roi.reshape(-1, 3)
    elif region.shape == "circle":
        cx = int(region.params.get("cx", 0))
        cy = int(region.params.get("cy", 0))
        r = int(region.params.get("r", 0))
        y_indices, x_indices = np.ogrid[:img.shape[0], :img.shape[1]]
        mask = (x_indices - cx) ** 2 + (y_indices - cy) ** 2 <= r ** 2
        flat = img[mask]
    elif region.shape == "polygon":
        points = [(int(p[0]), int(p[1])) for p in region.params.get("points", [])]
        mask = _polygon_mask(points, img.shape[:2])
        flat = img[mask]
    else:
        raise ValueError(f"Unsupported shape: {region.shape}")

    if flat.size == 0:
        return None

    mean = flat.mean(axis=0, dtype=np.float64)
    std = flat.std(axis=0, dtype=np.float64)
    return {
        "ID": region.id,
        "Shape Type": region.shape,
        "Parameters": json.dumps(region.params),
        "Mean R": float(mean[0]),
        "Mean G": float(mean[1]),
        "Mean B": float(mean[2]),
        "Std R": float(std[0]),
        "Std G": float(std[1]),
        "Std B": float(std[2]),
    }

def extract_raw_region(img: np.ndarray, region: Region):
    """Extract raw Bayer values for ``region``.

    Returns a tuple ``(data, mask)`` where ``data`` is a view of the
    raw image covering the region and ``mask`` indicates which elements
    belong to the region (``None`` for rectangular regions).  Elements
    outside the mask are left in place so callers can display or ignore
    them as needed.
    """
    if region.shape == "rect":
        x = int(region.params.get("x", 0))
        y = int(region.params.get("y", 0))
        w = int(region.params.get("w", 0))
        h = int(region.params.get("h", 0))
        return img[y:y + h, x:x + w], None
    elif region.shape == "circle":
        cx = int(region.params.get("cx", 0))
        cy = int(region.params.get("cy", 0))
        r = int(region.params.get("r", 0))
        y0 = max(cy - r, 0)
        y1 = min(cy + r + 1, img.shape[0])
        x0 = max(cx - r, 0)
        x1 = min(cx + r + 1, img.shape[1])
        sub = img[y0:y1, x0:x1]
        yy, xx = np.ogrid[y0:y1, x0:x1]
        mask = (xx - cx) ** 2 + (yy - cy) ** 2 <= r ** 2
        return sub, mask
    elif region.shape == "polygon":
        points = [(int(p[0]), int(p[1])) for p in region.params.get("points", [])]
        if not points:
            return np.array([]), None
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        x0 = max(min(xs), 0)
        x1 = min(max(xs) + 1, img.shape[1])
        y0 = max(min(ys), 0)
        y1 = min(max(ys) + 1, img.shape[0])
        sub = img[y0:y1, x0:x1]
        shifted = [(px - x0, py - y0) for px, py in points]
        mask = _polygon_mask(shifted, sub.shape)
        return sub, mask
    else:
        raise ValueError(f"Unsupported shape: {region.shape}")
    
def measure_regions(img: np.ndarray, regions: List[Region]) -> pd.DataFrame:
    """Measure multiple regions and return a DataFrame."""
    rows = []
    for reg in regions:
        stats = compute_region_stats(img, reg)
        if stats:
            rows.append(stats)
    columns = [
        "ID",
        "Shape Type",
        "Parameters",
        "Mean R",
        "Mean G",
        "Mean B",
        "Std R",
        "Std G",
        "Std B",
    ]
    return pd.DataFrame(rows, columns=columns)