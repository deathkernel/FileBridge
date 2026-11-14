"""Authenticated local-network file server with safe upload and file management."""

from __future__ import annotations

import base64
import hmac
import json
import mimetypes
import os
import re
import secrets
import shutil
import stat
import tempfile
import threading
import zipfile
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlsplit

CHUNK_SIZE = 1024 * 1024
MAX_UPLOAD_BYTES = 5 * 1024 * 1024 * 1024
upload_sessions: dict[str, dict[str, Any]] = {}
upload_lock = threading.Lock()
mimetypes.add_type("video/x-matroska", ".mkv")
mimetypes.add_type("video/mp4", ".m4v")
mimetypes.add_type("audio/flac", ".flac")
mimetypes.add_type("audio/ogg", ".ogg")
mimetypes.add_type("audio/mp4", ".m4a")


class FileAccessError(Exception):
    """Raised when a requested path is outside the selected shared directory."""


def resolve_shared_path(root: Path, relative_path: str = "") -> Path:
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


def _safe_name(name: str) -> str:
    name = name.replace("\\", "/").split("/")[-1].strip()
    if not name or name in {".", ".."} or "\x00" in name or name.startswith("."):
        raise ValueError("Invalid or hidden file name.")
    if any(ord(character) < 32 for character in name):
        raise ValueError("File name contains unsupported characters.")
    return name


def _file_metadata(path: Path, relative_path: str) -> dict[str, Any]:
    info = path.stat()
    mime_type, _ = mimetypes.guess_type(path.name)
    return {"name": path.name, "path": relative_path.replace(os.sep, "/"),
            "kind": "directory" if stat.S_ISDIR(info.st_mode) else "file",
            "size": info.st_size if stat.S_ISREG(info.st_mode) else None,
            "modified": datetime.fromtimestamp(info.st_mtime).astimezone().isoformat(timespec="seconds"),
            "mime": mime_type or "application/octet-stream", "extension": path.suffix.lower()}


def _parse_range(value: str, file_size: int) -> tuple[int, int] | None:
    if not value:
        return None
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value.strip())
    if not match or file_size <= 0:
        raise ValueError("Invalid byte range.")
    first, last = match.groups()
    if not first:
        suffix = int(last or "0")
        if suffix <= 0:
            raise ValueError("Invalid byte range.")
        return max(file_size - suffix, 0), file_size - 1
    start = int(first)
    end = int(last) if last else file_size - 1
    if start >= file_size or end < start:
        raise ValueError("Unsatisfiable byte range.")
    return start, min(end, file_size - 1)


