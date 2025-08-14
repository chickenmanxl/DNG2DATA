# Utilities for processing a time series of DNG images
from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, Iterable, List, Sequence

import pandas as pd
import piexif

from .dng_loader import load_dng
from .analysis import measure_regions
from .regions import Region, load_template


__all__ = ["collect_time_series"]


def _get_image_timestamp(path: str) -> datetime:
    """Return the capture timestamp for a DNG image.

    Attempts to read the ``DateTimeOriginal`` EXIF tag; if unavailable,
    falls back to the file's modification time.
    """
    try:
        exif = piexif.load(path)
        exif_ifd = exif.get("Exif", {}) or {}
        dt = (
            exif_ifd.get(piexif.ExifIFD.DateTimeOriginal)
            or exif_ifd.get(piexif.ExifIFD.DateTimeDigitized)
        )
        if dt:
            if isinstance(dt, bytes):
                dt = dt.decode("utf-8", errors="ignore")
            return datetime.strptime(dt, "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    return datetime.fromtimestamp(os.path.getmtime(path))


def collect_time_series(
    folder: str,
    template: str | Sequence[Region],
    excel_path: str,
    load_settings: Dict | None = None,
) -> pd.DataFrame:
    """Process a folder of DNG images and export region data to Excel.

    Parameters
    ----------
    folder:
        Path containing the DNG images to process.
    template:
        Either a path to a region template JSON file or a sequence of
        :class:`Region` objects.
    excel_path:
        Output path for the generated Excel file.
    load_settings:
        Optional dictionary of keyword arguments forwarded to
        :func:`load_dng` to ensure consistent processing across images.

    Returns
    -------
    pandas.DataFrame
        Data table containing measurements for all images.
    """

    if isinstance(template, str):
        regions = load_template(template)
    else:
        regions = list(template)
    load_settings = dict(load_settings or {})

    # Collect and sort image paths for reproducibility
    paths = [
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if f.lower().endswith(".dng")
    ]
    paths.sort()
    if not paths:
        raise FileNotFoundError(f"No DNG images found in {folder!r}")

    frames: List[pd.DataFrame] = []
    for p in paths:
        full_rgb, _, _ = load_dng(p, **load_settings)
        df = measure_regions(full_rgb, regions)
        ts = _get_image_timestamp(p)
        df.insert(0, "Timestamp", ts)
        df.insert(0, "Image", os.path.basename(p))
        frames.append(df)

    result = pd.concat(frames, ignore_index=True)
    result.to_excel(excel_path, index=False)
    return result