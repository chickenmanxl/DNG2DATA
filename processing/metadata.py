# processing/metadata.py
"""
Robust metadata reader for DNG files.

Strategy:
1) EXIF (piexif)
2) XMP from TIFF tag 700 (tifffile) — supports element and attribute forms
3) Optional exiftool fallback for stubborn vendor/MakerNotes fields

Fields returned:
  - CameraMake
  - CameraModel
  - ExposureTime (e.g., "1/90 s" or "0.01111 s")
  - FNumber (e.g., "f/1.7")
  - ISO (int)
"""

from __future__ import annotations
import re
import shutil
import os
import subprocess
import piexif
from typing import Any, Dict, Optional
from xml.etree import ElementTree as ET

def _find_exiftool() -> str | None:
    # 1) Respect explicit env var
    cand = os.environ.get("EXIFTOOL_PATH")
    if cand and os.path.isfile(cand):
        return cand

    # 2) PATH search (common names)
    for name in ("exiftool", "exiftool.exe", "exiftool(-k).exe"):
        p = shutil.which(name)
        if p:
            return p

    # 3) Common Windows locations (tweak if you installed elsewhere)
    guesses = [
        r"C:\Windows\exiftool.exe",
        r"C:\Windows\exiftool(-k).exe",
        r"C:\Program Files\exiftool\exiftool.exe",
        r"C:\Program Files (x86)\exiftool\exiftool.exe",
        r"C:\ProgramData\chocolatey\bin\exiftool.exe",
    ]
    for g in guesses:
        if os.path.isfile(g):
            return g
    return None



# =========================
# Formatting / conversions
# =========================
def _rational_to_float(v):
    try:
        if isinstance(v, (list, tuple)) and len(v) == 2:
            n, d = v
            return float(n) / float(d) if d else float(n)
        return float(v)
    except Exception:
        return None


def _format_exposure(v) -> Optional[str]:
    f = _rational_to_float(v)
    if f is None or f <= 0:
        return None
    if f >= 1.0:
        return f"{f:.3f} s"
    inv = round(1.0 / f)
    # Prefer nice reciprocal if close
    if abs((1.0 / inv) - f) < 1e-4:
        return f"1/{inv} s"
    return f"{f:.5f} s"


def _format_fnumber(v) -> Optional[str]:
    f = _rational_to_float(v)
    return f"f/{f:.1f}" if f and f > 0 else None


def _pick_text(v) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, (bytes, bytearray)):
        s = v.decode(errors="ignore").strip()
        return s if s else None
    s = str(v).strip()
    return s if s else None


def _coerce_int(x) -> Optional[int]:
    try:
        if isinstance(x, (list, tuple)) and x:
            x = x[0]
        return int(float(x))
    except Exception:
        return None


# =========================
# EXIF (piexif) helpers
# =========================
def _exif_read(path: str) -> Dict[str, Any]:
    out = {
        "CameraMake": None,
        "CameraModel": None,
        "ExposureTime": None,
        "FNumber": None,
        "ISO": None,
    }
    if piexif is None:
        return out

    try:
        exif = piexif.load(path)
        zeroth = exif.get("0th", {}) or {}
        exif_ifd = exif.get("Exif", {}) or {}
        first = exif.get("1st", {}) or {}
        ifds = (exif_ifd, zeroth, first)

        # Camera
        out["CameraMake"] = _pick_text(
            zeroth.get(piexif.ImageIFD.Make) or first.get(piexif.ImageIFD.Make)
        )
        out["CameraModel"] = _pick_text(
            zeroth.get(piexif.ImageIFD.Model) or first.get(piexif.ImageIFD.Model)
        )

        # Exposure
        exp_val = exif_ifd.get(piexif.ExifIFD.ExposureTime)  # 0x829A
        out["ExposureTime"] = _format_exposure(exp_val)

        # Aperture
        fnum_val = exif_ifd.get(piexif.ExifIFD.FNumber)  # 0x829D
        out["FNumber"] = _format_fnumber(fnum_val)

        # ISO (try several)
        iso_raw = (
            exif_ifd.get(piexif.ExifIFD.ISOSpeedRatings)  # 0x8827
            or exif_ifd.get(0x883E)  # PhotographicSensitivity
            or exif_ifd.get(0x8831)  # StandardOutputSensitivity
            or exif_ifd.get(0x8832)  # RecommendedExposureIndex
        )
        out["ISO"] = _coerce_int(iso_raw)
    except Exception:
        # swallow; caller will try XMP / exiftool
        pass

    return out


