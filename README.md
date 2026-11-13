# FileBridge

A lightweight, local Wi-Fi file browser for Windows. Select a folder on your PC, start the server, and browse its contents from an Android phone or another device on the same trusted Wi-Fi network.

## Features

- Desktop control panel to select the shared folder and start/stop the server.
- Browser-based, responsive file manager.
- Browse subfolders without exposing anything outside the selected root folder.
- Search filenames in the current folder.
- Preview common browser-supported formats: images, video, audio, PDF, and text.
- Download any file type.
- HTTP byte-range support for video/audio seeking.
- Python standard library only; no cloud, account, database, or third-party package required.

## Requirements

- Windows 10/11 (Tkinter must be included with your Python installation).
- Python 3.10 or newer.
- Phone and PC connected to the same trusted Wi-Fi network.

## Run on Windows

Open PowerShell in the repository folder:

```powershell
py -3 --version
py -3 main.py
```

1. Click **Choose folder** and select the folder you want to share.
2. Click **Start server**.
3. Open the displayed LAN URL on your phone, for example `http://192.168.1.20:6789`.
4. Browse folders, preview supported files, or download files.

Stop the server from the desktop control panel when you are finished.

## Network and firewall

- FileBridge listens on `0.0.0.0` so devices on the same LAN can connect.
- Allow Python/FileBridge through Windows Firewall on **Private networks only** if Windows asks.
- Do not expose port 6789 through router port forwarding.
- Do not use this unauthenticated HTTP server on public or untrusted Wi-Fi.
- The server is read-only: it does not upload, edit, rename, or delete files.

## Security model

The selected folder is the server's filesystem boundary. Requests are resolved and checked against that root before any file is read. Path traversal attempts and symlinks that resolve outside the selected folder are rejected. Hidden entries are omitted from directory listings.

## Project layout

```text
FileBridge/
├── filebridge/
│   ├── __init__.py
│   ├── desktop.py
│   ├── server.py
│   └── web/
│       ├── app.js
│       ├── index.html
│       └── styles.css
├── tests/
│   └── test_server.py
├── .gitignore
├── main.py
└── README.md
```

## Notes

- Browser playback depends on the media codec. MP4 with H.264/AAC is widely supported; some MKV/AVI codecs may need VLC or another player.
- The PC must remain awake and connected to Wi-Fi while the server is running.
- FileBridge does not copy or move your files. It serves them directly from the selected folder.
