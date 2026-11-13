# FileBridge

FileBridge is a lightweight, read-only local Wi-Fi file browser for Windows. Select a folder on your PC, start the desktop server, and browse or preview its contents from a phone or another device on the same trusted Wi-Fi network.

## Phase 1: Read and view

- Desktop control panel to select one shared folder and start/stop the server.
- Responsive browser interface for phones, tablets and PCs.
- Browse nested folders and search names in the current folder.
- Preview images, PDFs and text-based files.
- Stream browser-supported video and audio with HTTP byte-range seeking.
- Metadata display (file size and modified date).
- No uploads, downloads, edits, renames, moves or deletes.
- Python standard library only; no cloud account, database or third-party package.

## Requirements

- Windows 10/11 (Tkinter must be included with Python).
- Python 3.10 or newer.
- Phone and PC connected to the same trusted private Wi-Fi network.

## Run on Windows

Open PowerShell in the repository folder:

```powershell
py -3 --version
py -3 main.py
```

1. Click **Choose folder** and select the folder you want to share.
2. Click **Start server**.
3. Open the displayed LAN URL on your phone, for example `http://192.168.1.20:6789`.
4. Browse folders and preview supported files.
5. Stop the server from the desktop control panel when finished.

## Network safety

- FileBridge listens on `0.0.0.0` so devices on the same LAN can connect.
- Allow Python/FileBridge through Windows Firewall on **Private networks only**.
- Do not expose port 6789 through router port forwarding.
- Do not use this unauthenticated HTTP server on public or untrusted Wi-Fi.
- Share only a folder whose contents you are comfortable making visible to devices on that Wi-Fi.
- Keep the PC awake and connected to Wi-Fi while the server is running.
- Stop the server when you are finished.

## Read-only and security behavior

- The selected folder is the filesystem boundary for browsing and reads.
- Parent traversal and symlinks resolving outside the selected folder are rejected.
- Hidden entries are omitted from listings.
- Only regular files and directories are listed.
- HTTP write methods are explicitly rejected with `405 Method Not Allowed`.
- File responses are inline and support byte ranges for media seeking.
- FileBridge does not alter or copy the shared files.

This is a personal LAN utility, not an internet-facing file server. The current HTTP connection has no login or encryption; use it only on a trusted private network. Filesystem checks reduce path-escape risk, but do not treat this as a hardened multi-user service.

## Browser compatibility

Playback depends on the browser and media codec. MP4 with H.264/AAC is widely supported; some MKV/AVI codecs may not play in a mobile browser. PDF preview also depends on built-in browser PDF support. Unsupported formats remain visible but cannot be previewed in the browser.

## Development

Run tests:

```powershell
py -3 -m unittest discover -v
```