def create_server(shared_folder: str | Path, port: int = 6789, password: str | None = None) -> ThreadingHTTPServer:
    """Create an authenticated HTTP server. Supply a strong per-session password."""
    root = Path(shared_folder).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")
    session_password = password or secrets.token_urlsafe(12)

    class FileBridgeHandler(BaseHTTPRequestHandler):
        server_version = "FileBridge/2.0"
        sys_version = ""

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def end_headers(self) -> None:
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "SAMEORIGIN")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; style-src 'self'; script-src 'self'; object-src 'self'; base-uri 'none'; frame-ancestors 'self'")
            super().end_headers()

        def _send_json(self, payload: Any, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _authorized(self) -> bool:
            header = self.headers.get("Authorization", "")
            try:
                scheme, encoded = header.split(" ", 1)
                username, supplied = base64.b64decode(encoded, validate=True).decode("utf-8").split(":", 1)
            except (ValueError, UnicodeError):
                username, supplied, scheme = "", "", ""
            if scheme.lower() == "basic" and username == "filebridge" and hmac.compare_digest(supplied, session_password):
                return True
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="FileBridge", charset="UTF-8"')
            self.send_header("Content-Length", "0")
            self.end_headers()
            return False

        def _query_path(self) -> str:
            return parse_qs(urlsplit(self.path).query, keep_blank_values=True).get("path", [""])[0]

        def _json_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 64 * 1024:
                raise ValueError("Invalid request body.")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Invalid request body.")
            return payload

        def do_GET(self) -> None:  # noqa: N802
            if not self._authorized():
                return
            route = urlsplit(self.path).path
            if route == "/":
                self._serve_asset("index.html", "text/html; charset=utf-8")
            elif route == "/assets/styles.css":
                self._serve_asset("assets/styles.css", "text/css; charset=utf-8")
            elif route == "/assets/app.js":
                self._serve_asset("assets/app.js", "text/javascript; charset=utf-8")
            elif route == "/api/health":
                self._send_json({"status": "ok", "name": "FileBridge", "mode": "authenticated"})
            elif route == "/api/files":
                self._list_directory(self._query_path())
            elif route == "/api/file":
                download = parse_qs(urlsplit(self.path).query).get("download", ["0"])[0] == "1"
                self._serve_file(self._query_path(), attachment=download)
            elif route == "/api/archive":
                self._serve_archive(self._query_path())
            elif route == "/api/upload/status":
                self._upload_status()
            else:
                self._send_json({"error": "Not found."}, 404)

        def do_HEAD(self) -> None:  # noqa: N802
            if not self._authorized():
                return
            if urlsplit(self.path).path == "/api/file":
                self._serve_file(self._query_path(), attachment=True)
            else:
                self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            if not self._authorized():
                return
            route = urlsplit(self.path).path
            operations = {"/api/upload": self._upload_file, "/api/folder": self._create_folder,
                          "/api/rename": self._rename, "/api/delete": self._delete, "/api/move": self._move}
            operation = operations.get(route)
            if route == "/api/upload/status":
                self._upload_status()
                return
            if route == "/api/upload/init":
                self._upload_init()
                return
            if route == "/api/upload/chunk":
                self._upload_chunk()
                return
            if route == "/api/upload/complete":
                self._upload_complete()
                return
            if route == "/api/upload/cancel":
                self._upload_cancel()
                return
            if operation:
                operation()
            else:
                self._send_json({"error": "Unknown operation."}, 404)

        do_PUT = do_POST
        do_PATCH = do_POST
        do_DELETE = do_POST

        def _serve_asset(self, filename: str, content_type: str) -> None:
            try:
                body = (Path(__file__).parent / "web" / filename).read_bytes()
            except OSError:
                self._send_json({"error": "Web assets are missing."}, 500)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _list_directory(self, relative_path: str) -> None:
            try:
                directory = resolve_shared_path(root, relative_path)
                if not directory.is_dir():
                    self._send_json({"error": "This path is not a folder."}, 400)
                    return
                entries = []
                for child in directory.iterdir():
                    if child.name.startswith("."):
                        continue
                    try:
                        safe_child = resolve_shared_path(root, child.relative_to(root).as_posix())
                        info = safe_child.stat()
                        if stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode):
                            entries.append(_file_metadata(safe_child, safe_child.relative_to(root).as_posix()))
                    except (OSError, FileAccessError, ValueError):
                        continue
                entries.sort(key=lambda item: (item["kind"] != "directory", item["name"].casefold()))
                normalized = relative_path.replace("\\", "/").strip("/")
                parent = str(PurePosixPath(normalized).parent) if normalized else ""
                self._send_json({"current": normalized, "parent": "" if parent == "." else parent, "items": entries})
            except (FileAccessError, OSError):
                self._send_json({"error": "Folder is unavailable or outside the shared folder."}, 400)

        def _serve_file(self, relative_path: str, attachment: bool) -> None:
            try:
                file_path = resolve_shared_path(root, relative_path)
                if not file_path.is_file():
                    self._send_json({"error": "File not found."}, 404)
                    return
                with file_path.open("rb") as handle:
                    opened = os.fstat(handle.fileno())
                    current = resolve_shared_path(root, relative_path).stat()
                    if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
                        raise FileAccessError("File changed while opening.")
                    size = opened.st_size
                    try:
                        byte_range = _parse_range(self.headers.get("Range", ""), size)
                    except ValueError:
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{size}")
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    start, end = byte_range if byte_range else (0, max(size - 1, 0))
                    length = max(end - start + 1, 0)
                    mime, _ = mimetypes.guess_type(file_path.name)
                    self.send_response(206 if byte_range else 200)
                    self.send_header("Content-Type", mime or "application/octet-stream")
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Content-Length", str(length))
                    if byte_range:
                        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                    disposition = "attachment" if attachment else "inline"
                    self.send_header("Content-Disposition", f"{disposition}; filename*=UTF-8''{quote(file_path.name)}")
                    self.end_headers()
                    if self.command == "HEAD":
                        return
                    handle.seek(start)
                    remaining = length
                    while remaining:
                        chunk = handle.read(min(CHUNK_SIZE, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (FileAccessError, OSError, ValueError):
                if not self.wfile.closed:
                    try:
                        self._send_json({"error": "File is unavailable."}, 404)
                    except OSError:
                        pass

        def _upload_init(self) -> None:
            try:
                data = self._json_body()
                size = int(data.get("size", -1))
                relative = str(data.get("relative", data.get("name", ""))).replace("\\", "/")
                parts = PurePosixPath(relative).parts
                if not parts or any(part in ("", ".", "..") for part in parts):
                    raise ValueError("Invalid upload path.")
                clean_parts = [_safe_name(part) for part in parts]
                destination = resolve_shared_path(root, str(data.get("path", "")))
                if not destination.is_dir() or size < 0 or size > MAX_UPLOAD_BYTES:
                    raise ValueError("Invalid upload destination or file size.")
                target_parent = destination
                for folder_name in clean_parts[:-1]:
                    target_parent = resolve_shared_path(root, (target_parent / folder_name).relative_to(root).as_posix())
                    if target_parent.exists() and not target_parent.is_dir():
                        raise ValueError("Upload folder conflicts with an existing file.")
                    target_parent.mkdir(exist_ok=True)
                target_parent = resolve_shared_path(root, target_parent.relative_to(root).as_posix())
                target = target_parent / clean_parts[-1]
                if target.exists():
                    self._send_json({"error": "An item with this name already exists."}, 409)
                    return
                with upload_lock:
                    if len(upload_sessions) >= 8:
                        self._send_json({"error": "Too many active uploads."}, 429)
                        return
                    upload_id = secrets.token_urlsafe(24)
                    fd, temp_name = tempfile.mkstemp(prefix=".filebridge-", suffix=".resume", dir=destination)
                    os.close(fd)
                    upload_sessions[upload_id] = {"path": target, "temp": Path(temp_name), "size": size, "received": 0, "lock": threading.Lock()}
                self._send_json({"upload_id": upload_id, "offset": 0, "chunk_size": 4 * 1024 * 1024})
            except (ValueError, FileAccessError, OSError) as exc:
                self._send_json({"error": str(exc) or "Could not start upload."}, 400)

        def _upload_status(self) -> None:
            upload_id = parse_qs(urlsplit(self.path).query).get("upload_id", [""])[0]
            with upload_lock:
                session = upload_sessions.get(upload_id)
            if not session:
                self._send_json({"error": "Upload session not found."}, 404)
                return
            with session["lock"]:
                self._send_json({"upload_id": upload_id, "offset": session["received"], "size": session["size"]})

        def _upload_chunk(self) -> None:
            upload_id = self.headers.get("X-Upload-Id", "")
            with upload_lock:
                session = upload_sessions.get(upload_id)
            if not session:
                self._send_json({"error": "Upload session not found."}, 404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                offset = int(self.headers.get("X-Upload-Offset", "-1"))
                with session["lock"]:
                    if length <= 0 or length > 4 * 1024 * 1024 or offset != session["received"] or session["received"] + length > session["size"]:
                        self._send_json({"error": "Invalid chunk size or upload offset."}, 409)
                        return
                    with session["temp"].open("ab") as output:
                        remaining = length
                        while remaining:
                            chunk = self.rfile.read(min(CHUNK_SIZE, remaining))
                            if not chunk:
                                raise OSError("Upload connection ended early.")
                            output.write(chunk)
                            remaining -= len(chunk)
                        output.flush()
                    session["received"] += length
                    self._send_json({"ok": True, "offset": session["received"], "size": session["size"]})
            except (ValueError, OSError) as exc:
                self._send_json({"error": str(exc) or "Chunk upload failed."}, 400)

        def _upload_complete(self) -> None:
            data = self._json_body()
            upload_id = str(data.get("upload_id", ""))
            with upload_lock:
                session = upload_sessions.get(upload_id)
            if not session:
                self._send_json({"error": "Upload session not found."}, 404)
                return
            with session["lock"]:
                if session["received"] != session["size"]:
                    self._send_json({"error": "Upload is incomplete."}, 409)
                    return
                if session["path"].exists():
                    self._send_json({"error": "A file with this name already exists."}, 409)
                    return
                os.replace(session["temp"], session["path"])
                with upload_lock:
                    upload_sessions.pop(upload_id, None)
                self._send_json({"ok": True, "item": _file_metadata(session["path"], session["path"].relative_to(root).as_posix())})

        def _upload_cancel(self) -> None:
            data = self._json_body()
            upload_id = str(data.get("upload_id", ""))
            with upload_lock:
                session = upload_sessions.pop(upload_id, None)
            if session:
                with session["lock"]:
                    session["temp"].unlink(missing_ok=True)
            self._send_json({"ok": True})

        def _upload_file(self) -> None:
            temporary: Path | None = None
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > MAX_UPLOAD_BYTES:
                    self._send_json({"error": "Upload must be between 1 byte and 5 GB."}, 413)
                    return
                query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                destination = resolve_shared_path(root, query.get("path", [""])[0])
                if not destination.is_dir():
                    self._send_json({"error": "Upload destination is not a folder."}, 400)
                    return
                relative = unquote(self.headers.get("X-Relative-Path", self.headers.get("X-File-Name", "")))
                parts = PurePosixPath(relative.replace("\\", "/")).parts
                if not parts or any(part in ("", ".", "..") for part in parts):
                    self._send_json({"error": "Invalid upload path."}, 400)
                    return
                clean_parts = [_safe_name(part) for part in parts]
                target_parent = destination
                for folder_name in clean_parts[:-1]:
                    next_folder = resolve_shared_path(root, (target_parent / folder_name).relative_to(root).as_posix())
                    if next_folder.exists() and not next_folder.is_dir():
                        raise ValueError("An upload folder name conflicts with an existing file.")
                    next_folder.mkdir(exist_ok=True)
                    target_parent = resolve_shared_path(root, next_folder.relative_to(root).as_posix())
                target_parent = resolve_shared_path(root, target_parent.relative_to(root).as_posix())
                if not target_parent.is_dir():
                    raise FileAccessError("Invalid upload destination.")
                target = target_parent / clean_parts[-1]
                if target.exists():
                    self._send_json({"error": "A file or folder with this name already exists."}, 409)
                    return
                fd, temp_name = tempfile.mkstemp(prefix=".filebridge-", suffix=".upload", dir=target_parent)
                temporary = Path(temp_name)
                received = 0
                with os.fdopen(fd, "wb") as output:
                    while received < length:
                        chunk = self.rfile.read(min(CHUNK_SIZE, length - received))
                        if not chunk:
                            raise OSError("Upload connection ended early.")
                        output.write(chunk)
                        received += len(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                if target.exists():
                    self._send_json({"error": "Destination appeared during upload."}, 409)
                    return
                os.replace(temporary, target)
                temporary = None
                self._send_json({"ok": True, "item": _file_metadata(target, target.relative_to(root).as_posix())})
            except (ValueError, FileAccessError, OSError) as exc:
                self._send_json({"error": str(exc) or "Upload failed."}, 400)
            finally:
                if temporary:
                    temporary.unlink(missing_ok=True)

        def _create_folder(self) -> None:
            try:
                data = self._json_body()
                parent = resolve_shared_path(root, str(data.get("path", "")))
                name = _safe_name(str(data.get("name", "")))
                if not parent.is_dir():
                    raise ValueError("Parent folder not found.")
                (parent / name).mkdir()
                self._send_json({"ok": True})
            except FileExistsError:
                self._send_json({"error": "An item with this name already exists."}, 409)
            except (ValueError, FileAccessError, OSError) as exc:
                self._send_json({"error": str(exc) or "Could not create folder."}, 400)

        def _rename(self) -> None:
            try:
                data = self._json_body()
                source = resolve_shared_path(root, str(data.get("path", "")))
                if source == root or not source.exists():
                    raise ValueError("Item not found.")
                target = source.with_name(_safe_name(str(data.get("name", ""))))
                if target.exists():
                    raise FileExistsError
                os.rename(source, target)
                self._send_json({"ok": True, "path": target.relative_to(root).as_posix()})
            except FileExistsError:
                self._send_json({"error": "An item with this name already exists."}, 409)
            except (ValueError, FileAccessError, OSError) as exc:
                self._send_json({"error": str(exc) or "Could not rename item."}, 400)

        def _move(self) -> None:
            try:
                data = self._json_body()
                source = resolve_shared_path(root, str(data.get("path", "")))
                destination = resolve_shared_path(root, str(data.get("destination", "")))
                if source == root or not source.exists() or not destination.is_dir():
                    raise ValueError("Source item or destination folder is invalid.")
                if source.is_dir() and destination == source:
                    raise ValueError("A folder cannot be moved into itself.")
                try:
                    destination.relative_to(source)
                    if source.is_dir():
                        raise ValueError("A folder cannot be moved inside itself.")
                except ValueError as exc:
                    if str(exc) == "A folder cannot be moved inside itself.":
                        raise
                target = destination / source.name
                if target.exists():
                    raise FileExistsError
                os.rename(source, target)
                self._send_json({"ok": True, "path": target.relative_to(root).as_posix()})
            except FileExistsError:
                self._send_json({"error": "An item with this name already exists in the destination."}, 409)
            except (ValueError, FileAccessError, OSError) as exc:
                self._send_json({"error": str(exc) or "Could not move item."}, 400)

        def _delete(self) -> None:
            try:
                data = self._json_body()
                target = resolve_shared_path(root, str(data.get("path", "")))
                if target == root or not target.exists():
                    raise ValueError("Item not found.")
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
                self._send_json({"ok": True})
            except (ValueError, FileAccessError, OSError) as exc:
                self._send_json({"error": str(exc) or "Could not delete item."}, 400)

        def _serve_archive(self, relative_path: str) -> None:
            archive_path: Path | None = None
            try:
                folder = resolve_shared_path(root, relative_path)
                if not folder.is_dir():
                    self._send_json({"error": "Select a folder to create a ZIP."}, 400)
                    return
                fd, name = tempfile.mkstemp(prefix="filebridge-", suffix=".zip")
                os.close(fd)
                archive_path = Path(name)
                with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
                    for current, directories, files in os.walk(folder, followlinks=False):
                        current_path = Path(current)
                        directories[:] = [d for d in directories if not d.startswith(".") and not (current_path / d).is_symlink()]
                        for filename in files:
                            source = current_path / filename
                            if filename.startswith(".") or source.is_symlink() or not source.is_file():
                                continue
                            safe = resolve_shared_path(root, source.relative_to(root).as_posix())
                            archive.write(safe, safe.relative_to(folder.parent))
                size = archive_path.stat().st_size
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Length", str(size))
                self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(folder.name or 'shared-folder')}.zip")
                self.end_headers()
                if self.command != "HEAD":
                    with archive_path.open("rb") as archive_file:
                        shutil.copyfileobj(archive_file, self.wfile, CHUNK_SIZE)
            except (FileAccessError, OSError, ValueError):
                if not self.wfile.closed:
                    self._send_json({"error": "Could not create ZIP archive."}, 400)
            finally:
                if archive_path:
                    archive_path.unlink(missing_ok=True)

    server = ThreadingHTTPServer(("0.0.0.0", int(port)), FileBridgeHandler)
    server.daemon_threads = True
    server.allow_reuse_address = True
    server.filebridge_password = session_password
    return server
