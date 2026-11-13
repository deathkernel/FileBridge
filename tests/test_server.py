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


if __name__ == "__main__":
    unittest.main()
