# GUI layout and event logic
import customtkinter as ctk
from PIL import ImageTk
import numpy as np

from utils.file_dialogs import ask_open_dng
from processing.dng_loader import load_dng
from processing.metadata import get_metadata_string
from processing.analysis import compute_avg_rgb


class DNGViewerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.title("DNG Analyzer")
        self.geometry("1100x750")

        # Top bar
        top = ctk.CTkFrame(self)
        top.pack(side="top", fill="x", padx=10, pady=(10, 0))

        self.open_btn = ctk.CTkButton(top, text="Open DNG", command=self.on_open)
        self.open_btn.pack(side="left", padx=(5, 10), pady=8)

        self.meta_label = ctk.CTkLabel(top, text="No file loaded", anchor="w", justify="left")
        self.meta_label.pack(side="left", fill="x", expand=True, padx=5, pady=8)

        # Canvas area
        self.image_frame = ctk.CTkFrame(self)
        self.image_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Use a CTkCanvas for convenience
        self.canvas = ctk.CTkCanvas(self.image_frame, bg="black", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # Bottom status
        bottom = ctk.CTkFrame(self)
        bottom.pack(side="bottom", fill="x", padx=10, pady=(0, 10))

        self.stats_label = ctk.CTkLabel(bottom, text="", anchor="w", justify="left")
        self.stats_label.pack(side="left", fill="x", expand=True, padx=5, pady=8)

        # State
        self._tk_img = None            # PhotoImage reference
        self._display_origin = (0, 0)  # top-left where image is drawn on canvas
        self._scale = 1.0              # display scale -> full-res
        self._full_rgb = None          # numpy HxWx3, uint8 or uint16
        self._rect_id = None
        self._drag_start = None
        self._image_size_display = (0, 0)

        # Bindings
        self.canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)
        self.bind("<Configure>", lambda e: self._redraw_image())  # keep centered on resize

    # ---------- File Ops ----------
    def on_open(self):
        path = ask_open_dng(self)
        if not path:
            return
        try:
            full_rgb, display_pil, scale = load_dng(path, max_w=1400, max_h=900, output_bits=8, use_camera_wb=True)
        except Exception as e:
            self.meta_label.configure(text=f"Failed to load: {e}")
            return

        self._full_rgb = full_rgb
        self._scale = scale
        self._set_display_image(display_pil)
        self.meta_label.configure(text=get_metadata_string(path))
        self.stats_label.configure(text="Drag to select a region…")

    # ---------- Canvas/Image ----------
    def _set_display_image(self, pil_image):
        self._tk_img = ImageTk.PhotoImage(pil_image)
        self._image_size_display = (pil_image.width, pil_image.height)
        self._redraw_image()

    def _redraw_image(self):
        """Center the image on the canvas and redraw."""
        self.canvas.delete("all")
        if not self._tk_img:
            return
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        iw, ih = self._image_size_display
        ox = max(0, (cw - iw) // 2)
        oy = max(0, (ch - ih) // 2)
        self._display_origin = (ox, oy)
        self.canvas.create_image(ox, oy, image=self._tk_img, anchor="nw")

    # ---------- ROI Selection ----------
    def _on_mouse_down(self, event):
        if not self._tk_img:
            return
        self._drag_start = (event.x, event.y)
        if self._rect_id:
            self.canvas.delete(self._rect_id)
            self._rect_id = None

    def _on_mouse_drag(self, event):
        if not self._drag_start:
            return
        x0, y0 = self._drag_start
        x1, y1 = event.x, event.y
        if self._rect_id:
            self.canvas.coords(self._rect_id, x0, y0, x1, y1)
        else:
            self._rect_id = self.canvas.create_rectangle(x0, y0, x1, y1, outline="red", width=2)

    def _on_mouse_up(self, event):
        if not self._drag_start or self._full_rgb is None:
            return

        # Selection in canvas coords
        sx, sy = self._drag_start
        ex, ey = event.x, event.y
        self._drag_start = None

        # Normalize
        x0, x1 = sorted([sx, ex])
        y0, y1 = sorted([sy, ey])

        # Convert to image display coords (subtract origin)
        ox, oy = self._display_origin
        x0 -= ox; x1 -= ox
        y0 -= oy; y1 -= oy

        # Clip to displayed image bounds
        iw, ih = self._image_size_display
        x0 = max(0, min(iw, x0)); x1 = max(0, min(iw, x1))
        y0 = max(0, min(ih, y0)); y1 = max(0, min(ih, y1))

        # Ignore too small selections
        if (x1 - x0) < 2 or (y1 - y0) < 2:
            self.stats_label.configure(text="Selection too small.")
            return

        # Map display coords -> full-res coords using scale
        # display_px = full_px * scale  =>  full_px = display_px / scale
        fx0 = int(np.floor(x0 / self._scale))
        fy0 = int(np.floor(y0 / self._scale))
        fx1 = int(np.ceil(x1 / self._scale))
        fy1 = int(np.ceil(y1 / self._scale))

        h, w, _ = self._full_rgb.shape
        fx0 = max(0, min(w, fx0)); fx1 = max(0, min(w, fx1))
        fy0 = max(0, min(h, fy0)); fy1 = max(0, min(h, fy1))

        if fx1 - fx0 < 2 or fy1 - fy0 < 2:
            self.stats_label.configure(text="Selection too small after scaling.")
            return

        avg = compute_avg_rgb(self._full_rgb, fx0, fy0, fx1, fy1)
        if avg is None:
            self.stats_label.configure(text="No pixels in selection.")
            return

        r, g, b = avg
        bitdepth = 8 if self._full_rgb.dtype == np.uint8 else 16
        self.stats_label.configure(
            text=f"ROI avg (R,G,B) = ({r:.2f}, {g:.2f}, {b:.2f})  [{bitdepth}-bit]"
        )
