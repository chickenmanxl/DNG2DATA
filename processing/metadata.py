# Extracts image metadata
import piexif

def _fmt_rational(val):
    # piexif returns (num, den) for rationals
    try:
        num, den = val
        return f"{num}/{den}" if den else str(num)
    except Exception:
        return str(val)

def get_metadata_string(path: str) -> str:
    """
    Lightweight EXIF summary (Exposure, ISO, FNumber, Make/Model if present).
    """
    try:
        exif = piexif.load(path)
        exif_ifd = exif.get("Exif", {})
        zeroth = exif.get("0th", {})
        # Common fields
        exposure = exif_ifd.get(piexif.ExifIFD.ExposureTime, None)
        iso = exif_ifd.get(piexif.ExifIFD.ISOSpeedRatings, None)
        fnum = exif_ifd.get(piexif.ExifIFD.FNumber, None)
        make = zeroth.get(piexif.ImageIFD.Make, b"").decode(errors="ignore")
        model = zeroth.get(piexif.ImageIFD.Model, b"").decode(errors="ignore")

        parts = []
        if exposure is not None:
            parts.append(f"Exposure: {_fmt_rational(exposure)} s")
        if iso is not None:
            parts.append(f"ISO: {iso}")
        if fnum is not None:
            parts.append(f"FNumber: f/{_fmt_rational(fnum)}")
        cam = " ".join(x for x in [make, model] if x).strip()
        if cam:
            parts.append(f"Camera: {cam}")
        return " | ".join(parts) if parts else "No EXIF found"
    except Exception as e:
        return f"Metadata error: {e}"
