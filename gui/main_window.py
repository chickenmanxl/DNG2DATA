import customtkinter as ctk
from PIL import ImageTk
import numpy as np

from utils.file_dialogs import (
    ask_open_dng,
    ask_save_csv,
    ask_open_template,
    ask_save_template,
    ask_open_folder,
    ask_save_excel,
)
from processing.dng_loader import load_dng
from processing.metadata import get_metadata_string
from processing.analysis import compute_region_stats, measure_regions, extract_raw_region
from processing.regions import Region, load_template, save_template
from processing.time_series import collect_time_series


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

        self.shape_var = ctk.StringVar(value="rect")
        self.shape_menu = ctk.CTkOptionMenu(top, variable=self.shape_var, values=["rect", "circle", "polygon"])
        self.shape_menu.pack(side="left", padx=(0, 10), pady=8)

        self.load_tpl_btn = ctk.CTkButton(top, text="Load Template", command=self.on_load_template)
        self.load_tpl_btn.pack(side="left", padx=(0, 10), pady=8)
        self.save_tpl_btn = ctk.CTkButton(top, text="Save Template", command=self.on_save_template)
        self.save_tpl_btn.pack(side="left", padx=(0, 10), pady=8)
        self.export_btn = ctk.CTkButton(top, text="Export CSV", command=self.on_export_csv)
        self.export_btn.pack(side="left", padx=(0, 10), pady=8)
        self.series_btn = ctk.CTkButton(top, text="Process Folder", command=self.on_process_folder)
        self.series_btn.pack(side="left", padx=(0, 10), pady=8)
        self.raw_btn = ctk.CTkButton(top, text="View Raw", command=self.on_view_raw)
        self.raw_btn.pack(side="left", padx=(0, 10), pady=8)

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
        self._raw_bayer = None
        self._temp_shape_id = None
        self._drag_start = None
        self._image_size_display = (0, 0)
        self._current_path = None

        self.regions: list[Region] = []
        self._next_region_id = 1
        self._drawing_polygon = False
        self._poly_points: list[tuple[int, int]] = []
        self._poly_line_ids: list[int] = []
        self._last_region: Region | None = None

        # Bindings
        self.canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)
        self.canvas.bind("<Double-Button-1>", self._on_double_click)
        self.bind("<Configure>", lambda e: self._redraw_image())

    # ---------- File Ops ----------
    def on_open(self):
        path = ask_open_dng(self)
        if not path:
            return
        self._current_path = path
        self._load_and_show()

    def apply_settings(self):
        # Reprocess current image with new settings (if any image is loaded).
        if not self._current_path:
            return
        self._load_and_show()

    def _get_load_settings(self) -> dict:
        # Collect current loader settings from the options panel.
        return {
            "output_bits": 16 if self.opts.bitdepth_var.get() == "16-bit" else 8,
            "wb_mode": self.opts.wb_mode_var.get(),
            "user_wb_rgb": self.opts.get_manual_wb(),
            "gamma_mode": self.opts.gamma_mode_var.get(),
            "gamma_tuple": self.opts.get_gamma_tuple(),
            "auto_bright": bool(self.opts.auto_bright_var.get()),
            "demosaic_algo": self.opts.demosaic_var.get(),
        }

    def _load_and_show(self):
        print(self._get_load_settings())
        try:
            full_rgb, raw_bayer, display_pil, scale = load_dng(
                self._current_path,
                max_w=1600, max_h=1000,
                **self._get_load_settings(),
            )
        except Exception as e:
            self.meta_label.configure(text=f"Failed to load: {e}")
            return

        self._full_rgb = full_rgb
        self._raw_bayer = raw_bayer
        self._scale = scale
        self.regions.clear()
        self._next_region_id = 1
        self._last_region = None
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
        self._draw_all_regions()

    def _draw_all_regions(self):
        if self._full_rgb is None:
            return
        ox, oy = self._display_origin
        for reg in self.regions:
            if reg.shape == "rect":
                x = reg.params["x"]; y = reg.params["y"]
                w = reg.params["w"]; h = reg.params["h"]
                x0 = int(x * self._scale + ox)
                y0 = int(y * self._scale + oy)
                x1 = int((x + w) * self._scale + ox)
                y1 = int((y + h) * self._scale + oy)
                self.canvas.create_rectangle(x0, y0, x1, y1, outline="red", width=2)
                self.canvas.create_text(x0 + 4, y0 + 4, text=str(reg.id), anchor="nw", fill="red")
            elif reg.shape == "circle":
                cx = reg.params["cx"]; cy = reg.params["cy"]; r = reg.params["r"]
                x0 = int((cx - r) * self._scale + ox)
                y0 = int((cy - r) * self._scale + oy)
                x1 = int((cx + r) * self._scale + ox)
                y1 = int((cy + r) * self._scale + oy)
                self.canvas.create_oval(x0, y0, x1, y1, outline="red", width=2)
                self.canvas.create_text(x0 + 4, y0 + 4, text=str(reg.id), anchor="nw", fill="red")
            elif reg.shape == "polygon":
                pts = []
                for px, py in reg.params["points"]:
                    pts.extend([int(px * self._scale + ox), int(py * self._scale + oy)])
                self.canvas.create_polygon(pts, outline="red", fill="", width=2)
                if pts:
                    self.canvas.create_text(pts[0] + 4, pts[1] + 4, text=str(reg.id), anchor="nw", fill="red")

    # ---------- ROI Selection ----------
    def _on_mouse_down(self, event):
        if not self._tk_img:
            return
        mode = self.shape_var.get()
        if mode == "polygon":
            if not self._drawing_polygon:
                self._drawing_polygon = True
                self._poly_points = [(event.x, event.y)]
            else:
                last = self._poly_points[-1]
                line_id = self.canvas.create_line(last[0], last[1], event.x, event.y, fill="red", width=2)
                self._poly_line_ids.append(line_id)
                self._poly_points.append((event.x, event.y))
            return
        self._drag_start = (event.x, event.y)
        if self._temp_shape_id:
            self.canvas.delete(self._temp_shape_id)
            self._temp_shape_id = None

    def _on_mouse_drag(self, event):
        if not self._drag_start or self.shape_var.get() == "polygon":
            return
        x0, y0 = self._drag_start
        x1, y1 = event.x, event.y
        mode = self.shape_var.get()
        if mode == "rect":
            if self._temp_shape_id:
                self.canvas.coords(self._temp_shape_id, x0, y0, x1, y1)
            else:
                self._temp_shape_id = self.canvas.create_rectangle(x0, y0, x1, y1, outline="red", width=2)
        elif mode == "circle":
            r = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
            if self._temp_shape_id:
                self.canvas.coords(self._temp_shape_id, x0 - r, y0 - r, x0 + r, y0 + r)
            else:
                self._temp_shape_id = self.canvas.create_oval(x0 - r, y0 - r, x0 + r, y0 + r, outline="red", width=2)

    def _on_mouse_up(self, event):
        if self.shape_var.get() == "polygon":
            return
        if not self._drag_start or self._full_rgb is None:
            return
        sx, sy = self._drag_start
        ex, ey = event.x, event.y
        self._drag_start = None

        ox, oy = self._display_origin
    
        mode = self.shape_var.get()
        if mode == "rect":
            x0, x1 = sorted([sx, ex])
            y0, y1 = sorted([sy, ey])
            x0 -= ox; x1 -= ox; y0 -= oy; y1 -= oy
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
            w = fx1 - fx0; h = fy1 - fy0
            params = {"x": fx0, "y": fy0, "w": w, "h": h}
        elif mode == "circle":
            dx = ex - sx
            dy = ey - sy
            r_disp = (dx ** 2 + dy ** 2) ** 0.5
            cx = (sx - ox) / self._scale
            cy = (sy - oy) / self._scale
            r = r_disp / self._scale
            params = {"cx": int(round(cx)), "cy": int(round(cy)), "r": int(round(r))}
        else:
            return
        
        region = Region(id=self._next_region_id, shape=mode, params=params)
        self.regions.append(region)
        self._next_region_id += 1
        self._temp_shape_id = None
        self._redraw_image()
        self._last_region = region
        stats = compute_region_stats(self._full_rgb, region)
        if stats:
            self.stats_label.configure(
                text=f"Region {region.id} mean (R,G,B) = ({stats['Mean R']:.2f}, {stats['Mean G']:.2f}, {stats['Mean B']:.2f})"
            )

    def _on_double_click(self, event):
        if self.shape_var.get() != "polygon" or not self._drawing_polygon:
            return
        if len(self._poly_points) < 3:
            return
        # Close polygon
        first = self._poly_points[0]
        last = self._poly_points[-1]
        line_id = self.canvas.create_line(last[0], last[1], first[0], first[1], fill="red", width=2)
        self._poly_line_ids.append(line_id)
        pts_display = self._poly_points[:]
        self._drawing_polygon = False
        self._poly_points = []
        for lid in self._poly_line_ids:
            self.canvas.delete(lid)
        self._poly_line_ids = []
        # Convert to full-resolution coordinates
        ox, oy = self._display_origin
        points_full = []
        for x, y in pts_display:
            fx = int(round((x - ox) / self._scale))
            fy = int(round((y - oy) / self._scale))
            points_full.append([fx, fy])
        region = Region(id=self._next_region_id, shape="polygon", params={"points": points_full})
        self.regions.append(region)
        self._next_region_id += 1
        self._redraw_image()
        self._last_region = region
        stats = compute_region_stats(self._full_rgb, region)
        if stats:
            self.stats_label.configure(
                text=f"Region {region.id} mean (R,G,B) = ({stats['Mean R']:.2f}, {stats['Mean G']:.2f}, {stats['Mean B']:.2f})"
            )

    # ---------- Template & Export ----------
    def on_load_template(self):
        path = ask_open_template(self)
        if not path:
            return
        try:
            regs = load_template(path)
        except Exception as e:
            self.stats_label.configure(text=f"Failed to load template: {e}")
            return
        for r in regs:
            r.id = self._next_region_id
            self._next_region_id += 1
            self.regions.append(r)
        self._last_region = self.regions[-1] if self.regions else None
        self._redraw_image()

    def on_save_template(self):
        path = ask_save_template(self)
        if not path:
            return
        save_template(path, self.regions)

    def on_export_csv(self):
        if not self.regions or self._full_rgb is None:
            return
        path = ask_save_csv(self)
        if not path:
            return
        df = measure_regions(self._full_rgb, self.regions)
        df.to_csv(path, index=False)
        self.stats_label.configure(text=f"Saved {len(df)} regions to {path}")

    def on_process_folder(self):
        """Batch-process a folder of DNG images using current regions."""
        if not self.regions:
            self.stats_label.configure(text="Define regions or load a template first")
            return
        folder = ask_open_folder(self)
        if not folder:
            return
        excel_path = ask_save_excel(self)
        if not excel_path:
            return
        try:
            collect_time_series(
                folder,
                self.regions,
                excel_path,
                load_settings=self._get_load_settings(),
            )
            self.stats_label.configure(text=f"Saved Excel to {excel_path}")
        except Exception as e:
            self.stats_label.configure(text=f"Failed: {e}")

    def on_view_raw(self):
            """Display raw Bayer data for the most recently defined region."""
            if self._raw_bayer is None or self._last_region is None:
                self.stats_label.configure(text="No region selected")
                return
            data, mask = extract_raw_region(self._raw_bayer, self._last_region)
            if data.size == 0:
                self.stats_label.configure(text="Region is empty")
                return
            top = ctk.CTkToplevel(self)
            top.title(f"Raw Region {self._last_region.id}")
            box = ctk.CTkTextbox(top, width=400, height=400, font=("Courier", 12))
            box.pack(fill="both", expand=True)
            lines = []
            if mask is None:
                for row in data:
                    lines.append(" ".join(str(int(v)) for v in row))
            else:
                for row, mrow in zip(data, mask):
                    vals = []
                    for val, m in zip(row, mrow):
                        vals.append(str(int(val)) if m else ".")
                    lines.append(" ".join(vals))
            box.insert("1.0", "\n".join(lines))
            box.configure(state="disabled")

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
        ctk.CTkLabel(wb_row, text="Manual WB (R,G1,B, G2)").pack(side="left")
        self.wb_r = ctk.CTkEntry(wb_row, width=60, placeholder_text="R")
        self.wb_g1 = ctk.CTkEntry(wb_row, width=60, placeholder_text="G1")
        self.wb_b = ctk.CTkEntry(wb_row, width=60, placeholder_text="B")
        self.wb_g2 = ctk.CTkEntry(wb_row, width=60, placeholder_text="G2")
        self.wb_r.pack(side="left", padx=(6, 4)); self.wb_g1.pack(side="left", padx=4); self.wb_b.pack(side="left", padx=4); self.wb_g2.pack(side="left", padx=4)
        # sensible defaults (neutral)
        self.wb_r.insert(0, "1.0"); self.wb_g1.insert(0, "0.5"); self.wb_b.insert(0, "1.0"); self.wb_g2.insert(0, "0.5")

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
        #try:
            r = float(self.wb_r.get())
            g1 = float(self.wb_g1.get())
            b = float(self.wb_b.get())
            g2 = float(self.wb_g2.get())
            return (r, g1, b, g2)
        #except Exception:
            #return (1.0, 0.5, 1.0, 0.5)

    def get_gamma_tuple(self):
        if self.gamma_mode_var.get() != "Manual":
            return (1.0, 1.0)
        try:
            p = float(self.gamma_power.get())
            s = float(self.gamma_slope.get())
            return (p, s)
        except Exception:
            return (2.222, 4.5)
