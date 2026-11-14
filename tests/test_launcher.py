from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import main


class LauncherTests(unittest.TestCase):
    def test_requires_a_folder(self) -> None:
        output = io.StringIO()
        with patch.object(sys, "argv", ["main.py"]), patch("builtins.input", return_value=""):
            with contextlib.redirect_stderr(output):
                result = main.main()
        self.assertEqual(result, 2)
        self.assertIn("No folder selected", output.getvalue())

    def test_rejects_missing_folder(self) -> None:
        output = io.StringIO()
        with patch.object(sys, "argv", ["main.py", "missing-folder"]):
            with contextlib.redirect_stderr(output):
                result = main.main()
        self.assertEqual(result, 2)
        self.assertIn("does not exist", output.getvalue())

    def test_starts_web_server_and_opens_local_browser(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            server = Mock()
            output = io.StringIO()
            with (
                patch.object(sys, "argv", ["main.py", folder]),
                patch.object(main, "create_server", return_value=server) as create_server,
                patch.object(main, "_lan_address", return_value="192.168.1.20"),
                patch.object(main.webbrowser, "open") as open_browser,
                contextlib.redirect_stdout(output),
            ):
                result = main.main()

        self.assertEqual(result, 0)
        create_server.assert_called_once()
        self.assertEqual(create_server.call_args.args[0], Path(folder))
        self.assertEqual(create_server.call_args.kwargs["port"], 6789)
        self.assertTrue(create_server.call_args.kwargs["password"])
        server.serve_forever.assert_called_once()
        server.server_close.assert_called_once()
        open_browser.assert_called_once_with("http://127.0.0.1:6789/")
        self.assertIn("http://192.168.1.20:6789/", output.getvalue())
        self.assertIn("Username:      filebridge", output.getvalue())


if __name__ == "__main__":
    unittest.main()
