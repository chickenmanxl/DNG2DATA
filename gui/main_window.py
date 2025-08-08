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
        self.geometry("1250x800")

        # --- Top bar ---
        top = ctk.CTkFrame(self)
        top.pack(side="top", fill="x", padx=10, pady=(10, 0))

        self.open_btn = ctk.CTkButton(top, text="Open DNG", command=self.on_open)
        self.open_btn.pack(side="left", padx=(5, 10), pady=8)

        self.meta_label = ctk.CTkLabel(top, text="No file loaded", anchor="w", justify="left")
        self.meta_label.pack(side="left", fill="x", expand=True, padx=5, pady=8)

        # --- Main content: canvas + options panel ---
        main = ctk.CTkFrame(self)
        main.pack(fill="both", expand=True, padx=10, pady=10)

        # Canvas area
        self.canvas = ctk.CTkCanvas(main, bg="black", highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True, padx=(0, 10))

        # Options panel
        self.opts = OptionsPanel(main, apply_callback=self.apply_settings)
        self.opts.pack(side="right", fill="y")

        # Bottom status
        bottom = ctk.CTkFrame(self)
        bottom.pack(side="bottom", fill="x", padx=10, pady=(0, 10))

        self.stats_label = ctk.CTkLabel(bottom, text="", anchor="w", justify="left")
        self.stats_label.pack(side="left", fill="x", expand=True, padx=5, pady=8)

        # State
        self._tk_img = None
        self._display_origin = (0, 0)
        self._scale = 1.0
        self._full_rgb = None
        self._rect_id = None
        self._drag_start = None
        self._image_size_display = (0, 0)
        self._current_path = None

        # Bindings
        self.canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)
        self.bind("<Configure>", lambda e: self._redraw_image())

    # ---------- File Ops ----------
    def on_open(self):
        path = ask_open_dng(self)
        if not path:
            return
        self._current_path = path
        self._load_and_show()

    def apply_settings(self):
        """Reprocess current image with new settings (if any image is loaded)."""
        if not self._current_path:
            return
        self._load_and_show()

    def _load_and_show(self):
        try:
            full_rgb, display_pil, scale = load_dng(
                self._current_path,
                max_w=1600, max_h=1000,
                output_bits=16 if self.opts.bitdepth_var.get() == "16-bit" else 8,
                wb_mode=self.opts.wb_mode_var.get(),
                user_wb_rgb=self.opts.get_manual_wb(),
                gamma_mode=self.opts.gamma_mode_var.get(),
                gamma_tuple=self.opts.get_gamma_tuple(),
                auto_bright=bool(self.opts.auto_bright_var.get()),
                demosaic_algo=self.opts.demosaic_var.get(),
            )
        except Exception as e:
            self.meta_label.configure(text=f"Failed to load: {e}")
            return

        self._full_rgb = full_rgb
        self._scale = scale
        self._set_display_image(display_pil)
        self.meta_label.configure(text=get_metadata_string(self._current_path))
        self.stats_label.configure(text="Drag to select a region…")

    # ---------- Canvas/Image ----------
    def _set_display_image(self, pil_image):
        self._tk_img = ImageTk.PhotoImage(pil_image)
        self._image_size_display = (pil_image.width, pil_image.height)
        self._redraw_image()

    def _redraw_image(self):
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
        sx, sy = self._drag_start
        ex, ey = event.x, event.y
        self._drag_start = None

        x0, x1 = sorted([sx, ex])
        y0, y1 = sorted([sy, ey])

        ox, oy = self._display_origin
        x0 -= ox; x1 -= ox
        y0 -= oy; y1 -= oy

        iw, ih = self._image_size_display
        x0 = max(0, min(iw, x0)); x1 = max(0, min(iw, x1))
        y0 = max(0, min(ih, y0)); y1 = max(0, min(ih, y1))
        if (x1 - x0) < 2 or (y1 - y0) < 2:
            self.stats_label.configure(text="Selection too small.")
            return

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