# =========================
# XMP (TIFF tag 700) helpers
# =========================
_XMP_NS = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "exif": "http://ns.adobe.com/exif/1.0/",
    "exifEX": "http://cipa.jp/exif/1.0/",
    "aux": "http://ns.adobe.com/exif/1.0/aux/",
}


def _tifflike_get_xmp_xml(path: str) -> Optional[ET.Element]:
    """
    Read XMP from TIFF tag 700 using tifffile.
    Returns the root Element of the x:xmpmeta tree or None.
    """
    try:
        from tifffile import TiffFile  # lazy import
    except Exception:
        return None

    try:
        with TiffFile(path) as tf:

            def _scan(pages):
                for p in pages:
                    tag = p.tags.get(700)  # XMP
                    if tag is not None:
                        val = tag.value
                        if isinstance(val, bytes):
                            txt = val.decode("utf-8", errors="ignore")
                        elif isinstance(val, str):
                            txt = val
                        else:
                            txt = None
                        if txt:
                            # Some XMP payloads may not include <x:xmpmeta>, handle both
                            m = re.search(
                                r"<x:xmpmeta[\s\S]*?</x:xmpmeta>",
                                txt,
                                re.IGNORECASE,
                            )
                            xml_txt = m.group(0) if m else txt
                            try:
                                return ET.fromstring(xml_txt)
                            except Exception:
                                return None
                    # recurse subifds (if present)
                    sub = getattr(p, "subifds", None)
                    if sub:
                        r = _scan(sub)
                        if r is not None:
                            return r
                return None

            return _scan(tf.pages)
    except Exception:
        return None


def _xmp_attr(root: ET.Element, ns_uri: str, local: str) -> Optional[str]:
    q = f"{{{ns_uri}}}{local}"
    for desc in root.findall(".//rdf:Description", _XMP_NS):
        if q in desc.attrib:
            val = (desc.attrib[q] or "").strip()
            if val != "":
                return val
    return None


def _xmp_iso(root: ET.Element) -> Optional[int]:
    # 1) exif:ISOSpeedRatings as Seq of rdf:li
    for el in root.findall(".//exif:ISOSpeedRatings//rdf:li", _XMP_NS):
        try:
            v = int((el.text or "").strip())
            if v > 0:
                return v
        except Exception:
            pass

    # 2) exifEX:PhotographicSensitivity element
    for el in root.findall(".//exifEX:PhotographicSensitivity", _XMP_NS):
        s = (el.text or "").strip()
        if s.isdigit():
            v = int(s)
            if v > 0:
                return v

    # 3) Attributes on rdf:Description
    for (ns, key) in (
        (_XMP_NS["exifEX"], "PhotographicSensitivity"),
        (_XMP_NS["exif"], "ISOSpeedRatings"),
        (_XMP_NS["aux"], "ISO"),
    ):
        s = _xmp_attr(root, ns, key)
        if s:
            try:
                s = s.strip().strip("[]")
                return int(s.split(",")[0])
            except Exception:
                continue
    return None


def _xmp_exposure(root: ET.Element) -> Optional[str]:
    # element text
    for el in root.findall(".//exif:ExposureTime", _XMP_NS):
        s = (el.text or "").strip()
        if s:
            if "/" in s:
                try:
                    n, d = s.split("/", 1)
                    return _format_exposure((int(n), int(d)))
                except Exception:
                    pass
            try:
                return _format_exposure(float(s))
            except Exception:
                pass

    # attribute on rdf:Description
    s = _xmp_attr(root, _XMP_NS["exif"], "ExposureTime")
    if s:
        s = s.strip()
        if "/" in s:
            try:
                n, d = s.split("/", 1)
                return _format_exposure((int(n), int(d)))
            except Exception:
                return None
        try:
            return _format_exposure(float(s))
        except Exception:
            return None
    return None


def _xmp_fnumber(root: ET.Element) -> Optional[str]:
    # element
    for el in root.findall(".//exif:FNumber", _XMP_NS):
        s = (el.text or "").strip()
        if s:
            try:
                if "/" in s:
                    n, d = s.split("/", 1)
                    return _format_fnumber((int(n), int(d)))
                return _format_fnumber(float(s))
            except Exception:
                pass

    # attribute
    s = _xmp_attr(root, _XMP_NS["exif"], "FNumber")
    if s:
        try:
            if "/" in s:
                n, d = s.split("/", 1)
                return _format_fnumber((int(n), int(d)))
            return _format_fnumber(float(s))
        except Exception:
            return None
    return None


