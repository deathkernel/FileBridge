"""Read-only HTTP file server restricted to one user-selected directory."""

from __future__ import annotations

import json
import mimetypes
import os
import re
import stat
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit

CHUNK_SIZE = 1024 * 1024
MAX_TEXT_PREVIEW_BYTES = 500_000
mimetypes.add_type("video/x-matroska", ".mkv")
mimetypes.add_type("video/mp4", ".m4v")
mimetypes.add_type("audio/flac", ".flac")
mimetypes.add_type("audio/ogg", ".ogg")
mimetypes.add_type("audio/mp4", ".m4a")


class FileAccessError(Exception):
    """Raised when a requested path is outside the selected shared folder."""


def resolve_shared_path(root: Path, relative_path: str = "") -> Path:
    """Resolve a browser path and reject traversal outside the selected root."""
    root = root.resolve(strict=True)
    normalized = relative_path.replace("\\", "/")
    requested = PurePosixPath(normalized)
    if requested.is_absolute() or any(part == ".." for part in requested.parts):
        raise FileAccessError("Path is outside the shared folder.")
    candidate = root.joinpath(*(part for part in requested.parts if part not in ("", ".")))
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise FileAccessError("Path is outside the shared folder.") from exc
    return resolved


def _file_metadata(path: Path, relative_path: str) -> dict[str, Any]:
    info = path.stat()
    mime_type, _ = mimetypes.guess_type(path.name)
    return {
        "name": path.name,
        "path": relative_path.replace(os.sep, "/"),
        "kind": "directory" if stat.S_ISDIR(info.st_mode) else "file",
        "size": info.st_size if stat.S_ISREG(info.st_mode) else None,
        "modified": datetime.fromtimestamp(info.st_mtime).astimezone().isoformat(timespec="seconds"),
        "mime": mime_type or "application/octet-stream",
        "extension": path.suffix.lower(),
    }


def _parse_range(value: str, file_size: int) -> tuple[int, int] | None:
    """Parse one HTTP byte range; reject malformed and unsatisfiable ranges."""
    if not value:
        return None
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value.strip())
    if not match or file_size <= 0:
        raise ValueError("Invalid byte range.")
    first, last = match.groups()
    if not first:
        suffix_length = int(last or "0")
        if suffix_length <= 0:
            raise ValueError("Invalid byte range.")
        return max(file_size - suffix_length, 0), file_size - 1
    start = int(first)
    end = int(last) if last else file_size - 1
    if start >= file_size or end < start:
        raise ValueError("Unsatisfiable byte range.")
    return start, min(end, file_size - 1)


