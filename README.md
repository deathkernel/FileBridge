# FileBridge

FileBridge is a browser-based file manager for transferring files between a Windows PC and devices on the same trusted local Wi-Fi network. The PC runs a small Python HTTP server; users access the application from a desktop or mobile browser. FileBridge is not a desktop GUI application and does not provide a Windows EXE launcher.

## Features

- Browse folders and search file names.
- Preview images, PDFs, text, and browser-supported audio/video.
- Download individual files and ZIP archives of folders.
- Upload multiple files and folders while preserving relative paths.
- Chunked uploads with progress, throughput, pause/resume at chunk boundaries, and cancellation while the page and server remain active.
- Create folders, rename, move, and permanently delete items.
- HTTP byte-range support for media seeking.
- No-login access by default on the trusted local network.
- Responsive React web interface with dark and light themes.

## Requirements

- Windows 10/11.
- Python 3.10 or newer.
- Node.js 22 or newer only when building the frontend.
- PC and client devices connected to the same trusted private Wi-Fi network.

The Python backend uses only the Python standard library. No Python package installation is required to run the browser-based server.

## Build the web interface

From the repository root, when changing the frontend:

```powershell
cd frontend
npm install
npm run build
cd ..
```

The production frontend is generated into `filebridge/web`. The GitHub Actions workflow also builds and publishes these production assets to the main branch after the Linux and Windows checks pass.

## Start FileBridge

From CMD or PowerShell, in the repository root:

```powershell
py -3 main.py
```

When prompted, enter the folder you want to share. You can also pass it directly:

```powershell
py -3 main.py "C:\Users\YourName\Documents"
```

Optional arguments:

```powershell
py -3 main.py --port 6789 --no-browser "C:\Users\YourName\Documents"
```

The server opens the local browser automatically unless `--no-browser` is supplied. The terminal displays the local URL and the LAN URL to open on your phone or another device connected to the same Wi-Fi network. **The standard launcher does not ask for a username or password.** Keep the terminal open while using FileBridge. Press `Ctrl+C` to stop the server.

## HTTPS (optional)

For encrypted browser-to-server traffic, provide a TLS certificate and its private key:

```powershell
py -3 main.py --tls-cert "C:\certs\filebridge.crt" --tls-key "C:\certs\filebridge.key" "C:\Users\YourName\Documents"
```

Use a certificate whose Subject Alternative Names cover the LAN hostname or IP address used by your devices, and install/trust its issuing CA on those devices. A self-signed or mismatched certificate will trigger browser warnings. Without these options, FileBridge uses HTTP.

## Security and safe use

- Use FileBridge only on a trusted private network. Do not expose the port to the public internet.
- Login is disabled in the standard launcher. Anyone on the same reachable LAN can list, download, upload, rename, move, and delete files in the shared folder. Use only a trusted private Wi-Fi network; do not use public Wi-Fi or expose the port to the internet.
- HTTPS requires a valid certificate trusted by every connecting device. TLS protects traffic in transit but does not turn this personal LAN utility into an internet-facing service.
- Do not configure router port forwarding.
- Allow Python through Windows Firewall on Private networks only, if Windows asks.
- Uploads, moves, renames, and deletes modify the selected shared folder. Deletions are permanent.
- Uploads refuse to overwrite an existing file.
- The server limits uploads to 5 GiB per file and uses chunked uploads.
- This is a personal LAN utility, not a hardened multi-user or internet-facing file server.

## Browser notes

Folder upload depends on browser directory-selection support, commonly available in Chromium-based browsers. Media playback depends on browser codecs. Transfers can be interrupted if a phone sleeps or leaves Wi-Fi range. Upload resume is limited to the active server process and browser page; it does not survive closing the tab or restarting the server.

## Tests

From the repository root:

```powershell
py -3 -m unittest discover -v
```

The GitHub Actions workflow performs the frontend production build and Python unit/integration tests on both Linux and Windows. It does not package a Windows desktop executable.
