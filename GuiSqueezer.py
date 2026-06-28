import datetime
import logging
import os
import sys
import threading
from pathlib import Path

import cv2
import rawpy
import tifffile
from PIL import Image
import numpy as np
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

LOG_PATH = Path.home() / 'Library' / 'Logs' / 'RAWSqueezer.log'
RAW_EXTENSIONS = ['.arw', '.nef', '.cr2', '.dng', '.orf', '.raf', '.pef', '.srw', '.x3f']

COLORSPACE_MAP = {
    'sRGB': rawpy.ColorSpace.sRGB,
    'Adobe RGB': rawpy.ColorSpace.Adobe,
    'ProPhoto RGB': rawpy.ColorSpace.ProPhoto,
}

cancel_event = threading.Event()
root = None
folder_var = None
factor_var = None
custom_var = None
colorspace_var = None
file_label_var = None
browse_btn = None
combobox = None
colorspace_combobox = None
custom_entry = None
start_btn = None
cancel_btn = None
progress = None


def configure_logging():
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(LOG_PATH),
        level=logging.DEBUG,
        format='%(asctime)s %(levelname)s %(message)s',
        force=True,
    )
    logging.debug('RAWSqueezer startup: argv=%s', sys.argv)
    logging.debug('Python executable: %s', sys.executable)
    logging.debug('Python version: %s', sys.version)
    logging.debug('rawpy version: %s', getattr(rawpy, '__version__', 'unknown'))
    logging.debug('cv2 version: %s', getattr(cv2, '__version__', 'unknown'))
    logging.debug('PIL version: %s', getattr(Image, '__version__', 'unknown'))
    logging.debug('tifffile imported successfully')


def log_exception(message: str):
    logging.error(message, exc_info=True)


def write_launch_log():
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open('a', encoding='utf-8') as handle:
            handle.write(f'----- STARTUP {datetime.datetime.now().isoformat()} -----\n')
    except Exception:
        pass


write_launch_log()
configure_logging()


def save_tiff(output_path: str, image: np.ndarray):
    try:
        if image.dtype != np.uint16:
            image = image.astype(np.uint16)

        tifffile.imwrite(
            output_path,
            image,
            photometric='rgb',
            compression='lzw',
            metadata={'axes': 'YXC'},
        )
        logging.debug('Saved 16-bit TIFF: %s', output_path)
    except Exception:
        logging.warning('Failed to save 16-bit TIFF, falling back to 8-bit TIFF', exc_info=True)
        fallback = (image >> 8).astype('uint8')
        img = Image.fromarray(fallback)
        img.save(output_path, compression='tiff_lzw')


def desqueeze_raw(file_path: str, output_folder: str, factor: float, output_color: rawpy.ColorSpace):
    logging.debug('Processing file: %s', file_path)
    with rawpy.imread(file_path) as raw:
        rgb = raw.postprocess(
            use_camera_wb=True,
            no_auto_bright=True,
            output_bps=16,
            output_color=output_color,
        )

    height, width, _ = rgb.shape
    new_width = int(width * factor)
    resized = cv2.resize(rgb, (new_width, height), interpolation=cv2.INTER_LANCZOS4)

    filename = os.path.splitext(os.path.basename(file_path))[0] + '_desqueezed.tiff'
    output_path = os.path.join(output_folder, filename)
    save_tiff(output_path, resized)


def set_ui_state(processing: bool):
    state = 'disabled' if processing else 'normal'
    start_btn.config(state=state)
    browse_btn.config(state=state)
    combobox.config(state='disabled' if processing else 'readonly')
    colorspace_combobox.config(state='disabled' if processing else 'readonly')
    cancel_btn.config(state='normal' if processing else 'disabled')
    if not processing:
        file_label_var.set('')
        progress['value'] = 0


def browse_folder():
    folder = filedialog.askdirectory()
    if folder:
        folder_var.set(folder)


def on_factor_select(event=None):
    if factor_var.get() == 'Custom':
        custom_entry.config(state='normal')
        custom_entry.focus_set()
    else:
        custom_entry.config(state='disabled')


def update_progress(index: int, total: int, filename: str):
    progress['maximum'] = total
    progress['value'] = index
    file_label_var.set(f'Processing {filename} ({index}/{total})')


