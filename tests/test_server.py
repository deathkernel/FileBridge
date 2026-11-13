from __future__ import annotations

import base64
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from filebridge.server import FileAccessError, _parse_range, create_server, resolve_shared_path


class FileBridgeIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name).resolve()
        (self.root / "clip.mp4").write_bytes(b"0123456789")
        (self.root / "notes.txt").write_text("hello", encoding="utf-8")
        (self.root / ".hidden").write_text("secret", encoding="utf-8")
        (self.root / "destination").mkdir()
        self.server = create_server(self.root, 0, "test-secret")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.auth = "Basic " + base64.b64encode(b"filebridge:test-secret").decode()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp_dir.cleanup()

    def request(self, path: str, method: str = "GET", body: bytes | None = None, headers: dict | None = None):
        request_headers = {"Authorization": self.auth}
        request_headers.update(headers or {})
        return urlopen(Request(self.base + path, data=body, headers=request_headers, method=method))

    def json_post(self, route: str, payload: dict):
        body = json.dumps(payload).encode()
        return self.request(route, "POST", body, {"Content-Length": str(len(body))})

    def test_requires_authentication(self) -> None:
        with self.assertRaises(HTTPError) as raised:
            urlopen(self.base + "/api/files")
        self.assertEqual(raised.exception.code, 401)

    def test_lists_files_and_hides_hidden_entries(self) -> None:
        with self.request("/api/files") as response:
            data = json.loads(response.read())
        names = [item["name"] for item in data["items"]]
        self.assertIn("clip.mp4", names)
        self.assertNotIn(".hidden", names)

    def test_supports_byte_range(self) -> None:
        with self.request("/api/file?path=clip.mp4", headers={"Range": "bytes=2-5"}) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.read(), b"2345")

    def test_uploads_file(self) -> None:
        with self.request("/api/upload", "POST", b"payload", {"X-Relative-Path": "incoming.txt", "Content-Length": "7"}) as response:
            self.assertTrue(json.loads(response.read())["ok"])
        self.assertEqual((self.root / "incoming.txt").read_bytes(), b"payload")

    def test_uploads_nested_folder_path_and_decodes_names(self) -> None:
        with self.request("/api/upload", "POST", b"data", {"X-Relative-Path": "My%20Folder/sub%20folder/hello%20world.txt", "Content-Length": "4"}) as response:
            self.assertTrue(json.loads(response.read())["ok"])
        self.assertEqual((self.root / "My Folder" / "sub folder" / "hello world.txt").read_bytes(), b"data")

    def test_upload_rejects_overwrite(self) -> None:
        with self.assertRaises(HTTPError) as raised:
            self.request("/api/upload", "POST", b"new", {"X-Relative-Path": "notes.txt", "Content-Length": "3"})
        self.assertEqual(raised.exception.code, 409)

    def test_upload_rejects_parent_traversal(self) -> None:
        with self.assertRaises(HTTPError) as raised:
            self.request("/api/upload", "POST", b"x", {"X-Relative-Path": "../escape.txt", "Content-Length": "1"})
        self.assertEqual(raised.exception.code, 400)

    def test_creates_renames_and_deletes_folder(self) -> None:
        with self.json_post("/api/folder", {"path": "", "name": "new-folder"}) as response:
            self.assertTrue(json.loads(response.read())["ok"])
        with self.json_post("/api/rename", {"path": "new-folder", "name": "renamed"}) as response:
            self.assertTrue(json.loads(response.read())["ok"])
        with self.json_post("/api/delete", {"path": "renamed"}) as response:
            self.assertTrue(json.loads(response.read())["ok"])
        self.assertFalse((self.root / "renamed").exists())

    def test_moves_item_between_folders(self) -> None:
        with self.json_post("/api/move", {"path": "notes.txt", "destination": "destination"}) as response:
            self.assertTrue(json.loads(response.read())["ok"])
        self.assertTrue((self.root / "destination" / "notes.txt").exists())

    def test_rejects_move_into_descendant(self) -> None:
        (self.root / "parent" / "child").mkdir(parents=True)
        with self.assertRaises(HTTPError) as raised:
            self.json_post("/api/move", {"path": "parent", "destination": "parent/child"})
        self.assertEqual(raised.exception.code, 400)

    def test_file_preview_is_inline(self) -> None:
        with self.request("/api/file?path=notes.txt") as response:
            self.assertTrue(response.headers["Content-Disposition"].startswith("inline;"))

    def test_file_download_is_attachment(self) -> None:
        with self.request("/api/file?path=notes.txt&download=1") as response:
            self.assertTrue(response.headers["Content-Disposition"].startswith("attachment;"))

    def test_folder_archive_is_zip(self) -> None:
        with self.request("/api/archive?path=") as response:
            self.assertEqual(response.headers["Content-Type"], "application/zip")
            self.assertTrue(response.read().startswith(b"PK"))

    def test_write_operations_reject_unauthorized_request(self) -> None:
        request = Request(self.base + "/api/delete", data=b'{"path":"notes.txt"}', method="POST")
        with self.assertRaises(HTTPError) as raised:
            urlopen(request)
        self.assertEqual(raised.exception.code, 401)


class PathAndRangeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name).resolve()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_resolves_root(self) -> None:
        self.assertEqual(resolve_shared_path(self.root, ""), self.root)

    def test_rejects_parent_traversal(self) -> None:
        with self.assertRaises(FileAccessError):
            resolve_shared_path(self.root, "../secret")

    def test_rejects_windows_parent_traversal(self) -> None:
        with self.assertRaises(FileAccessError):
            resolve_shared_path(self.root, r"..\secret")

    def test_parses_ranges(self) -> None:
        self.assertEqual(_parse_range("bytes=2-5", 10), (2, 5))
        self.assertEqual(_parse_range("bytes=-4", 10), (6, 9))
        self.assertEqual(_parse_range("", 10), None)

    def test_rejects_invalid_range(self) -> None:
        with self.assertRaises(ValueError):
            _parse_range("bytes=20-", 10)


if __name__ == "__main__":
    unittest.main()
