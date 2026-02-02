import os
import rawpy
from PIL import Image
import datetime
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

RAW_EXTENSIONS = ['.arw', '.nef', '.cr2', '.dng', '.orf', '.raf', '.pef', '.srw', '.x3f']

def desqueeze_raw(file_path, output_folder, factor):
    with rawpy.imread(file_path) as raw:
        rgb = raw.postprocess(use_camera_wb=True, no_auto_bright=True)

    height, width, _ = rgb.shape
    new_width = int(width * factor)

    img = Image.fromarray(rgb)
    img = img.resize((new_width, height), Image.LANCZOS)

    filename = os.path.splitext(os.path.basename(file_path))[0] + "_desqueezed.tiff"
    img.save(os.path.join(output_folder, filename))

def run_desqueeze():
    folder_path = folder_var.get()
    if not folder_path:
        messagebox.showerror("Error", "Please select a folder with RAW files.")
        return

    try:
        if factor_var.get() == "Custom":
            factor = float(custom_var.get())
        else:
            factor = float(factor_var.get())
    except ValueError:
        messagebox.showerror("Error", "Invalid crop factor.")
        return

    matching_files = [
        f for f in os.listdir(folder_path)
        if f.lower().endswith(tuple(RAW_EXTENSIONS))
    ]

    if not matching_files:
        messagebox.showinfo("No files", "No supported RAW files found in this folder.")
        return

    today = datetime.datetime.now().strftime("%Y-%m-%d")
    output_folder = os.path.join(folder_path, f"desqueezed_{today}")
    os.makedirs(output_folder, exist_ok=True)

    progress["maximum"] = len(matching_files)
    progress["value"] = 0

    for i, file in enumerate(matching_files, start=1):
        desqueeze_raw(os.path.join(folder_path, file), output_folder, factor)
        progress["value"] = i
        root.update_idletasks()

    messagebox.showinfo(
        "Done",
        f"Desqueezing completed!\n\nOutput folder:\n{output_folder}"
    )

def browse_folder():
    folder = filedialog.askdirectory()
    if folder:
        folder_var.set(folder)

# ---------------- GUI ----------------

root = tk.Tk()
root.title("RAWSqueezer")
root.resizable(False, False)

main = ttk.Frame(root, padding=15)
main.grid()

folder_var = tk.StringVar()
factor_var = tk.StringVar(value="1.33")
custom_var = tk.StringVar(value="")

ttk.Label(main, text="RAW folder").grid(row=0, column=0, sticky="w")
ttk.Entry(main, textvariable=folder_var, width=45).grid(row=0, column=1, padx=5)
ttk.Button(main, text="Browse", command=browse_folder).grid(row=0, column=2)

ttk.Label(main, text="Desqueeze factor").grid(row=1, column=0, sticky="w", pady=(10, 0))
combobox = ttk.Combobox(
    main,
    textvariable=factor_var,
    values=["1.33", "1.5", "1.6", "2.0", "Custom"],
    state="readonly",
    width=10
)
combobox.grid(row=1, column=1, sticky="w", pady=(10, 0))

custom_entry = ttk.Entry(main, textvariable=custom_var, width=8, state="disabled")
custom_entry.grid(row=1, column=2, sticky="w", padx=(8, 0), pady=(10, 0))

def on_factor_select(event=None):
    if factor_var.get() == "Custom":
        custom_entry.config(state="normal")
        custom_entry.focus_set()
    else:
        custom_entry.config(state="disabled")

combobox.bind('<<ComboboxSelected>>', on_factor_select)

ttk.Button(
    main,
    text="Start Desqueeze",
    command=run_desqueeze
).grid(row=2, column=1, pady=15)

progress = ttk.Progressbar(main, length=300)
progress.grid(row=3, column=0, columnspan=3, pady=(0, 10))

ttk.Label(
    main,
    text="Output will be saved in the same folder\nas desqueezed_YYYY-MM-DD",
    foreground="gray"
).grid(row=4, column=0, columnspan=3)

root.mainloop()
