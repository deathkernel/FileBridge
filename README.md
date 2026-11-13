# FileBridge

FileBridge is a Windows desktop utility for authenticated file access and transfer over a trusted local Wi-Fi network. Select one folder on the PC, start the server, and open the displayed LAN address from a phone or another device.

## Phase 1 — Browse and preview

- Browse nested folders and search names.
- Preview images, PDFs, text, and browser-supported media.
- HTTP byte-range support for media seeking.
- File metadata and responsive mobile UI.

## Phase 2 — Secure transfer and file management

- A fresh random session password is generated every time the desktop server starts.
- HTTP Basic authentication protects browser routes and all file operations.
- Upload individual or multiple files; upload a folder while preserving its relative folder structure.
- Download individual files and ZIP archives of folders.
- Create folders, rename and move items, and permanently delete files or folders.
- Uploads use temporary files and atomic placement; existing files are never silently overwritten.
- Upload progress is shown in the browser; uploads are limited to 5 GB per file.
- Standard-library-only Python implementation.

## Requirements and run

- Windows 10/11 and Python 3.10+ with Tkinter.
- Phone and PC on the same trusted private Wi-Fi network.

```powershell
git pull origin main
py -3 main.py
```

Choose a folder, start the server, then open the shown address on your phone. Enter username `filebridge` and the one-session password displayed in the desktop app.

## Safety

- Use only a trusted private Wi-Fi network. Share the session password only with your own devices.
- HTTP Basic authentication is not encryption. Credentials and files travel over plain HTTP and can be observed on an untrusted network. Do not use on public Wi-Fi or the internet.
- Never configure router port forwarding. Allow Python through Windows Firewall on Private networks only.
- Uploads, moves, renames, and deletes modify the selected folder. Deletions are permanent.
- Uploads refuse to overwrite an existing file. A folder upload can partially complete if interrupted; check the destination before retrying.
- ZIP archives are assembled in a temporary file on the PC and removed after sending.
- This is a personal LAN utility, not a hardened multi-user or internet-facing server. Filesystem protections reduce path escape risks but do not eliminate every filesystem race condition.

## Browser notes

Folder upload uses the browser's directory-selection feature (commonly supported in Chromium browsers). Playback depends on browser codecs. Large transfers may be interrupted if a phone sleeps or leaves Wi-Fi range.

## Tests

```powershell
py -3 -m unittest discover -v
```

## Phase 3 — Transfer experience

- Chunked upload API uses 4 MiB blocks.
- Pause and resume work at confirmed chunk boundaries while the page and server stay active.
- Browser queue shows per-file progress and approximate throughput.
- Drag-and-drop adds files to the queue.
- Directory uploads retain nested relative paths.
- The desktop app displays a QR code for the local URL. The session password is never embedded in the QR code.

## Windows executable

GitHub Actions runs a Windows packaging job on pushes to main. Open Actions, choose the latest successful workflow run, and download the FileBridge-Windows-x64 artifact. It is an unsigned portable EXE, not an installer.


## Current release status

The Windows packaging workflow has produced a portable FileBridge-Windows-x64 executable artifact. Download it from the latest successful workflow run under the Actions tab. The executable is not code-signed and is not an installer.

Chunked upload resume is supported while the server process and browser page remain open. Resume does not survive closing the browser tab or restarting the server. HTTPS and end-to-end encrypted transport are not implemented; use a trusted private Wi-Fi network only.
