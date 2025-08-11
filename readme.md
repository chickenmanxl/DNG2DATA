# DNG 2 Data

## Author: Caleb Nejely  
### August 10, 2025

**DNG 2 Data** is a Python GUI tool for extracting quantitative data from `.DNG` image files.  
***DNG 2 DATA is a work in progress, changes will happen quickly and often***
---

## Current Capabilities

### **1. File Handling**
- Open `.DNG` files via a file dialog.
- Scaled preview image for responsive display.
- Maintains mapping between preview coordinates and full-resolution pixels.

### **2. Image Display & Interaction**
- Image centered in a `customtkinter` canvas.
- Click-and-drag to define a rectangular region of interest (ROI).
- Coordinate conversion from preview → full-resolution image space.

### **3. ROI Analysis**
- Computes average R, G, B values for the ROI.
- Uses full-resolution pixel data for analysis (default 8-bit, 16-bit ready).
- Displays bit depth in the results.

### **4. Metadata Extraction**
- Reads basic EXIF tags from the DNG:
  - Exposure time (seconds or fraction)
  - ISO
  - Aperture (f-number)
  - Camera make and model
- Displays metadata in a concise top-bar summary.

### **5. Modular Codebase**
- **`gui/`** — Main GUI window, event handling, drawing.
- **`processing/`** — DNG loading, ROI analysis, metadata parsing.
- **`utils/`** — File dialog helpers.
- Designed for easy expansion (e.g., more stats, batch mode, Bayer analysis).

---

## Planned Features
- Toggle between 8-bit and 16-bit output in the UI (partially implemented)
- ROI stats: min, max, standard deviation, CV, pixel count, ect.
- Histogram display
- Multiple ROI selection with plate map and CSV data export
- Kenetic data collection from image time-seies
- Zoom and pan support
- Raw Bayer plane analysis
- Fallback to `exiftool` for metadata (partially implemented)
- Drag-and-drop file loading
- Persistent settings (white balance mode, gamma, etc.) (partially implemented)