def run_desqueeze():
    folder_path = folder_var.get()
    if not folder_path:
        messagebox.showerror('Error', 'Please select a folder with RAW files.')
        set_ui_state(processing=False)
        return

    try:
        factor = float(custom_var.get()) if factor_var.get() == 'Custom' else float(factor_var.get())
    except ValueError:
        messagebox.showerror('Error', 'Invalid desqueeze factor.')
        set_ui_state(processing=False)
        return

    matching_files = [
        f for f in os.listdir(folder_path)
        if f.lower().endswith(tuple(RAW_EXTENSIONS))
    ]
    if not matching_files:
        messagebox.showinfo('No files', 'No supported RAW files found in this folder.')
        set_ui_state(processing=False)
        return

    today = datetime.datetime.now().strftime('%Y-%m-%d')
    output_folder = os.path.join(folder_path, f'desqueezed_{today}')
    os.makedirs(output_folder, exist_ok=True)

    total = len(matching_files)
    output_color = COLORSPACE_MAP.get(colorspace_var.get(), rawpy.ColorSpace.sRGB)
    cancel_event.clear()

    failed_files = []

    for index, file_name in enumerate(matching_files, start=1):
        if cancel_event.is_set():
            file_label_var.set('Cancelled.')
            messagebox.showinfo(
                'Cancelled',
                f'Processing was cancelled.\n\n'
                f'Completed: {index - 1} / {total} files\n'
                f'Output folder:\n{output_folder}'
            )
            set_ui_state(processing=False)
            return

        update_progress(index, total, file_name)
        try:
            desqueeze_raw(os.path.join(folder_path, file_name), output_folder, factor, output_color)
        except Exception as exc:
            logging.error('Error processing %s', file_name, exc_info=True)
            failed_files.append((file_name, str(exc)))

        root.update_idletasks()

    set_ui_state(processing=False)
    file_label_var.set('')

    if failed_files:
        error_summary = '\n'.join(f'• {name}: {err}' for name, err in failed_files)
        messagebox.showwarning(
            'Done with errors',
            f'Completed with {len(failed_files)} error(s):\n\n{error_summary}\n\n'
            f'Output folder:\n{output_folder}'
        )
    else:
        messagebox.showinfo(
            'Done',
            f'Desqueezing completed!\n\n'
            f'Processed: {total} files\n'
            f'Output folder:\n{output_folder}'
        )


def start_desqueeze():
    set_ui_state(processing=True)
    threading.Thread(target=run_desqueeze, daemon=True).start()


def cancel_desqueeze():
    cancel_event.set()
    cancel_btn.config(state='disabled')
    file_label_var.set('Cancelling after current file...')


def build_ui():
    global root, folder_var, factor_var, custom_var, colorspace_var, file_label_var
    global browse_btn, combobox, colorspace_combobox, custom_entry, start_btn, cancel_btn, progress

    root = tk.Tk()
    root.title('RAWSqueezer')
    root.resizable(False, False)

    main_frame = ttk.Frame(root, padding=15)
    main_frame.grid()

    folder_var = tk.StringVar()
    factor_var = tk.StringVar(value='1.33')
    custom_var = tk.StringVar(value='')
    colorspace_var = tk.StringVar(value='sRGB')
    file_label_var = tk.StringVar(value='')

    ttk.Label(main_frame, text='RAW folder').grid(row=0, column=0, sticky='w')
    ttk.Entry(main_frame, textvariable=folder_var, width=45).grid(row=0, column=1, padx=5)
    browse_btn = ttk.Button(main_frame, text='Browse', command=browse_folder)
    browse_btn.grid(row=0, column=2)

    ttk.Label(main_frame, text='Desqueeze factor').grid(row=1, column=0, sticky='w', pady=(10, 0))
    combobox = ttk.Combobox(
        main_frame,
        textvariable=factor_var,
        values=['1.33', '1.5', '1.6', '2.0', 'Custom'],
        state='readonly',
        width=10,
    )
    combobox.grid(row=1, column=1, sticky='w', pady=(10, 0))
    combobox.bind('<<ComboboxSelected>>', on_factor_select)

    custom_entry = ttk.Entry(main_frame, textvariable=custom_var, width=8, state='disabled')
    custom_entry.grid(row=1, column=2, sticky='w', padx=(8, 0), pady=(10, 0))

    ttk.Label(main_frame, text='Output colorspace').grid(row=2, column=0, sticky='w', pady=(10, 0))
    colorspace_combobox = ttk.Combobox(
        main_frame,
        textvariable=colorspace_var,
        values=list(COLORSPACE_MAP.keys()),
        state='readonly',
        width=14,
    )
    colorspace_combobox.grid(row=2, column=1, sticky='w', pady=(10, 0))

    btn_frame = ttk.Frame(main_frame)
    btn_frame.grid(row=3, column=0, columnspan=3, pady=15)

    start_btn = ttk.Button(btn_frame, text='Start Desqueeze', command=start_desqueeze)
    start_btn.pack(side='left', padx=(0, 8))

    cancel_btn = ttk.Button(btn_frame, text='Cancel', command=cancel_desqueeze, state='disabled')
    cancel_btn.pack(side='left')

    progress = ttk.Progressbar(main_frame, length=300)
    progress.grid(row=4, column=0, columnspan=3, pady=(0, 4))

    ttk.Label(main_frame, textvariable=file_label_var, foreground='gray', width=50).grid(row=5, column=0, columnspan=3)
    ttk.Label(
        main_frame,
        text='Output saved as 16-bit TIFF in desqueezed_YYYY-MM-DD',
        foreground='gray',
    ).grid(row=6, column=0, columnspan=3, pady=(6, 0))

    root.mainloop()


if __name__ == '__main__':
    try:
        build_ui()
    except Exception:
        log_exception('Unhandled exception in GuiSqueezer')
        try:
            messagebox.showerror(
                'GuiSqueezer failed',
                f'An unexpected error occurred during startup.\nSee log: {LOG_PATH}'
            )
        except Exception:
            pass
        raise