def _xmp_read(path: str) -> Dict[str, Any]:
    out = {
        "CameraMake": None,
        "CameraModel": None,
        "ExposureTime": None,
        "FNumber": None,
        "ISO": None,
    }
    root = _tifflike_get_xmp_xml(path)
    if root is None:
        return out

    # Camera make/model often appear as attributes too
    make_attr = _xmp_attr(root, "http://ns.adobe.com/tiff/1.0/", "Make")
    model_attr = _xmp_attr(root, "http://ns.adobe.com/tiff/1.0/", "Model")
    out["CameraMake"] = _pick_text(make_attr)
    out["CameraModel"] = _pick_text(model_attr)

    out["ISO"] = _xmp_iso(root)
    out["ExposureTime"] = _xmp_exposure(root)
    out["FNumber"] = _xmp_fnumber(root)
    return out


# =========================
# ExifTool fallback
# =========================
def _exiftool_get(path, keys):
    exe = _find_exiftool()
    out = {k: None for k in keys}
    if not exe:
        return out  # silently give Nones; caller keeps EXIF/XMP values

    # -S = short tag names, -n = numeric values (no strings like "1/90")
    cmd = [exe, "-S", "-n"] + [f"-{k}" for k in keys] + [path]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        if res.returncode != 0:
            return out
        for line in (res.stdout or "").splitlines():
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            k = k.strip()
            v = v.strip()
            if k in out and v != "":
                out[k] = v
    except Exception:
        pass
    return out


# =========================
# Public API
# =========================
def get_metadata(path: str, enable_exiftool_fallback: bool = True) -> Dict[str, Any]:
    """
    Returns:
      dict with CameraMake, CameraModel, ExposureTime, FNumber, ISO

    Order:
      EXIF -> XMP -> (optional) exiftool
    """
    # Start empty
    out: Dict[str, Any] = {
        "CameraMake": None,
        "CameraModel": None,
        "ExposureTime": None,
        "FNumber": None,
        "ISO": None,
    }

    # EXIF
    ex = _exif_read(path)
    for k, v in ex.items():
        out[k] = v if out[k] in (None, "", []) and v not in (None, "", []) else out[k]

    # XMP (fills gaps)
    xm = _xmp_read(path)
    for k, v in xm.items():
        out[k] = v if out[k] in (None, "", []) and v not in (None, "", []) else out[k]

    # ExifTool fallback (fills remaining gaps, e.g., MakerNotes-backed values)
    if enable_exiftool_fallback and any(
        out[k] in (None, "", []) for k in ("ISO", "FNumber", "ExposureTime", "CameraMake", "CameraModel")
    ):
        fx = _exiftool_get(path, ["ISO", "FNumber", "ExposureTime", "Make", "Model"])
        if out["ISO"] in (None, "", []):
            try:
                out["ISO"] = _coerce_int(fx.get("ISO"))
            except Exception:
                pass
        if out["FNumber"] in (None, "", []):
            fv = fx.get("FNumber")
            if fv:
                try:
                    out["FNumber"] = _format_fnumber(float(fv))
                except Exception:
                    pass
        if out["ExposureTime"] in (None, "", []):
            ev = fx.get("ExposureTime")
            if ev:
                try:
                    if "/" in ev:
                        n, d = ev.split("/", 1)
                        out["ExposureTime"] = _format_exposure((int(n), int(d)))
                    else:
                        out["ExposureTime"] = _format_exposure(float(ev))
                except Exception:
                    pass
        if out["CameraMake"] in (None, "", []):
            mv = fx.get("Make")
            if mv:
                out["CameraMake"] = mv
        if out["CameraModel"] in (None, "", []):
            mv = fx.get("Model")
            if mv:
                out["CameraModel"] = mv

    return out


def get_metadata_string(path: str, enable_exiftool_fallback: bool = True) -> str:
    md = get_metadata(path, enable_exiftool_fallback=enable_exiftool_fallback)

    def nz(k, fallback="N/A"):
        v = md.get(k)
        return str(v) if v not in (None, "", []) else fallback

    parts = []
    cam = " ".join(x for x in [nz("CameraMake", ""), nz("CameraModel", "")] if x).strip()
    if cam:
        parts.append(f"Camera: {cam}")
    parts.append(f"Exposure: {nz('ExposureTime')}")
    parts.append(f"Aperture: {nz('FNumber')}")
    parts.append(f"ISO: {nz('ISO')}")
    return " | ".join(parts)
