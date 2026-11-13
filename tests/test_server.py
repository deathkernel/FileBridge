from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from filebridge.server import FileAccessError, _parse_range, resolve_shared_path


class ResolveSharedPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name).resolve()
        (self.root / "Movies").mkdir()
        (self.root / "Movies" / "sample.mp4").write_bytes(b"video")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_resolves_file_inside_shared_folder(self) -> None:
        result = resolve_shared_path(self.root, "Movies/sample.mp4")
        self.assertEqual(result, self.root / "Movies" / "sample.mp4")

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


class FileServerIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        import json
        import threading
        import urllib.request

        self._json = json
        self._threading = threading
        self._request = urllib.request.Request
        self._urlopen = urllib.request.urlopen
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name).resolve()
        (self.root / "clip.mp4").write_bytes(b"0123456789")
        from filebridge.server import create_server

        self.server = create_server(self.root, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp_dir.cleanup()

    def test_directory_listing_returns_file_metadata(self) -> None:
        with self._urlopen(f"{self.base_url}/api/files") as response:
            payload = self._json.loads(response.read().decode("utf-8"))
        self.assertEqual(payload["items"][0]["name"], "clip.mp4")
        self.assertEqual(payload["items"][0]["size"], 10)

    def test_file_server_supports_http_byte_ranges(self) -> None:
        request = self._request(
            f"{self.base_url}/api/file?path=clip.mp4",
            headers={"Range": "bytes=2-5"},
        )
        with self._urlopen(request) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.headers["Content-Range"], "bytes 2-5/10")
            self.assertEqual(response.read(), b"2345")

    def test_file_server_rejects_parent_traversal(self) -> None:
        from urllib.error import HTTPError

        with self.assertRaises(HTTPError) as raised:
            self._urlopen(f"{self.base_url}/api/files?path=..%2Foutside")
        self.assertEqual(raised.exception.code, 400)




if __name__ == "__main__":
    unittest.main()
