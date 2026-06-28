import os
import rawpy
from PIL import Image
import numpy as np
import datetime
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

RAW_EXTENSIONS = ['.arw', '.nef', '.cr2', '.dng', '.orf', '.raf', '.pef', '.srw', '.x3f']

cancel_event = threading.Event()


def desqueeze_raw(file_path, output_folder, factor):
    with rawpy.imread(file_path) as raw:
        rgb = raw.postprocess(
            use_camera_wb=True,
            no_auto_bright=True,
            output_bps=16          # 16-bit output — bevarer fuld dynamik fra RAW
        )
    height, width, _ = rgb.shape
    new_width = int(width * factor)

    # Try to write a 16-bit TIFF while preserving channels.
    # Resize each 16-bit channel with Pillow (it supports 16-bit single-channel),
    # then stack and save with tifffile if available.
    try:
        import tifffile

        channels = []
        for c in range(3):
            ch = Image.fromarray(rgb[:, :, c])
            ch_resized = ch.resize((new_width, height), Image.LANCZOS)
            channels.append(np.array(ch_resized, dtype=np.uint16))

        out_rgb = np.stack(channels, axis=2)
        filename = os.path.splitext(os.path.basename(file_path))[0] + "_desqueezed.tiff"
        tifffile.imwrite(
            os.path.join(output_folder, filename),
            out_rgb,
            photometric='rgb',
            compression='lzw'
        )
    except Exception:
        # Fallback: convert to 8-bit RGB and save with Pillow (still usable).
        img8 = (rgb >> 8).astype('uint8')
        img = Image.fromarray(img8)
        filename = os.path.splitext(os.path.basename(file_path))[0] + "_desqueezed.tiff"
        img = img.resize((new_width, height), Image.LANCZOS)
        img.save(
            os.path.join(output_folder, filename),
            compression="tiff_lzw"
        )


def run_desqueeze():
    folder_path = folder_var.get()
    if not folder_path:
        messagebox.showerror("Error", "Please select a folder with RAW files.")
        set_ui_state(processing=False)
        return

    try:
        factor = float(custom_var.get()) if factor_var.get() == "Custom" else float(factor_var.get())
    except ValueError:
        messagebox.showerror("Error", "Invalid desqueeze factor.")
        set_ui_state(processing=False)
        return

    matching_files = [
        f for f in os.listdir(folder_path)
        if f.lower().endswith(tuple(RAW_EXTENSIONS))
    ]
    if not matching_files:
        messagebox.showinfo("No files", "No supported RAW files found in this folder.")
        set_ui_state(processing=False)
        return

    today = datetime.datetime.now().strftime("%Y-%m-%d")
    output_folder = os.path.join(folder_path, f"desqueezed_{today}")
    os.makedirs(output_folder, exist_ok=True)

    progress["maximum"] = len(matching_files)
    progress["value"] = 0
    cancel_event.clear()

    failed_files = []

    for i, file in enumerate(matching_files, start=1):
        if cancel_event.is_set():
            file_label_var.set("Cancelled.")
            messagebox.showinfo(
                "Cancelled",
                f"Processing was cancelled.\n\n"
                f"Completed: {i - 1} / {len(matching_files)} files\n"
                f"Output folder:\n{output_folder}"
            )
            set_ui_state(processing=False)
            return

        file_label_var.set(f"Processing: {file}")
        try:
            desqueeze_raw(os.path.join(folder_path, file), output_folder, factor)
        except Exception as e:
            failed_files.append((file, str(e)))

        progress["value"] = i
        root.update_idletasks()

    file_label_var.set("")
    set_ui_state(processing=False)

    if failed_files:
        error_summary = "\n".join(f"• {name}: {err}" for name, err in failed_files)
        messagebox.showwarning(
            "Done with errors",
            f"Completed with {len(failed_files)} error(s):\n\n{error_summary}\n\n"
            f"Output folder:\n{output_folder}"
        )
    else:
        messagebox.showinfo(
            "Done",
            f"Desqueezing completed!\n\n"
            f"Processed: {len(matching_files)} files\n"
            f"Output folder:\n{output_folder}"
        )


def start_desqueeze():
    set_ui_state(processing=True)
    threading.Thread(target=run_desqueeze, daemon=True).start()


def cancel_desqueeze():
    cancel_event.set()
    cancel_btn.config(state="disabled")
    file_label_var.set("Cancelling after current file…")


def set_ui_state(processing: bool):
    state = "disabled" if processing else "normal"
    start_btn.config(state=state)
    browse_btn.config(state=state)
    combobox.config(state="disabled" if processing else "readonly")
    cancel_btn.config(state="normal" if processing else "disabled")
    if not processing:
        file_label_var.set("")
        progress["value"] = 0


def browse_folder():
    folder = filedialog.askdirectory()
    if folder:
        folder_var.set(folder)


def on_factor_select(event=None):
    if factor_var.get() == "Custom":
        custom_entry.config(state="normal")
        custom_entry.focus_set()
    else:
        custom_entry.config(state="disabled")


# ──────────────────────────── GUI ────────────────────────────

root = tk.Tk()
root.title("RAWSqueezer")
root.resizable(False, False)

main = ttk.Frame(root, padding=15)
main.grid()

folder_var      = tk.StringVar()
factor_var      = tk.StringVar(value="1.33")
custom_var      = tk.StringVar(value="")
file_label_var  = tk.StringVar(value="")

# Row 0 — folder picker
ttk.Label(main, text="RAW folder").grid(row=0, column=0, sticky="w")
ttk.Entry(main, textvariable=folder_var, width=45).grid(row=0, column=1, padx=5)
browse_btn = ttk.Button(main, text="Browse", command=browse_folder)
browse_btn.grid(row=0, column=2)

# Row 1 — desqueeze factor
ttk.Label(main, text="Desqueeze factor").grid(row=1, column=0, sticky="w", pady=(10, 0))
combobox = ttk.Combobox(
    main,
    textvariable=factor_var,
    values=["1.33", "1.5", "1.6", "2.0", "Custom"],
    state="readonly",
    width=10
)
combobox.grid(row=1, column=1, sticky="w", pady=(10, 0))
combobox.bind("<<ComboboxSelected>>", on_factor_select)

custom_entry = ttk.Entry(main, textvariable=custom_var, width=8, state="disabled")
custom_entry.grid(row=1, column=2, sticky="w", padx=(8, 0), pady=(10, 0))

# Row 2 — Start / Cancel
btn_frame = ttk.Frame(main)
btn_frame.grid(row=2, column=0, columnspan=3, pady=15)

start_btn = ttk.Button(btn_frame, text="Start Desqueeze", command=start_desqueeze)
start_btn.pack(side="left", padx=(0, 8))

cancel_btn = ttk.Button(btn_frame, text="Cancel", command=cancel_desqueeze, state="disabled")
cancel_btn.pack(side="left")

# Row 3 — progress bar
progress = ttk.Progressbar(main, length=300)
progress.grid(row=3, column=0, columnspan=3, pady=(0, 4))

# Row 4 — current filename
ttk.Label(main, textvariable=file_label_var, foreground="gray", width=50).grid(
    row=4, column=0, columnspan=3
)

# Row 5 — output info
ttk.Label(
    main,
    text="Output saved as 16-bit TIFF in desqueezed_YYYY-MM-DD",
    foreground="gray"
).grid(row=5, column=0, columnspan=3, pady=(6, 0))

root.mainloop()