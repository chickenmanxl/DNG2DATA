# Loads and converts DNGs
import rawpy
import numpy as np
from PIL import Image


_DEMOSAIC_MAP = {
    "AHD (default)": rawpy.DemosaicAlgorithm.AHD,
    "AMaZE": rawpy.DemosaicAlgorithm.AMAZE,
    "DCB": rawpy.DemosaicAlgorithm.DCB,
    "LMMSE": rawpy.DemosaicAlgorithm.LMMSE,
    "VNG": rawpy.DemosaicAlgorithm.VNG,
    "PPG": rawpy.DemosaicAlgorithm.PPG,
}


def _resolve_wb_kwargs(wb_mode: str, user_wb_rgb):
    """
    wb_mode: "Camera", "Auto", "Manual"
    user_wb_rgb: tuple/list of 3 floats (R,G,B) if manual
    Returns kwargs for raw.postprocess: use_camera_wb, use_auto_wb, user_wb
    """
    wb_mode = (wb_mode or "Camera").strip().lower()
    if wb_mode == "camera":
        return dict(use_camera_wb=True, use_auto_wb=False)
    if wb_mode == "auto":
        return dict(use_camera_wb=False, use_auto_wb=True)
    if wb_mode == "manual":
        if not user_wb_rgb or len(user_wb_rgb) < 3:
            # fallback to neutral gains if not provided
            user_wb_rgb = (1.0, 1.0, 1.0)
        r, g, b = map(float, user_wb_rgb[:3])
        # rawpy expects 4-tuple (R, G1, B, G2). Use same G for both.
        return dict(use_camera_wb=False, use_auto_wb=False, user_wb=(r, g, b, g))
    # default
    return dict(use_camera_wb=True, use_auto_wb=False)


def _resolve_gamma(gamma_mode: str, gamma_tuple):
    """
    gamma_mode: "Linear", "sRGB-ish", "Manual"
    gamma_tuple: (power, slope)
    """
    gm = (gamma_mode or "Linear").strip().lower()
    if gm == "linear":
        return (1.0, 1.0)
    if gm in ("srgb-ish", "srgb"):
        # rawpy's typical default is close to (2.222, 4.5)
        return (2.222, 4.5)
    if gm == "manual":
        if not gamma_tuple or len(gamma_tuple) < 2:
            return (1.0, 1.0)
        a, b = map(float, gamma_tuple[:2])
        return (a, b)
    return (1.0, 1.0)


def load_dng(
    path,
    max_w=1600,
    max_h=1000,
    output_bits=8,                # 8 or 16
    wb_mode="Camera",             # "Camera" | "Auto" | "Manual"
    user_wb_rgb=(1.0, 1.0, 1.0),  # used when wb_mode == "Manual"
    gamma_mode="Linear",          # "Linear" | "sRGB-ish" | "Manual"
    gamma_tuple=(1.0, 1.0),       # power, slope (Manual)
    auto_bright=False,            # False preserves linearity
    demosaic_algo="AHD (default)" # per _DEMOSAIC_MAP keys
):
    """
    Returns:
        full_rgb    : numpy array (H, W, 3), dtype uint8 or uint16
        display_pil : PIL Image (scaled preview, RGB 8-bit)
        scale       : float (display_px = full_px * scale)
    """
    if output_bits not in (8, 16):
        raise ValueError("output_bits must be 8 or 16")

    demosaic = _DEMOSAIC_MAP.get(demosaic_algo, rawpy.DemosaicAlgorithm.AHD)
    wb_kwargs = _resolve_wb_kwargs(wb_mode, user_wb_rgb)
    gamma = _resolve_gamma(gamma_mode, gamma_tuple)

    with rawpy.imread(path) as raw:
        rgb = raw.postprocess(
            output_bps=output_bits,
            demosaic_algorithm=demosaic,
            no_auto_bright=not auto_bright,
            gamma=gamma,
            **wb_kwargs
        )

    full_rgb = np.asarray(rgb)  # HxWx3

    # Build preview (always 8-bit for Tk)
    h, w, _ = full_rgb.shape
    scale = min(max_w / w, max_h / h, 1.0)
    disp_w = int(w * scale)
    disp_h = int(h * scale)

    # If 16-bit, convert to 8-bit for preview
    # This applys only to the display image, not the real data
    if full_rgb.dtype == np.uint16:
        preview = (full_rgb / 257).astype(np.uint8)  # 65535->255 mapping
    else:
        preview = full_rgb

    pil_full = Image.fromarray(preview, mode="RGB")
    display_pil = pil_full.resize((disp_w, disp_h), resample=Image.LANCZOS) if scale < 1.0 else pil_full

    return full_rgb, display_pil.convert("RGB"), scale
