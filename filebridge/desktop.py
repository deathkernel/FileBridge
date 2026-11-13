"""Tkinter desktop launcher for authenticated FileBridge."""

from __future__ import annotations

import secrets
import socket
import threading
import tempfile
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from http.server import ThreadingHTTPServer

from .server import create_server

DEFAULT_PORT = 6789


def get_lan_ip() -> str:
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 80))
        address = probe.getsockname()[0]
        if not address.startswith("127."):
            return address
    except OSError:
        pass
    finally:
        probe.close()
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = item[4][0]
            if not address.startswith("127."):
                return address
    except OSError:
        pass
    return "127.0.0.1"


class FileBridgeApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("FileBridge")
        self.root.geometry("650x540")
        self.root.minsize(580, 500)
        self.root.configure(bg="#101827")
        self.shared_folder: Path | None = None
        self.server: ThreadingHTTPServer | None = None
        self.server_thread: threading.Thread | None = None
        self.url = ""
        self.password = ""
        self.qr_image: tk.PhotoImage | None = None
        self.qr_temp_path: Path | None = None
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#101827")
        style.configure("Panel.TFrame", background="#182438")
        style.configure("TLabel", background="#101827", foreground="#e8eef8", font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background="#182438", foreground="#aab8cc", font=("Segoe UI", 9))
        style.configure("Title.TLabel", background="#101827", foreground="#ffffff", font=("Segoe UI Semibold", 22))
        style.configure("TButton", font=("Segoe UI Semibold", 10), padding=(14, 9))
        style.configure("Accent.TButton", background="#3b82f6", foreground="#ffffff")
        outer = ttk.Frame(self.root, padding=24)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="FileBridge", style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text="Private file transfer over your local Wi-Fi").pack(anchor="w", pady=(4, 18))
        panel = ttk.Frame(outer, style="Panel.TFrame", padding=18)
        panel.pack(fill="x")
        ttk.Label(panel, text="SHARED FOLDER", style="Muted.TLabel").pack(anchor="w")
        self.folder_label = ttk.Label(panel, text="No folder selected", style="Muted.TLabel", wraplength=560)
        self.folder_label.pack(anchor="w", pady=(8, 12))
        ttk.Button(panel, text="Choose folder", command=self._choose_folder).pack(anchor="w")
        settings = ttk.Frame(outer, padding=(0, 16, 0, 0))
        settings.pack(fill="x")
        ttk.Label(settings, text="Port").pack(side="left")
        self.port_var = tk.StringVar(value=str(DEFAULT_PORT))
        ttk.Entry(settings, textvariable=self.port_var, width=9).pack(side="left", padx=(10, 20))
        self.start_button = ttk.Button(settings, text="Start server", style="Accent.TButton", command=self._start_server)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(settings, text="Stop", command=self._stop_server, state="disabled")
        self.stop_button.pack(side="left", padx=(8, 0))
        status = ttk.Frame(outer, style="Panel.TFrame", padding=18)
        status.pack(fill="x", pady=(16, 0))
        ttk.Label(status, text="SERVER STATUS", style="Muted.TLabel").pack(anchor="w")
        self.status_label = ttk.Label(status, text="Stopped", style="Muted.TLabel")
        self.status_label.pack(anchor="w", pady=(6, 10))
        self.url_label = ttk.Label(status, text="Start the server to see your phone address.", style="Muted.TLabel")
        self.url_label.pack(anchor="w")
        ttk.Label(status, text="SESSION PASSWORD / PIN", style="Muted.TLabel").pack(anchor="w", pady=(14, 4))
        self.password_label = ttk.Label(status, text="Generated when server starts", style="Muted.TLabel")
        self.password_label.pack(anchor="w")
        self.qr_label = ttk.Label(status, text="QR code appears when server starts.", style="Muted.TLabel")
        self.qr_label.pack(anchor="w", pady=(12, 0))
        self.qr_image_label = ttk.Label(status, style="Muted.TLabel")
        self.qr_image_label.pack(anchor="w", pady=(6, 0))
        actions = ttk.Frame(status, style="Panel.TFrame")
        actions.pack(anchor="w", pady=(12, 0))
        self.open_button = ttk.Button(actions, text="Open in browser", command=self._open_browser, state="disabled")
        self.open_button.pack(side="left")
        self.copy_button = ttk.Button(actions, text="Copy address", command=self._copy_address, state="disabled")
        self.copy_button.pack(side="left", padx=(8, 0))
        ttk.Label(outer, text="Use only trusted private Wi-Fi. Share the session password only with your own devices. Do not enable router port forwarding.", wraplength=580).pack(anchor="w", pady=(16, 0))

    def _choose_folder(self) -> None:
        selected = filedialog.askdirectory(title="Choose a folder to share")
        if selected:
            self.shared_folder = Path(selected).resolve()
            self.folder_label.configure(text=str(self.shared_folder))

    def _start_server(self) -> None:
        if self.server is not None:
            return
        if self.shared_folder is None or not self.shared_folder.is_dir():
            messagebox.showwarning("Choose a folder", "Select the folder you want to share first.")
            return
        try:
            port = int(self.port_var.get())
            if not 1024 <= port <= 65535:
                raise ValueError
            self.password = secrets.token_urlsafe(9)
            self.server = create_server(self.shared_folder, port, self.password)
            self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.server_thread.start()
        except (ValueError, OSError) as exc:
            self.server = None
            messagebox.showerror("Could not start server", f"Check the port and try again.\n\n{exc}")
            return
        self.url = f"http://{get_lan_ip()}:{port}"
        self.status_label.configure(text="Running · authenticated")
        self.url_label.configure(text=f"Phone address (same Wi-Fi):\n{self.url}")
        self.password_label.configure(text=self.password)
        self._show_qr_code()
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.open_button.configure(state="normal")
        self.copy_button.configure(state="normal")

    def _show_qr_code(self) -> None:
        try:
            import qrcode
            image = qrcode.make(self.url)
            handle = tempfile.NamedTemporaryFile(prefix="filebridge-qr-", suffix=".png", delete=False)
            self.qr_temp_path = Path(handle.name)
            handle.close()
            image.save(self.qr_temp_path)
            self.qr_image = tk.PhotoImage(file=str(self.qr_temp_path))
            self.qr_image_label.configure(image=self.qr_image, text="")
            self.qr_label.configure(text="Scan this QR code to open FileBridge. Enter the session password when asked.")
        except (ImportError, OSError, tk.TclError):
            self.qr_label.configure(text="QR unavailable. Install requirements.txt to enable QR display.")
            self.qr_image_label.configure(image="", text="")

    def _stop_server(self) -> None:
        server = self.server
        if server is None:
            return
        self.server = None
        server.shutdown()
        server.server_close()
        if self.server_thread:
            self.server_thread.join(timeout=2)
        self.server_thread = None
        self.url = ""
        self.password = ""
        self.qr_image = None
        self.qr_image_label.configure(image="", text="")
        self.qr_label.configure(text="QR code appears when server starts.")
        if self.qr_temp_path:
            self.qr_temp_path.unlink(missing_ok=True)
            self.qr_temp_path = None
        self.status_label.configure(text="Stopped")
        self.url_label.configure(text="Start the server to see your phone address.")
        self.password_label.configure(text="Generated when server starts")
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.open_button.configure(state="disabled")
        self.copy_button.configure(state="disabled")

    def _open_browser(self) -> None:
        if self.url:
            webbrowser.open(self.url)

    def _copy_address(self) -> None:
        if self.url:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.url)
            self.status_label.configure(text="Running · address copied")

    def _on_close(self) -> None:
        self._stop_server()
        self.root.destroy()


def run_desktop() -> None:
    root = tk.Tk()
    FileBridgeApp(root)
    root.mainloop()
