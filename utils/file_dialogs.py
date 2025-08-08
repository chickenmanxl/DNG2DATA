from tkinter import filedialog as fd

def ask_open_dng(parent=None):
    return fd.askopenfilename(
        parent=parent,
        title="Open DNG",
        filetypes=[("DNG files", "*.dng"), ("All files", "*.*")]
    )
