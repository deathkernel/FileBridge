from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from filebridge.server import FileAccessError, _parse_range, create_server, resolve_shared_path


class ResolveSharedPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name).resolve()
        (self.root / "Movies").mkdir()
        (self.root / "Movies" / "sample.mp4").write_bytes(b"video")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_resolves_file_inside_shared_folder(self) -> None:
        self.assertEqual(resolve_shared_path(self.root, "Movies/sample.mp4"), self.root / "Movies" / "sample.mp4")

    def test_empty_path_resolves_to_shared_root(self) -> None:
        self.assertEqual(resolve_shared_path(self.root, ""), self.root)

    def test_rejects_parent_directory_traversal(self) -> None:
        with self.assertRaises(FileAccessError):
            resolve_shared_path(self.root, "../secret.txt")

    def test_rejects_windows_style_parent_traversal(self) -> None:
        with self.assertRaises(FileAccessError):
            resolve_shared_path(self.root, r"..\secret.txt")

    def test_rejects_absolute_path(self) -> None:
        with self.assertRaises(FileAccessError):
            resolve_shared_path(self.root, str(self.root.parent / "secret.txt"))

    def test_rejects_symlink_outside_root(self) -> None:
        outside = Path(self.temp_dir.name).parent / "filebridge-outside-test.txt"
        outside.write_text("secret", encoding="utf-8")
        link = self.root / "outside-link"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            outside.unlink(missing_ok=True)
            self.skipTest("Symlink creation is not available.")
        try:
            with self.assertRaises(FileAccessError):
                resolve_shared_path(self.root, "outside-link")
        finally:
            link.unlink(missing_ok=True)
            outside.unlink(missing_ok=True)


class ParseRangeTests(unittest.TestCase):
    def test_parses_open_ended_range(self) -> None:
        self.assertEqual(_parse_range("bytes=5-", 10), (5, 9))

    def test_parses_suffix_range(self) -> None:
        self.assertEqual(_parse_range("bytes=-4", 10), (6, 9))

    def test_clamps_end_to_file_size(self) -> None:
        self.assertEqual(_parse_range("bytes=2-100", 10), (2, 9))

    def test_no_range_returns_none(self) -> None:
        self.assertIsNone(_parse_range("", 10))

    def test_rejects_unsatisfiable_range(self) -> None:
        with self.assertRaises(ValueError):
            _parse_range("bytes=20-", 10)

    def test_rejects_multiple_ranges(self) -> None:
        with self.assertRaises(ValueError):
            _parse_range("bytes=0-1,4-5", 10)


class FileServerIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name).resolve()
        (self.root / "clip.mp4").write_bytes(b"0123456789")
        (self.root / "notes.txt").write_text("hello", encoding="utf-8")
        (self.root / ".hidden").write_text("secret", encoding="utf-8")
        self.server = create_server(self.root, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp_dir.cleanup()

    def test_directory_listing_returns_metadata_and_hides_dotfiles(self) -> None:
        with urlopen(f"{self.base_url}/api/files") as response:
            payload = json.loads(response.read().decode("utf-8"))
        names = [item["name"] for item in payload["items"]]
        self.assertIn("clip.mp4", names)
        self.assertNotIn(".hidden", names)

    def test_file_server_supports_http_byte_ranges(self) -> None:
        request = Request(f"{self.base_url}/api/file?path=clip.mp4", headers={"Range": "bytes=2-5"})
        with urlopen(request) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.headers["Content-Range"], "bytes 2-5/10")
            self.assertEqual(response.read(), b"2345")

    def test_file_server_rejects_parent_traversal(self) -> None:
        with self.assertRaises(HTTPError) as raised:
            urlopen(f"{self.base_url}/api/files?path=..%2Foutside")
        self.assertEqual(raised.exception.code, 400)

    def test_write_methods_are_rejected(self) -> None:
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            request = Request(f"{self.base_url}/api/file?path=clip.mp4", method=method)
            with self.assertRaises(HTTPError) as raised:
                urlopen(request)
            self.assertEqual(raised.exception.code, 405)

    def test_file_response_is_inline_and_not_an_attachment(self) -> None:
        with urlopen(f"{self.base_url}/api/file?path=clip.mp4") as response:
            self.assertTrue(response.headers["Content-Disposition"].startswith("inline;"))
            self.assertEqual(response.headers["Accept-Ranges"], "bytes")
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")

    def test_health_endpoint_declares_read_only_mode(self) -> None:
        with urlopen(f"{self.base_url}/api/health") as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(payload["mode"], "read-only")


if __name__ == "__main__":
    unittest.main()
