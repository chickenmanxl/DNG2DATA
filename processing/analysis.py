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