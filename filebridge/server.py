"""HTTP file server restricted to one user-selected directory."""

from __future__ import annotations

import json
import mimetypes
import os
import re
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit


CHUNK_SIZE = 1024 * 1024
mimetypes.add_type("video/x-matroska", ".mkv")
mimetypes.add_type("video/mp4", ".m4v")
mimetypes.add_type("audio/flac", ".flac")
mimetypes.add_type("audio/ogg", ".ogg")


class FileAccessError(Exception):
    """Raised when a requested path is outside the selected shared folder."""


def resolve_shared_path(root: Path, relative_path: str = "") -> Path:
    """Resolve a browser path and reject traversal outside the selected root."""
    root = root.resolve(strict=True)
    normalized = relative_path.replace("\\", "/")
    requested = PurePosixPath(normalized)

    if requested.is_absolute() or any(part == ".." for part in requested.parts):
        raise FileAccessError("Path is outside the shared folder.")

    candidate = root.joinpath(*[part for part in requested.parts if part not in ("", ".")])
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise FileAccessError("Path is outside the shared folder.") from exc

    return resolved


def _file_metadata(path: Path, relative_path: str) -> dict[str, Any]:
    stat = path.stat()
    mime_type, _ = mimetypes.guess_type(path.name)
    return {
        "name": path.name,
        "path": relative_path.replace(os.sep, "/"),
        "kind": "directory" if path.is_dir() else "file",
        "size": stat.st_size if path.is_file() else None,
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "mime": mime_type or "application/octet-stream",
        "extension": path.suffix.lower(),
    }


def _parse_range(value: str, file_size: int) -> tuple[int, int] | None:
    """Parse a single HTTP byte range. Return None when no range was requested."""
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
        start = max(file_size - suffix_length, 0)
        end = file_size - 1
    else:
        start = int(first)
        end = int(last) if last else file_size - 1
        if start >= file_size or end < start:
            raise ValueError("Unsatisfiable byte range.")
        end = min(end, file_size - 1)
    return start, end


def create_server(shared_folder: str | Path, port: int = 6789) -> ThreadingHTTPServer:
    """Create a threaded HTTP server bound to all LAN interfaces."""
    root = Path(shared_folder).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    class FileBridgeHandler(BaseHTTPRequestHandler):
        server_version = "FileBridge/0.1"

        def log_message(self, fmt: str, *args: Any) -> None:
            # Keep request logs out of the desktop console by default.
            return

        def _send_json(self, payload: Any, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _query_path(self) -> str:
            return parse_qs(urlsplit(self.path).query).get("path", [""])[0]

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            parsed = urlsplit(self.path)
            route = parsed.path

            if route == "/":
                self._serve_asset("index.html", "text/html; charset=utf-8")
                return
            if route == "/assets/styles.css":
                self._serve_asset("styles.css", "text/css; charset=utf-8")
                return
            if route == "/assets/app.js":
                self._serve_asset("app.js", "text/javascript; charset=utf-8")
                return
            if route == "/api/health":
                self._send_json({"status": "ok", "name": "FileBridge"})
                return
            if route == "/api/files":
                self._list_directory(self._query_path())
                return
            if route == "/api/file":
                self._serve_shared_file(self._query_path(), parse_qs(parsed.query).get("download", ["0"])[0] == "1")
                return

            self._send_json({"error": "Not found."}, 404)

        def _serve_asset(self, filename: str, content_type: str) -> None:
            asset_path = Path(__file__).parent / "web" / filename
            try:
                body = asset_path.read_bytes()
            except OSError:
                self.send_error(500, "FileBridge web assets are missing.")
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
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
                        child_resolved = resolve_shared_path(root, child.relative_to(root).as_posix())
                        if not child_resolved.exists():
                            continue
                        child_relative = child_resolved.relative_to(root).as_posix()
                        entries.append(_file_metadata(child_resolved, child_relative))
                    except (OSError, FileAccessError, ValueError):
                        continue
                entries.sort(key=lambda item: (item["kind"] != "directory", item["name"].casefold()))
                self._send_json({
                    "current": relative_path.replace("\\", "/").strip("/"),
                    "parent": str(PurePosixPath(relative_path.replace("\\", "/")).parent)
                    if relative_path and str(PurePosixPath(relative_path.replace("\\", "/")).parent) != "."
                    else "",
                    "items": entries,
                })
            except (FileAccessError, OSError) as exc:
                self._send_json({"error": str(exc)}, 400)

        def _serve_shared_file(self, relative_path: str, download: bool) -> None:
            try:
                file_path = resolve_shared_path(root, relative_path)
                if not file_path.is_file():
                    self._send_json({"error": "File not found."}, 404)
                    return
                file_size = file_path.stat().st_size
                mime_type, _ = mimetypes.guess_type(file_path.name)
                content_type = mime_type or "application/octet-stream"
                range_header = self.headers.get("Range", "")
                try:
                    byte_range = _parse_range(range_header, file_size)
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
                if byte_range:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                disposition = "attachment" if download else "inline"
                self.send_header(
                    "Content-Disposition",
                    f"{disposition}; filename*=UTF-8''{quote(file_path.name)}",
                )
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()

                if self.command == "HEAD":
                    return
                with file_path.open("rb") as file_handle:
                    file_handle.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = file_handle.read(min(CHUNK_SIZE, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (FileAccessError, OSError, ValueError):
                self._send_json({"error": "File is unavailable."}, 404)

        def do_HEAD(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            parsed = urlsplit(self.path)
            if parsed.path == "/api/file":
                self._serve_shared_file(self._query_path(), False)
            else:
                self.send_error(404)

    server = ThreadingHTTPServer(("0.0.0.0", int(port)), FileBridgeHandler)
    server.daemon_threads = True
    server.allow_reuse_address = True
    return server
