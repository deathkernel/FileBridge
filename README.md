# FileBridge

FileBridge is a browser-based file manager for transferring files between a Windows PC and devices on the same trusted local Wi-Fi network. The PC runs a small Python HTTP server; users access the application from a desktop or mobile browser. There is no desktop GUI product or EXE launcher.

## Features

- Browse folders and search file names.
- Preview images, PDFs, text, and browser-supported audio/video.
- Download individual files and ZIP archives of folders.
- Upload multiple files and folders while preserving relative paths.
- Chunked uploads with progress, throughput, pause/resume at chunk boundaries, and cancellation while the page and server remain active.
- Create folders, rename, move, and permanently delete items.
- HTTP byte-range support for media seeking.
- Authentication with a fresh random session password on each server start.
- Responsive React web interface.

## Requirements

- Windows 10/11.
- Python 3.10 or newer.
- Node.js 22 or newer only when building the frontend.
- PC and client devices connected to the same trusted private Wi-Fi network.

## Build the web interface

From the repository root:

```powershell
cd frontend
npm install
npm run build
cd ..
```

The production frontend is generated into `filebridge/web`.

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

### HTTPS (optional)

For encrypted browser-to-server traffic, provide a TLS certificate and its private key:

```powershell
py -3 main.py --tls-cert "C:\certs\filebridge.crt" --tls-key "C:\certs\filebridge.key" "C:\Users\YourName\Documents"
```

Use a certificate whose Subject Alternative Names cover the LAN hostname or IP address used by your devices, and install/trust its issuing CA on those devices. A self-signed or mismatched certificate will trigger browser warnings. Without these options, FileBridge uses HTTP.

The terminal displays:
- Local browser URL.
- LAN URL for your phone or another device.
- Username: `filebridge`.
- A randomly generated password for this server session.

The local browser opens automatically unless `--no-browser` is supplied. Enter the displayed username and password when the browser requests authentication. Keep the terminal open while using FileBridge. Press `Ctrl+C` to stop the server.

## Security and safe use

- Use FileBridge only on a trusted private network. Do not expose the port to the public internet.
- Without the optional TLS certificate/key arguments, HTTP Basic authentication is not encryption. Credentials and file contents travel over plain HTTP. Do not use public Wi-Fi or untrusted networks.
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

```powershell
py -3 -m unittest discover -v
```

The GitHub Actions workflow installs Python and frontend dependencies, builds the React web application, compiles Python sources, and runs the test suite. It does not package a Windows desktop executable.
