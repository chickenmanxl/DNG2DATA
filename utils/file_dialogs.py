from tkinter import filedialog as fd

def ask_open_dng(parent=None):
    return fd.askopenfilename(
        parent=parent,
        title="Open DNG",
        filetypes=[("DNG files", "*.dng"), ("All files", "*.*")]
    )

def ask_save_csv(parent=None):
    return fd.asksaveasfilename(
        parent=parent,
        title="Save CSV",
        defaultextension=".csv",
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
    )


def ask_open_template(parent=None):
    return fd.askopenfilename(
        parent=parent,
        title="Open Template",
        filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
    )


def ask_save_template(parent=None):
    return fd.asksaveasfilename(
        parent=parent,
        title="Save Template",
        defaultextension=".json",
        filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
    )