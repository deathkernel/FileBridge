"""Start the FileBridge web server from the command line."""

from __future__ import annotations

import argparse
import secrets
import socket
import webbrowser
from pathlib import Path

from filebridge.server import create_server


def local_ip() -> str:
    """Return the LAN address selected by the active default route."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 80))
        return str(probe.getsockname()[0])
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the FileBridge private web app")
    parser.add_argument("folder", nargs="?", default=".", help="Folder to share (default: current directory)")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (default: all network interfaces)")
    parser.add_argument("--port", type=int, default=6789, help="Web server port (default: 6789)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser automatically")
    args = parser.parse_args()

    shared = Path(args.folder).expanduser().resolve(strict=True)
    password = secrets.token_urlsafe(12)
    server = create_server(shared, args.port, password)
    address = f"http://127.0.0.1:{server.server_address[1]}"
    lan_address = f"http://{local_ip()}:{server.server_address[1]}"

    print("\\nFileBridge Web is running")
    print(f"Shared folder : {shared}")
    print(f"Local URL     : {address}")
    print(f"Phone URL     : {lan_address}")
    print("Username      : filebridge")
    print(f"Password      : {password}")
    print("\\nPress Ctrl+C to stop FileBridge. Use only a trusted private Wi-Fi network.")
    if not args.no_browser:
        webbrowser.open(address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\\nStopping FileBridge…")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