class OptionsPanel(ctk.CTkFrame):
    def __init__(self, parent, apply_callback):
        super().__init__(parent, width=320)
        self.apply_callback = apply_callback

        # Section title
        title = ctk.CTkLabel(self, text="Options", font=ctk.CTkFont(size=16, weight="bold"))
        title.pack(anchor="w", padx=10, pady=(10, 6))

        # --- Bit depth ---
        self.bitdepth_var = ctk.StringVar(value="8-bit")
        ctk.CTkLabel(self, text="Output Bit Depth").pack(anchor="w", padx=10)
        ctk.CTkOptionMenu(self, variable=self.bitdepth_var, values=["8-bit", "16-bit"]).pack(fill="x", padx=10, pady=(0, 10))

        # --- White balance ---
        self.wb_mode_var = ctk.StringVar(value="Camera")
        ctk.CTkLabel(self, text="White Balance").pack(anchor="w", padx=10)
        ctk.CTkOptionMenu(self, variable=self.wb_mode_var, values=["Camera", "Auto", "Manual"]).pack(fill="x", padx=10)
        wb_row = ctk.CTkFrame(self)
        wb_row.pack(fill="x", padx=10, pady=(6, 10))
        ctk.CTkLabel(wb_row, text="Manual WB (R,G,B)").pack(side="left")
        self.wb_r = ctk.CTkEntry(wb_row, width=60, placeholder_text="R")
        self.wb_g = ctk.CTkEntry(wb_row, width=60, placeholder_text="G")
        self.wb_b = ctk.CTkEntry(wb_row, width=60, placeholder_text="B")
        self.wb_r.pack(side="left", padx=(6, 4)); self.wb_g.pack(side="left", padx=4); self.wb_b.pack(side="left", padx=4)
        # sensible defaults (neutral)
        self.wb_r.insert(0, "1.0"); self.wb_g.insert(0, "1.0"); self.wb_b.insert(0, "1.0")

        # --- Gamma ---
        self.gamma_mode_var = ctk.StringVar(value="Linear")
        ctk.CTkLabel(self, text="Gamma").pack(anchor="w", padx=10)
        ctk.CTkOptionMenu(self, variable=self.gamma_mode_var, values=["Linear", "sRGB-ish", "Manual"]).pack(fill="x", padx=10)
        gamma_row = ctk.CTkFrame(self)
        gamma_row.pack(fill="x", padx=10, pady=(6, 10))
        ctk.CTkLabel(gamma_row, text="Manual (power, slope)").pack(side="left")
        self.gamma_power = ctk.CTkEntry(gamma_row, width=70, placeholder_text="2.222")
        self.gamma_slope = ctk.CTkEntry(gamma_row, width=70, placeholder_text="4.5")
        self.gamma_power.pack(side="left", padx=(6, 4)); self.gamma_slope.pack(side="left", padx=4)

        # --- Auto bright ---
        self.auto_bright_var = ctk.IntVar(value=0)
        ctk.CTkCheckBox(self, text="Auto brightness (not linear)", variable=self.auto_bright_var).pack(anchor="w", padx=10, pady=(0, 10))

        # --- Demosaic ---
        self.demosaic_var = ctk.StringVar(value="AHD (default)")
        ctk.CTkLabel(self, text="Demosaic Algorithm").pack(anchor="w", padx=10)
        ctk.CTkOptionMenu(self, variable=self.demosaic_var,
                          values=["AHD (default)", "AMaZE", "DCB", "LMMSE", "VNG", "PPG"]).pack(fill="x", padx=10, pady=(0, 10))

        # --- Apply ---
        ctk.CTkButton(self, text="Apply Settings", command=self.apply_callback).pack(fill="x", padx=10, pady=(10, 12))

        # spacer
        ctk.CTkLabel(self, text="").pack(pady=4)

    def get_manual_wb(self):
        try:
            r = float(self.wb_r.get())
            g = float(self.wb_g.get())
            b = float(self.wb_b.get())
            return (r, g, b)
        except Exception:
            return (1.0, 1.0, 1.0)

    def get_gamma_tuple(self):
        if self.gamma_mode_var.get() != "Manual":
            return (1.0, 1.0)
        try:
            p = float(self.gamma_power.get())
            s = float(self.gamma_slope.get())
            return (p, s)
        except Exception:
            return (2.222, 4.5)
