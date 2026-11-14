import { useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  ArrowDownToLine, CloudUpload, File as FileIcon, FileImage, FileText, Film,
  Folder, FolderPlus, HardDrive, LayoutGrid, List, RefreshCw, Search,
  ShieldCheck, Smartphone, Wifi, X, Pencil, Trash2, Move, Pause, Play, Sun, Moon,
} from "lucide-react";

type Item = {
  name: string; path: string; kind: "file" | "directory"; size: number | null;
  modified: string; mime: string; extension: string;
};
type Transfer = { id: string; name: string; size: number; sent: number; status: string; speed: number; eta: number | null };
type UploadSession = { upload_id: string; chunk_size: number };

async function api<T = any>(url: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    let message = response.statusText;
    try { message = (await response.json()).error || message; } catch { /* keep status text */ }
    throw new Error(message || "Request failed");
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
async function loadFiles(path: string) {
  return api<{ current: string; parent: string; items: Item[] }>(
    "/api/files?" + new URLSearchParams({ path }),
  );
}
function duration(seconds: number | null) {
  if (seconds === null || !Number.isFinite(seconds)) return "Calculating…";
  if (seconds <= 0) return "Almost done";
  const minutes = Math.floor(seconds / 60);
  const remaining = Math.ceil(seconds % 60);
  return minutes ? minutes + "m " + remaining + "s left" : remaining + "s left";
}
function size(value: number | null) {
  if (value === null) return "—";
  if (!value) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), 4);
  return (value / 1024 ** index).toFixed(index ? 1 : 0) + " " + units[index];
}
function Glyph({ item }: { item: Item }) {
  if (item.kind === "directory") return <Folder className="glyph folder" />;
  if (item.mime.startsWith("image/")) return <FileImage className="glyph" />;
  if (item.mime.startsWith("video/") || item.mime.startsWith("audio/")) return <Film className="glyph" />;
  if (item.mime.startsWith("text/") || item.mime === "application/pdf") return <FileText className="glyph" />;
  return <FileIcon className="glyph" />;
}
function json(method: string, body: object): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export default function App() {
  const [path, setPath] = useState("");
  const [search, setSearch] = useState("");
  const [grid, setGrid] = useState(false);
  const [transfers, setTransfers] = useState<Transfer[]>([]);
  const [paused, setPaused] = useState(false);
  const [preview, setPreview] = useState<Item | null>(null);
  const [dragging, setDragging] = useState(false);
  const [sortBy, setSortBy] = useState<"name" | "size" | "modified">("name");
  const [lightTheme, setLightTheme] = useState(false);
  const pauseRef = useRef(false);
  const cancelRef = useRef(false);
  const uploadQueueRef = useRef<Promise<void>>(Promise.resolve());
  const pendingBatchesRef = useRef(0);
  const query = useQuery({ queryKey: ["files", path], queryFn: () => loadFiles(path) });
  const items = useMemo(
    () => (query.data?.items ?? [])
      .filter(item => item.name.toLowerCase().includes(search.toLowerCase()))
      .sort((a, b) => {
        if (a.kind !== b.kind) return a.kind === "directory" ? -1 : 1;
        if (sortBy === "size") return (b.size ?? -1) - (a.size ?? -1);
        if (sortBy === "modified") return b.modified.localeCompare(a.modified);
        return a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
      }),
    [query.data, search, sortBy],
  );
  const crumbs = path ? path.split("/").filter(Boolean) : [];

  function updateTransfer(id: string, patch: Partial<Transfer>) {
    setTransfers(current => current.map(item => item.id === id ? { ...item, ...patch } : item));
  }

  async function uploadFiles(fileList: FileList | File[]) {
    const files = Array.from(fileList);
    if (!files.length) return;
    if (pendingBatchesRef.current === 0) cancelRef.current = false;
    pendingBatchesRef.current += 1;

    const runBatch = async () => {
      try {
        if (cancelRef.current) return;
        for (const file of files) {
          if (cancelRef.current) break;
          const id = crypto.randomUUID();
          const relative = (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
          setTransfers(current => [...current, { id, name: relative, size: file.size, sent: 0, status: "Queued", speed: 0, eta: null }]);
          let session: UploadSession | null = null;
          try {
            session = await api<UploadSession>("/api/upload/init", {
              ...json("POST", { path, relative, size: file.size }),
            });
            let offset = 0;
            let lastTime = performance.now();
            let lastOffset = 0;
            updateTransfer(id, { status: "Uploading" });
            while (offset < file.size) {
              while (pauseRef.current && !cancelRef.current) {
                updateTransfer(id, { status: "Paused" });
                await new Promise(resolve => setTimeout(resolve, 180));
              }
              if (cancelRef.current) throw new Error("Cancelled");
              const end = Math.min(offset + session.chunk_size, file.size);
              const chunk = file.slice(offset, end);
              const response = await fetch("/api/upload/chunk", {
                method: "POST",
                headers: { "X-Upload-Id": session.upload_id, "X-Upload-Offset": String(offset) },
                body: chunk,
              });
              if (!response.ok) {
                let message = response.statusText;
                try { message = (await response.json()).error || message; } catch { /* ignore */ }
                throw new Error(message);
              }
              const result = await response.json();
              offset = result.offset;
              const now = performance.now();
              const elapsed = Math.max((now - lastTime) / 1000, 0.001);
              const speed = (offset - lastOffset) / elapsed;
              updateTransfer(id, { sent: offset, speed, eta: speed > 0 ? (file.size - offset) / speed : null, status: "Uploading" });
              lastTime = now;
              lastOffset = offset;
            }
            await api("/api/upload/complete", json("POST", { upload_id: session.upload_id }));
            updateTransfer(id, { sent: file.size, status: "Complete", speed: 0, eta: 0 });
          } catch (error) {
            if (session) {
              try { await api("/api/upload/cancel", json("POST", { upload_id: session.upload_id })); } catch { /* session may already be gone */ }
            }
            updateTransfer(id, { status: error instanceof Error ? error.message : "Upload failed", speed: 0, eta: null });
            if (cancelRef.current) break;
          }
        }
      } finally {
        pendingBatchesRef.current -= 1;
        if (pendingBatchesRef.current === 0) {
          setPaused(false);
          pauseRef.current = false;
          cancelRef.current = false;
          void query.refetch();
        }
      }
    };

    const queuedBatch = uploadQueueRef.current.then(runBatch, runBatch);
    uploadQueueRef.current = queuedBatch;
    await queuedBatch;
  }
  function togglePause() {
    const next = !pauseRef.current;
    pauseRef.current = next;
    setPaused(next);
  }
  function cancelUploads() {
    cancelRef.current = true;
    pauseRef.current = false;
    setPaused(false);
  }
  async function createFolder() {
    const name = prompt("Folder name");
    if (!name) return;
    try { await api("/api/folder", json("POST", { path, name })); await query.refetch(); }
    catch (error) { alert(error instanceof Error ? error.message : "Could not create folder"); }
  }
  async function renameItem(item: Item) {
    const name = prompt("New name", item.name);
    if (!name || name === item.name) return;
    try { await api("/api/rename", json("POST", { path: item.path, name })); await query.refetch(); }
    catch (error) { alert(error instanceof Error ? error.message : "Could not rename item"); }
  }
  async function moveItem(item: Item) {
    const destination = prompt("Destination folder path (relative to shared folder)", path);
    if (destination === null) return;
    try { await api("/api/move", json("POST", { path: item.path, destination })); await query.refetch(); }
    catch (error) { alert(error instanceof Error ? error.message : "Could not move item"); }
  }
  async function deleteItem(item: Item) {
    if (!confirm(`Permanently delete "${item.name}"?`)) return;
    try { await api("/api/delete", json("POST", { path: item.path })); await query.refetch(); }
    catch (error) { alert(error instanceof Error ? error.message : "Could not delete item"); }
  }
  function fileUrl(item: Item) {
    return "/api/file?" + new URLSearchParams({ path: item.path });
  }
  function previewContent(item: Item) {
    const url = fileUrl(item);
    if (item.mime.startsWith("image/")) return <img className="preview-image" src={url} alt={item.name} />;
    if (item.mime.startsWith("video/")) return <video className="preview-media" src={url} controls />;
    if (item.mime.startsWith("audio/")) return <audio src={url} controls />;
    if (item.mime === "application/pdf") return <iframe className="preview-frame" src={url} title={item.name} />;
    if (item.mime.startsWith("text/") || item.extension === ".json" || item.extension === ".csv") {
      return <iframe className="preview-frame" src={url} title={item.name} />;
    }
    return <p>Preview is not available for this file type. Use Download to save it.</p>;
  }

  return (
    <div className={lightTheme ? "shell light" : "shell"} onDragOver={event => { event.preventDefault(); setDragging(true); }}
      onDragLeave={event => { if (event.currentTarget === event.target) setDragging(false); }}
      onDrop={event => { event.preventDefault(); setDragging(false); void uploadFiles(event.dataTransfer.files); }}>
      <aside className="sidebar">
        <a className="brand"><b>F</b> FileBridge</a><small>WORKSPACE</small>
        <div className="nav active"><HardDrive size={17} /> My files</div>
        <div className="side-bottom"><div className="security"><ShieldCheck /><div><strong>Private session</strong><span>Local network access</span></div></div></div>
      </aside>
      <main>
        <header><div className="mobile-brand"><b>F</b> FileBridge</div>
          <span className="network"><i /><Wifi size={14} /> Local network connected</span>
          <div className="header-actions"><span className="auth"><ShieldCheck size={15} /> Authenticated</span><button className="icon theme-toggle" onClick={() => setLightTheme(value => !value)} aria-label="Toggle color theme">{lightTheme ? <Moon /> : <Sun />}</button></div>
        </header>
        <section className="content">
          <div className="heading"><div><small>YOUR PRIVATE CLOUD</small><h1>My files</h1><p>Everything you need, in one private space.</p></div>
            <label className="primary"><CloudUpload size={17} /> Upload files<input type="file" multiple hidden onChange={event => { if (event.target.files) void uploadFiles(event.target.files); event.target.value = ""; }} /></label>
          </div>
          <div className="stats">
            <article><HardDrive /><span>Items in this folder<strong>{items.length}</strong></span></article>
            <article><Folder /><span>Folders<strong>{items.filter(item => item.kind === "directory").length}</strong></span></article>
            <article><ShieldCheck /><span>Connection<strong className="green">Private</strong></span></article>
          </div>
          <section className="panel">
            <div className="toolbar"><div className="crumbs">
              <button onClick={() => setPath("")}>My files</button>
              {crumbs.map((crumb, index) => <span key={index}>/ <button onClick={() => setPath(crumbs.slice(0, index + 1).join("/"))}>{crumb}</button></span>)}
            </div><div className="tools">
              <label className="search"><Search size={16} /><input placeholder="Search files..." value={search} onChange={event => setSearch(event.target.value)} /></label>
              <button className="icon" aria-label="List view" onClick={() => setGrid(false)}><List /></button>
              <button className="icon" aria-label="Grid view" onClick={() => setGrid(true)}><LayoutGrid /></button>
              <select className="sort-select" aria-label="Sort files" value={sortBy} onChange={event => setSortBy(event.target.value as typeof sortBy)}><option value="name">Name</option><option value="size">Size</option><option value="modified">Modified</option></select>
              <button className="icon" aria-label="Refresh" onClick={() => void query.refetch()}><RefreshCw /></button>
            </div></div>
            <div className="subbar"><span>{items.length} items</span><div>
              <label className="subtle">Upload folder<input type="file" hidden multiple {...({ webkitdirectory: "", directory: "" } as any)}
                onChange={event => { if (event.target.files) void uploadFiles(event.target.files); event.target.value = ""; }} /></label>
              <button className="subtle" onClick={() => void createFolder()}><FolderPlus size={14} /> New folder</button>
            </div></div>
            {query.isLoading ? <div className="empty">Loading files…</div> : query.isError ? <div className="empty error">{query.error.message}</div> :
              !items.length ? <div className="empty"><Folder size={30} /><strong>This folder is empty</strong><span>Upload a file or create a folder to get started.</span></div> :
              <div className={grid ? "grid" : "rows"}>
                {!grid && <div className="table-head"><span>Name</span><span>Size</span><span>Modified</span><span>Actions</span></div>}
                {items.map(item => <motion.div layout key={item.path} className={grid ? "tile" : "file-row"}>
                  <button className="file-name" onClick={() => item.kind === "directory" ? setPath(item.path) : setPreview(item)}>
                    <Glyph item={item} /><span><strong>{item.name}</strong><small>{item.kind === "directory" ? "Folder" : item.mime}</small></span>
                  </button>
                  {!grid && <><span className="meta">{size(item.size)}</span><span className="meta date">{new Date(item.modified).toLocaleString()}</span></>}
                  <div className="item-actions">
                    {item.kind === "directory" ? <a className="download" title="Download ZIP" href={"/api/archive?" + new URLSearchParams({ path: item.path })}><ArrowDownToLine size={16} /></a> :
                      <a className="download" title="Download" href={fileUrl(item) + "&download=1"}><ArrowDownToLine size={16} /></a>}
                    <button className="download" title="Rename" onClick={() => void renameItem(item)}><Pencil size={15} /></button>
                    <button className="download" title="Move" onClick={() => void moveItem(item)}><Move size={15} /></button>
                    <button className="download danger-action" title="Delete" onClick={() => void deleteItem(item)}><Trash2 size={15} /></button>
                  </div>
                </motion.div>)}
              </div>}
          </section>
          <section className="transfer-panel">
            <div className="transfer-heading"><strong>Transfer queue</strong><div>
              <button className="subtle" onClick={togglePause} disabled={!transfers.some(item => item.status === "Uploading" || item.status === "Paused")}>
                {paused ? <Play size={14} /> : <Pause size={14} />} {paused ? "Resume" : "Pause"}
              </button>
              <button className="subtle" onClick={cancelUploads} disabled={!transfers.some(item => item.status === "Uploading" || item.status === "Paused" || item.status === "Preparing" || item.status === "Queued")}>Cancel</button>
              <button className="subtle" onClick={() => setTransfers([])} disabled={transfers.some(item => item.status === "Uploading" || item.status === "Paused" || item.status === "Preparing" || item.status === "Queued")}>Clear</button>
            </div></div>
            {!transfers.length ? <p className="muted">No active or recent transfers.</p> : transfers.map(item =>
              <div className="transfer-row" key={item.id}>
                <div className="transfer-info"><span>{item.name}</span><small>{size(item.sent)} / {size(item.size)} · {item.status} {item.speed > 0 ? "· " + size(item.speed) + "/s" : ""} {item.status === "Uploading" || item.status === "Paused" ? "· " + duration(item.eta) : ""}</small></div>
                <progress value={item.size ? item.sent : 1} max={item.size || 1} />
              </div>)}
          </section>
          <footer><Smartphone size={15} /> Open this address on another device connected to the same Wi-Fi network.</footer>
        </section>
      </main>
      {dragging && <div className="drop-overlay"><CloudUpload size={34} /><strong>Drop files to upload</strong></div>}
      {preview && <div className="preview-overlay" onClick={() => setPreview(null)}>
        <section className="preview-modal" onClick={event => event.stopPropagation()}>
          <div className="preview-top"><div><strong>{preview.name}</strong><small>{size(preview.size)} · {preview.mime}</small></div>
            <button className="icon" onClick={() => setPreview(null)} aria-label="Close preview"><X /></button></div>
          <div className="preview-body">{previewContent(preview)}</div>
          <div className="preview-bottom"><a className="subtle" href={fileUrl(preview) + "&download=1"}><ArrowDownToLine size={14} /> Download</a></div>
        </section>
      </div>}
    </div>
  );
}
