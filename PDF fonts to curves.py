import os
import subprocess
import sys
import threading
import time
import tkinter.messagebox as mb
import urllib.request
import webbrowser
import tempfile
import shutil
import tkinter as tk
import customtkinter as ctk
from tkinter import filedialog, messagebox
from tkinterdnd2 import TkinterDnD, DND_FILES

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

PROMPT_COLOR = "#666666"
RESULT_COLOR = "#2a7ab5"
BG = "#e8e8e8"


def create_rounded_rect(canvas, x1, y1, x2, y2, radius=15, **kwargs):
    points = [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


def get_app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


GS_WIN_NAMES = ["gswin64c.exe", "gswin32c.exe"]
GS_UNIX_NAMES = ["gs"]


def find_ghostscript():
    is_windows = sys.platform == "win32"
    gs_names = GS_WIN_NAMES if is_windows else GS_UNIX_NAMES
    # bundled portable GS alongside the app
    app_dir = get_app_dir()
    gs_dir = os.path.join(app_dir, "gs")
    if os.path.isdir(gs_dir):
        for ver_dir in os.listdir(gs_dir):
            for name in GS_WIN_NAMES + GS_UNIX_NAMES:
                exe_path = os.path.join(gs_dir, ver_dir, "bin", name)
                if os.path.exists(exe_path):
                    return exe_path

    if is_windows:
        search_paths = [
            r"C:\Program Files\gs\gs10.07.1\bin\gswin64c.exe",
            r"C:\Program Files\gs\gs10.07.0\bin\gswin64c.exe",
            r"C:\Program Files\gs\gs10.06.0\bin\gswin64c.exe",
            r"C:\Program Files\gs\gs10.05.0\bin\gswin64c.exe",
            r"C:\Program Files\gs\gs10.04.0\bin\gswin64c.exe",
            r"C:\Program Files (x86)\gs\gs10.07.1\bin\gswin32c.exe",
            r"C:\Program Files (x86)\gs\gs10.07.0\bin\gswin32c.exe",
            r"C:\Program Files\gs\gs9.56.1\bin\gswin64c.exe",
            r"C:\Program Files\gs\gs9.55.0\bin\gswin64c.exe",
        ]
        for path in search_paths:
            if os.path.exists(path):
                return path

        for root_dir in [r"C:\Program Files\gs", r"C:\Program Files (x86)\gs"]:
            if os.path.isdir(root_dir):
                for ver_dir in os.listdir(root_dir):
                    for name in GS_WIN_NAMES:
                        exe_path = os.path.join(root_dir, ver_dir, "bin", name)
                        if os.path.exists(exe_path):
                            return exe_path

    # check PATH
    for name in gs_names:
        try:
            result = subprocess.run([name, "--version"], capture_output=True, timeout=5,
                                   creationflags=0x08000000 if sys.platform == "win32" else 0)
            if result.returncode == 0:
                return name
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    return None


GS_VERSION = "10.07.1"
GS_VERSION_DIR = f"gs{GS_VERSION.replace('.', '')}"
GS_DOWNLOAD_URLS = {
    "win32": (
        "https://github.com/ArtifexSoftware/ghostpdl-downloads/releases/download/"
        f"gs{GS_VERSION.replace('.', '')}/gs{GS_VERSION.replace('.', '')}w64.exe"
    ),
}


def _download_file(url, callback):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        total = int(resp.headers.get("Content-Length", 0) or 0)
        data = bytearray()
        while True:
            chunk = resp.read(8192)
            if not chunk:
                break
            data.extend(chunk)
            if callback and total:
                callback(len(data) / total)
    return data


def _extract_windows_installer(exe_data, dest):
    """Extract a Windows InnoSetup GS installer using bundled 7z."""
    import zipfile
    tmp = tempfile.mkdtemp()
    tmp_exe = os.path.join(tmp, "gs_installer.exe")
    try:
        with open(tmp_exe, "wb") as f:
            f.write(exe_data)

        # Download 7za standalone from NuGet to extract 7-Zip NSIS installer
        nuget_url = "https://www.nuget.org/api/v2/package/7-Zip.CommandLine/25.1.0"
        nuget_data = _download_file(nuget_url, None)
        with zipfile.ZipFile(io.BytesIO(nuget_data)) as zf:
            for name in zf.namelist():
                if name.endswith("7za.exe"):
                    zf.extract(name, tmp)
                    seven_za = os.path.join(tmp, name)
                    break
            else:
                return False

        # Download 7-Zip NSIS installer
        seven_url = "https://github.com/ip7z/7zip/releases/download/26.01/7z2601-x64.exe"
        seven_data = _download_file(seven_url, None)
        seven_exe = os.path.join(tmp, "7z_installer.exe")
        with open(seven_exe, "wb") as f:
            f.write(seven_data)

        # Extract 7-Zip installer with 7za
        seven_dir = os.path.join(tmp, "7z_extract")
        os.makedirs(seven_dir, exist_ok=True)
        cf = 0x08000000 if sys.platform == "win32" else 0
        subprocess.run([seven_za, "x", seven_exe, f"-o{seven_dir}", "-y"],
                       capture_output=True, timeout=60, check=True, creationflags=cf)

        seven_z = os.path.join(seven_dir, "7z.exe")
        if not os.path.exists(seven_z):
            return False

        # Now extract GS installer with full 7z
        gs_tmp = os.path.join(tmp, "gs_extract")
        os.makedirs(gs_tmp, exist_ok=True)
        subprocess.run([seven_z, "x", tmp_exe, f"-o{gs_tmp}", "-y"],
                       capture_output=True, timeout=120, check=True, creationflags=cf)

        # Find the gs version folder
        items = os.listdir(gs_tmp)
        gs_subdirs = [d for d in items
                      if d.startswith("gs") and os.path.isdir(os.path.join(gs_tmp, d))]
        src_dir = os.path.join(gs_tmp, gs_subdirs[0]) if gs_subdirs else gs_tmp
        shutil.copytree(src_dir, dest, dirs_exist_ok=True)

        # Clean installer junk
        for f in ["$PLUGINSDIR", "uninstgs.exe.nsis", "vcredist_x64.exe",
                   "EnVar.dll", "modern-wizard.bmp", "nsDialogs.dll",
                   "nsExec.dll", "System.dll"]:
            p = os.path.join(dest, f)
            if os.path.isfile(p):
                os.remove(p)
            elif os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
        return True
    except Exception:
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def download_ghostscript(callback=None):
    import io
    app_dir = get_app_dir()
    dest = os.path.join(app_dir, "gs", GS_VERSION_DIR)
    os.makedirs(dest, exist_ok=True)

    def task():
        try:
            url = GS_DOWNLOAD_URLS.get(sys.platform)
            if not url:
                return False
            data = _download_file(url, callback)

            if sys.platform == "win32":
                ok = _extract_windows_installer(data, dest)
            else:
                # On Linux/macOS, GS is installed via package manager
                # For bundled, we'd download a tarball – not implemented here
                ok = False
            return ok
        except Exception:
            return False

    return task


class App(TkinterDnD.DnDWrapper, ctk.CTk):
    def __init__(self):
        super().__init__()
        self.TkdndVersion = TkinterDnD._require(self)

        self.title("PDF Fonts to Curves Converter")
        self.geometry("700x400")
        self.resizable(False, False)
        self.attributes('-topmost', True)
        self.configure(fg_color=BG)

        self.fn_font = ctk.CTkFont(size=26)
        self.sm_font = ctk.CTkFont(size=20)
        self.gs_path = find_ghostscript()
        self.current_result_path = None
        self.result_shown = False
        self.converting = False
        self.error_timer = None
        self._anim_id = None

        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=30, pady=30)

        self.after(10, self._setup)

    def _setup(self):
        self.update_idletasks()
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()

        create_rounded_rect(
            self.canvas, 10, 10, cw - 10, ch - 10,
            radius=128, outline="#cecece", dash=(100, 40), width=12, fill=""
        )

        self.prompt_label = ctk.CTkLabel(
            self.canvas,
            text="Drop a PDF file here or click anywhere to select",
            font=self.fn_font, text_color=PROMPT_COLOR
        )
        self.prompt_id = self.canvas.create_window(cw // 2, ch // 2 - 20, window=self.prompt_label)

        self.progress_bar = ctk.CTkProgressBar(
            self.canvas, width=500,
            fg_color="#d0d0d0", progress_color="#3b8ed0", height=14
        )
        self.progress_bar.set(0)
        self.progress_wid = self.canvas.create_window(cw // 2, ch // 2 + 40, window=self.progress_bar, state='hidden')

        self.result_frame = ctk.CTkFrame(self.canvas, fg_color="transparent")

        self.result_label = ctk.CTkLabel(
            self.result_frame, text="Done: ",
            font=self.sm_font, text_color=PROMPT_COLOR
        )
        self.result_label.grid(row=0, column=0)

        self.result_filename = ctk.CTkLabel(
            self.result_frame, text="",
            font=self.sm_font, text_color=PROMPT_COLOR, cursor="hand2"
        )
        self.result_filename.grid(row=0, column=1)
        self.result_filename.bind("<Button-1>", self._open_result_file)
        self.result_filename.bind("<Enter>", lambda e: self.result_filename.configure(text_color=RESULT_COLOR))
        self.result_filename.bind("<Leave>", lambda e: self.result_filename.configure(text_color=PROMPT_COLOR))

        self.folder_icon = ctk.CTkLabel(
            self.result_frame, text="📁",
            font=ctk.CTkFont(family="Segoe UI Emoji", size=15),
            text_color="#888888", cursor="hand2"
        )
        self.folder_icon.grid(row=0, column=2, padx=(6, 0))
        self.folder_icon.bind("<Button-1>", self._open_result_folder)

        self.result_wid = self.canvas.create_window(cw // 2, ch // 2 + 70, window=self.result_frame, state='hidden')

        self.canvas.bind("<Button-1>", self._on_click)

        self.drop_target_register(DND_FILES)
        self.dnd_bind('<<Drop>>', self._drop)

    def _on_click(self, event):
        if self.converting:
            return
        self.open_file_dialog()

    def open_file_dialog(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("PDF Files", "*.pdf")],
            title="Select a PDF file"
        )
        if file_path:
            self.convert_single_pdf(file_path)

    def convert_single_pdf(self, file_path):
        if self.error_timer:
            self.after_cancel(self.error_timer)
            self.error_timer = None

        if not file_path.lower().endswith(".pdf"):
            self.prompt_label.configure(text="Not a PDF file", text_color="#cc3333")
            self.error_timer = self.after(2500, self._reset_prompt)
            return

        if not os.path.isfile(file_path):
            self.prompt_label.configure(text="File not found", text_color="#cc3333")
            self.error_timer = self.after(2500, self._reset_prompt)
            return

        if not self.gs_path:
            ret = messagebox.askyesno(
                "Ghostscript not found",
                "This program requires Ghostscript to convert PDFs.\n\n"
                "Do you want to download it now?\n\n"
                "Place the extracted 'gs' folder next to the application afterwards."
            )
            if ret:
                import webbrowser
                webbrowser.open("https://github.com/ArtifexSoftware/ghostpdl-downloads/releases")
            return

        base_name, ext = os.path.splitext(file_path)
        output_pdf_path = f"{base_name}_curves{ext}"

        if os.path.exists(output_pdf_path):
            if not messagebox.askyesno("File exists",
                    f"Overwrite existing file?\n{os.path.basename(output_pdf_path)}"):
                return

        self.result_shown = False
        self._show_result_visible(False)
        self._show_progress_visible(True)
        self.prompt_label.configure(
            text=f"Converting: {os.path.basename(file_path)}...",
            text_color=PROMPT_COLOR
        )

        threading.Thread(target=lambda: self._worker(file_path, output_pdf_path), daemon=True).start()

    def _worker(self, file_path, output_path):
        try:
            self._convert_fonts_to_curves(file_path, output_path)
            self.after(0, lambda: self._on_done(output_path))
        except subprocess.TimeoutExpired:
            self.after(0, lambda: self._on_error("Error: Timeout"))
        except Exception as e:
            self.after(0, lambda: self._on_error(str(e)[:50]))

    def _convert_fonts_to_curves(self, pdf_path, output_pdf_path):

        gs_command = [
            self.gs_path,
            "-o", output_pdf_path,
            "-dNoOutputFonts",
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.7",
            "-dNOPAUSE",
            "-dBATCH",
            pdf_path
        ]

        result = subprocess.run(gs_command, capture_output=True, text=True, timeout=120,
                               creationflags=0x08000000 if sys.platform == "win32" else 0)
        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip() or "Unknown error"
            raise RuntimeError(f"Ghostscript error: {error_msg}")

        return output_pdf_path

    def _on_done(self, output):
        self._show_progress_visible(False)
        self.current_result_path = output
        self.result_shown = True
        self._show_result(output)
        self._reset_prompt()

    def _on_error(self, msg):
        self._show_progress_visible(False)
        self.prompt_label.configure(text=f"Error: {msg}", text_color="#cc3333")
        self.error_timer = self.after(3000, self._reset_prompt)

    def _reset_prompt(self):
        self.prompt_label.configure(
            text="Drop a PDF file here or click anywhere to select",
            text_color=PROMPT_COLOR
        )

    def _show_progress_visible(self, visible):
        if visible:
            self.converting = True
            self.progress_bar.set(0)
            self.canvas.itemconfig(self.progress_wid, state='normal')
            self._anim_id = self.after(50, self._animate_progress)
        else:
            self.converting = False
            if self._anim_id:
                self.after_cancel(self._anim_id)
                self._anim_id = None
            self.canvas.itemconfig(self.progress_wid, state='hidden')

    def _animate_progress(self):
        if not self.converting:
            return
        val = self.progress_bar.get() + 0.04
        if val >= 0.95:
            val = 0.05
        self.progress_bar.set(val)
        self._anim_id = self.after(50, self._animate_progress)

    def _show_result(self, file_path):
        basename = os.path.basename(file_path)
        if len(basename) > 35:
            basename = basename[:32] + "..."
        self.result_filename.configure(text=basename)
        self.canvas.itemconfig(self.result_wid, state='normal')
        label = "📁" if os.path.exists(file_path) else ""
        self.folder_icon.configure(text=label)

    def _show_result_visible(self, visible):
        state = 'normal' if visible else 'hidden'
        self.canvas.itemconfig(self.result_wid, state=state)

    def _open_result_file(self, event):
        if self.current_result_path and os.path.exists(self.current_result_path):
            os.startfile(self.current_result_path)
        return "break"

    def _open_result_folder(self, event):
        if self.current_result_path and os.path.exists(self.current_result_path):
            os.startfile(os.path.dirname(self.current_result_path))
        return "break"

    def _drop(self, event):
        raw = event.data.strip()
        if not raw:
            return
        files = re.findall(r'\{(.*?)\}|(\S+)', raw)
        paths = [m[0] or m[1] for m in files]
        paths = [p for p in paths if p]
        for path in paths:
            self.convert_single_pdf(path)


if __name__ == "__main__":
    app = App()
    app.mainloop()
