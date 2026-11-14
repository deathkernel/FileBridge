"""Launch the FileBridge web application from a terminal."""

from __future__ import annotations

import argparse
import secrets
import socket
import ssl
import sys
import webbrowser
from pathlib import Path

from filebridge.server import create_server


def _lan_address() -> str:
    """Return the outbound LAN interface address without sending network data."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start FileBridge as a browser-based file server."
    )
    parser.add_argument(
        "folder",
        nargs="?",
        help="Folder to share (prompted for when omitted).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=6789,
        help="HTTP port to listen on (default: 6789).",
    )
    parser.add_argument(
        "--tls-cert",
        help="Path to a TLS certificate (requires --tls-key).",
    )
    parser.add_argument(
        "--tls-key",
        help="Path to the TLS private key (requires --tls-cert).",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open the browser automatically.",
    )
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    folder_input = args.folder or input("Folder to share: ").strip().strip('"')
    if not folder_input:
        print("No folder selected. Exiting.", file=sys.stderr)
        return 2

    folder = Path(folder_input).expanduser()
    if not folder.exists() or not folder.is_dir():
        print(f"Folder does not exist or is not a directory: {folder}", file=sys.stderr)
        return 2
    if not 1 <= args.port <= 65535:
        print("Port must be between 1 and 65535.", file=sys.stderr)
        return 2
    if bool(args.tls_cert) != bool(args.tls_key):
        print("--tls-cert and --tls-key must be supplied together.", file=sys.stderr)
        return 2

    password = secrets.token_urlsafe(18)
    try:
        server = create_server(folder, port=args.port, password=password)
    except OSError as exc:
        print(f"Could not start FileBridge: {exc}", file=sys.stderr)
        return 1

    scheme = "http"
    if args.tls_cert and args.tls_key:
        try:
            tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            tls_context.minimum_version = ssl.TLSVersion.TLSv1_2
            tls_context.load_cert_chain(args.tls_cert, args.tls_key)
            server.socket = tls_context.wrap_socket(server.socket, server_side=True)
            scheme = "https"
        except (OSError, ssl.SSLError) as exc:
            server.server_close()
            print(f"Could not configure HTTPS: {exc}", file=sys.stderr)
            return 1

    local_url = f"{scheme}://127.0.0.1:{args.port}/"
    lan_url = f"{scheme}://{_lan_address()}:{args.port}/"
    print("\nFileBridge is running.")
    print(f"Shared folder: {folder.resolve()}")
    print(f"Local URL:     {local_url}")
    print(f"LAN URL:       {lan_url}")
    print("Username:      filebridge")
    print(f"Password:      {password}")
    print("\nOpen the LAN URL on a device connected to the same trusted Wi-Fi.")
    print("Keep this terminal open. Press Ctrl+C to stop FileBridge.\n")

    if not args.no_browser:
        webbrowser.open(local_url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping FileBridge...")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
