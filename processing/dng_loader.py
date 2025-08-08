# Loads and converts DNGs
import rawpy
import numpy as np
from PIL import Image


def load_dng(path, max_w=1600, max_h=1000, output_bits=8, use_camera_wb=True):
    """
    Returns:
        full_rgb  : numpy array (H, W, 3), dtype uint8 or uint16
        display_pil: PIL Image (scaled for GUI display, RGB)
        scale     : display_px = full_px * scale
    """
    if output_bits not in (8, 16):
        raise ValueError("output_bits must be 8 or 16")

    with rawpy.imread(path) as raw:
        rgb = raw.postprocess(
            use_camera_wb=use_camera_wb,
            output_bps=output_bits,
            no_auto_bright=True,
            gamma=(1, 1)  # linear; keeps math honest for averages
        )

    full_rgb = np.asarray(rgb)  # HxWx3, dtype uint8/uint16

    # Create display image (downscale to fit while preserving aspect)
    h, w, _ = full_rgb.shape
    scale = min(max_w / w, max_h / h, 1.0)
    disp_w = int(w * scale)
    disp_h = int(h * scale)

    pil_full = Image.fromarray(full_rgb.astype(np.uint8 if output_bits == 8 else np.uint16), mode="RGB")
    # Use high-quality downscale
    if scale < 1.0:
        display_pil = pil_full.resize((disp_w, disp_h), resample=Image.LANCZOS)
    else:
        display_pil = pil_full

    return full_rgb, display_pil.convert("RGB"), scale