def create_server(shared_folder: str | Path, port: int = 6789) -> ThreadingHTTPServer:
    """Create a read-only HTTP server bound to LAN interfaces."""
    root = Path(shared_folder).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    class FileBridgeHandler(BaseHTTPRequestHandler):
        server_version = "FileBridge/1.0"
        sys_version = ""

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def end_headers(self) -> None:
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "SAMEORIGIN")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; style-src 'self'; script-src 'self'; object-src 'self'; base-uri 'none'; frame-ancestors 'self'")
            super().end_headers()

        def _send_json(self, payload: Any, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _query_path(self) -> str:
            return parse_qs(urlsplit(self.path).query, keep_blank_values=True).get("path", [""])[0]

        def do_GET(self) -> None:  # noqa: N802
            route = urlsplit(self.path).path
            if route == "/":
                self._serve_asset("index.html", "text/html; charset=utf-8")
            elif route == "/assets/styles.css":
                self._serve_asset("styles.css", "text/css; charset=utf-8")
            elif route == "/assets/app.js":
                self._serve_asset("app.js", "text/javascript; charset=utf-8")
            elif route == "/api/health":
                self._send_json({"status": "ok", "name": "FileBridge", "mode": "read-only"})
            elif route == "/api/files":
                self._list_directory(self._query_path())
            elif route == "/api/file":
                self._serve_shared_file(self._query_path())
            else:
                self._send_json({"error": "Not found."}, 404)

        def do_HEAD(self) -> None:  # noqa: N802
            route = urlsplit(self.path).path
            if route == "/api/file":
                self._serve_shared_file(self._query_path())
            elif route == "/api/health":
                self._send_json({"status": "ok", "name": "FileBridge", "mode": "read-only"})
            else:
                self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            self._send_json({"error": "FileBridge is read-only. Write operations are disabled."}, 405)

        do_PUT = do_POST
        do_PATCH = do_POST
        do_DELETE = do_POST

        def _serve_asset(self, filename: str, content_type: str) -> None:
            asset_path = Path(__file__).parent / "web" / filename
            try:
                body = asset_path.read_bytes()
            except OSError:
                self._send_json({"error": "FileBridge web assets are missing."}, 500)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _list_directory(self, relative_path: str) -> None:
            try:
                directory = resolve_shared_path(root, relative_path)
                if not directory.is_dir():
                    self._send_json({"error": "This path is not a folder."}, 400)
                    return
                entries: list[dict[str, Any]] = []
                for child in directory.iterdir():
                    if child.name.startswith("."):
                        continue
                    try:
                        safe_child = resolve_shared_path(root, child.relative_to(root).as_posix())
                        if not safe_child.exists():
                            continue
                        info = safe_child.stat()
                        if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                            continue
                        entries.append(_file_metadata(safe_child, safe_child.relative_to(root).as_posix()))
                    except (OSError, FileAccessError, ValueError):
                        continue
                entries.sort(key=lambda item: (item["kind"] != "directory", item["name"].casefold()))
                normalized = relative_path.replace("\\", "/").strip("/")
                parent = str(PurePosixPath(normalized).parent) if normalized else ""
                if parent == ".":
                    parent = ""
                self._send_json({"current": normalized, "parent": parent, "items": entries})
            except (FileAccessError, OSError):
                self._send_json({"error": "Folder is unavailable or outside the shared folder."}, 400)

        def _serve_shared_file(self, relative_path: str) -> None:
            try:
                file_path = resolve_shared_path(root, relative_path)
                if not file_path.is_file():
                    self._send_json({"error": "File not found."}, 404)
                    return
                # Open before sending headers, then validate the opened file and path again.
                file_handle = file_path.open("rb")
                try:
                    opened_info = os.fstat(file_handle.fileno())
                    current_path = resolve_shared_path(root, relative_path)
                    current_info = current_path.stat()
                    if not stat.S_ISREG(opened_info.st_mode) or not current_path.is_file():
                        raise FileAccessError("Not a regular file.")
                    if (opened_info.st_dev, opened_info.st_ino) != (current_info.st_dev, current_info.st_ino):
                        raise FileAccessError("File changed while opening.")
                    file_size = opened_info.st_size
                    mime_type, _ = mimetypes.guess_type(current_path.name)
                    content_type = mime_type or "application/octet-stream"
                    try:
                        byte_range = _parse_range(self.headers.get("Range", ""), file_size)
                    except ValueError:
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{file_size}")
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    start, end = byte_range if byte_range else (0, max(file_size - 1, 0))
                    length = max(end - start + 1, 0)
                    self.send_response(206 if byte_range else 200)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Content-Length", str(length))
                    self.send_header("Cache-Control", "private, no-store")
                    if byte_range:
                        self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                    self.send_header("Content-Disposition", f"inline; filename*=UTF-8''{quote(current_path.name)}")
                    self.end_headers()
                    if self.command == "HEAD":
                        return
                    file_handle.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = file_handle.read(min(CHUNK_SIZE, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
                finally:
                    file_handle.close()
            except (FileAccessError, OSError, ValueError):
                if not self.wfile.closed:
                    try:
                        self._send_json({"error": "File is unavailable."}, 404)
                    except OSError:
                        pass

    server = ThreadingHTTPServer(("0.0.0.0", int(port)), FileBridgeHandler)
    server.daemon_threads = True
    server.allow_reuse_address = True
    return server
