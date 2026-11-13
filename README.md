# FileBridge

FileBridge is a Windows desktop utility for authenticated file access and transfer over a trusted local Wi-Fi network. The PC selects one folder and runs the server; a phone or another device opens the displayed LAN address.

## Phase 1 — Browse and preview

- Browse nested folders and search names.
- Preview images, PDFs, text, and browser-supported media.
- HTTP byte-range support for media seeking.
- File metadata and responsive mobile UI.

## Phase 2 — Transfer and manage

- A fresh random session password is generated every time the desktop server starts.
- HTTP Basic authentication protects browser routes and file operations.
- Upload individual or multiple files; upload a folder while preserving its relative folder structure.
- Download individual files and ZIP archives of folders.
- Create folders, rename items, and permanently delete files or folders.
- Uploads are written to a temporary file and atomically moved into place; existing files are never silently overwritten.
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

- Use only a trusted private Wi-Fi network. The session password is shown on the PC; do not share it with untrusted devices.
- HTTP Basic authentication is not encryption. Anyone able to observe unencrypted traffic on the LAN may be able to capture credentials and files. Do not use this over public Wi-Fi or the internet.
- Never configure router port forwarding for FileBridge.
- Allow Python through Windows Firewall on Private networks only.
- Uploads, renames, and deletes modify the selected folder. Deleted files are not moved to the recycle bin.
- Uploads refuse to overwrite an existing file. A folder upload may partially complete if the connection fails; retry after checking the destination.
- Upload size is limited to 5 GB per file.
- ZIP archives are assembled in a temporary file on the PC and removed after sending.
- This is a personal LAN utility, not a hardened multi-user or internet-facing server. Filesystem protections reduce path escape risks but do not eliminate every filesystem race condition.

## Browser support

Folder upload uses the browser's directory-selection feature (commonly available in Chromium browsers). Video and audio playback depends on codecs supported by the browser. Large uploads may be interrupted if the phone sleeps or leaves Wi-Fi range.

## Tests

```powershell
py -3 -m unittest discover -v
```
