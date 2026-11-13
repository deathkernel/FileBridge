"""Tkinter desktop launcher for FileBridge."""

from __future__ import annotations

import socket
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from http.server import ThreadingHTTPServer

from .server import create_server


DEFAULT_PORT = 6789


def get_lan_ip() -> str:
    """Return the preferred LAN IPv4 address without sending application data."""
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
        self.root.geometry("620x460")
        self.root.minsize(560, 420)
        self.root.configure(bg="#101827")
        self.shared_folder: Path | None = None
        self.server: ThreadingHTTPServer | None = None
        self.server_thread: threading.Thread | None = None
        self.url = ""

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
        style.map("Accent.TButton", background=[("active", "#2563eb")])

        outer = ttk.Frame(self.root, padding=24)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="FileBridge", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="Your private file browser over local Wi-Fi",
        ).pack(anchor="w", pady=(4, 20))

        folder_panel = ttk.Frame(outer, style="Panel.TFrame", padding=18)
        folder_panel.pack(fill="x")
        ttk.Label(folder_panel, text="SHARED FOLDER", style="Muted.TLabel").pack(anchor="w")
        self.folder_label = ttk.Label(
            folder_panel,
            text="No folder selected",
            style="Muted.TLabel",
            wraplength=520,
        )
        self.folder_label.pack(anchor="w", pady=(8, 14))
        ttk.Button(folder_panel, text="Choose folder", command=self._choose_folder).pack(anchor="w")

        settings = ttk.Frame(outer, padding=(0, 18, 0, 0))
        settings.pack(fill="x")
        ttk.Label(settings, text="Port").pack(side="left")
        self.port_var = tk.StringVar(value=str(DEFAULT_PORT))
        self.port_entry = ttk.Entry(settings, textvariable=self.port_var, width=9)
        self.port_entry.pack(side="left", padx=(10, 20))
        self.start_button = ttk.Button(
            settings,
            text="Start server",
            style="Accent.TButton",
            command=self._start_server,
        )
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(settings, text="Stop", command=self._stop_server, state="disabled")
        self.stop_button.pack(side="left", padx=(8, 0))

        status_panel = ttk.Frame(outer, style="Panel.TFrame", padding=18)
        status_panel.pack(fill="x", pady=(18, 0))
        ttk.Label(status_panel, text="SERVER STATUS", style="Muted.TLabel").pack(anchor="w")
        self.status_label = ttk.Label(status_panel, text="Stopped", style="Muted.TLabel")
        self.status_label.pack(anchor="w", pady=(6, 10))
        self.url_label = ttk.Label(status_panel, text="Start the server to see your phone address.", style="Muted.TLabel")
        self.url_label.pack(anchor="w")
        actions = ttk.Frame(status_panel, style="Panel.TFrame")
        actions.pack(anchor="w", pady=(12, 0))
        self.open_button = ttk.Button(actions, text="Open in browser", command=self._open_browser, state="disabled")
        self.open_button.pack(side="left")
        self.copy_button = ttk.Button(actions, text="Copy address", command=self._copy_address, state="disabled")
        self.copy_button.pack(side="left", padx=(8, 0))

        ttk.Label(
            outer,
            text="Only share folders you trust. Use on a trusted private Wi-Fi network; stop the server when finished.",
            wraplength=560,
        ).pack(anchor="w", pady=(18, 0))

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
            self.server = create_server(self.shared_folder, port)
            self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.server_thread.start()
        except (ValueError, OSError) as exc:
            self.server = None
            messagebox.showerror("Could not start server", f"Check the port and try again.\n\n{exc}")
            return

        self.url = f"http://{get_lan_ip()}:{port}"
        self.status_label.configure(text="Running")
        self.url_label.configure(text=f"Open on your phone (same Wi-Fi):\n{self.url}")
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.open_button.configure(state="normal")
        self.copy_button.configure(state="normal")

    def _stop_server(self) -> None:
        server = self.server
        if server is None:
            return
        self.server = None
        server.shutdown()
        server.server_close()
        self.server_thread = None
        self.url = ""
        self.status_label.configure(text="Stopped")
        self.url_label.configure(text="Start the server to see your phone address.")
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
