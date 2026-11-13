const state = { path: "", items: [], query: "", requestId: 0, previewUrl: "" };

const elements = {
  breadcrumbs: document.querySelector("#breadcrumbs"),
  search: document.querySelector("#search"),
  title: document.querySelector("#folder-title"),
  count: document.querySelector("#item-count"),
  list: document.querySelector("#file-list"),
  loading: document.querySelector("#loading"),
  empty: document.querySelector("#empty"),
  error: document.querySelector("#error"),
  refresh: document.querySelector("#refresh"),
  dialog: document.querySelector("#preview-dialog"),
  previewTitle: document.querySelector("#preview-title"),
  previewMeta: document.querySelector("#preview-meta"),
  previewContent: document.querySelector("#preview-content"),
  closePreview: document.querySelector("#close-preview"),
};

function formatBytes(bytes) {
  if (bytes === null || bytes === undefined) return "—";
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / (1024 ** index)).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function fileUrl(path) {
  return `/api/file?${new URLSearchParams({ path }).toString()}`;
}

function iconLabel(item) {
  if (item.kind === "directory") return "DIR";
  return ((item.extension || "").replace(".", "") || "FILE").slice(0, 4);
}

function setError(message = "") {
  elements.error.hidden = !message;
  elements.error.textContent = message;
}

function renderBreadcrumbs() {
  elements.breadcrumbs.replaceChildren();
  const parts = state.path ? state.path.split("/").filter(Boolean) : [];
  const crumbs = [{ label: "Shared folder", path: "" }];
  let current = "";
  for (const part of parts) {
    current = current ? `${current}/${part}` : part;
    crumbs.push({ label: part, path: current });
  }
  crumbs.forEach((crumb, index) => {
    if (index > 0) {
      const separator = document.createElement("span");
      separator.className = "crumb-separator";
      separator.textContent = "/";
      elements.breadcrumbs.append(separator);
    }
    const button = document.createElement("button");
    button.type = "button";
    button.className = `crumb${index === crumbs.length - 1 ? " current" : ""}`;
    button.textContent = crumb.label;
    button.addEventListener("click", () => loadFolder(crumb.path));
    elements.breadcrumbs.append(button);
  });
}

function renderItems() {
  elements.list.replaceChildren();
  const query = state.query.trim().toLocaleLowerCase();
  const visible = state.items.filter((item) => item.name.toLocaleLowerCase().includes(query));
  elements.count.textContent = `${visible.length} item${visible.length === 1 ? "" : "s"}`;
  elements.empty.hidden = visible.length !== 0;
  if (visible.length === 0) return;

  for (const item of visible) {
    const row = document.createElement("div");
    row.className = "file-row";
    const main = document.createElement("div");
    main.className = "file-main";
    const icon = document.createElement("span");
    icon.className = `file-icon${item.kind === "directory" ? " folder" : ""}`;
    icon.textContent = iconLabel(item);

    const textWrap = document.createElement("div");
    textWrap.className = "file-text";
    const name = document.createElement("button");
    name.type = "button";
    name.className = "file-name";
    name.textContent = item.name;
    name.title = item.name;
    name.addEventListener("click", () => item.kind === "directory" ? loadFolder(item.path) : openPreview(item));
    const subtitle = document.createElement("div");
    subtitle.className = "file-subtitle";
    subtitle.textContent = item.kind === "directory" ? "Folder" : (item.mime || "File");
    textWrap.append(name, subtitle);
    main.append(icon, textWrap);

    const size = document.createElement("span");
    size.className = "file-detail";
    size.textContent = item.kind === "directory" ? "—" : formatBytes(item.size);
    const modified = document.createElement("span");
    modified.className = "file-detail modified-detail";
    modified.textContent = item.modified ? new Date(item.modified).toLocaleDateString() : "—";

    const action = document.createElement("button");
    action.type = "button";
    action.className = "row-action";
    action.title = item.kind === "directory" ? "Open folder" : "Preview file";
    action.setAttribute("aria-label", action.title);
    action.textContent = item.kind === "directory" ? "›" : "↗";
    action.addEventListener("click", () => item.kind === "directory" ? loadFolder(item.path) : openPreview(item));
    row.append(main, size, modified, action);
    elements.list.append(row);
  }
}

async function loadFolder(path = "") {
  const requestId = ++state.requestId;
  state.path = path;
  elements.loading.hidden = false;
  elements.list.replaceChildren();
  elements.empty.hidden = true;
  setError();
  renderBreadcrumbs();
  try {
    const response = await fetch(`/api/files?${new URLSearchParams({ path })}`, { cache: "no-store" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Could not load this folder.");
    if (requestId !== state.requestId) return;
    state.items = data.items || [];
    const parts = path.split("/").filter(Boolean);
    elements.title.textContent = parts.length ? parts[parts.length - 1] : "Shared folder";
    renderItems();
  } catch (error) {
    if (requestId !== state.requestId) return;
    state.items = [];
    setError(error.message || "Connection error. Refresh and try again.");
  } finally {
    if (requestId === state.requestId) elements.loading.hidden = true;
  }
}

function closePreview() {
  const media = elements.previewContent.querySelectorAll("video, audio");
  media.forEach((element) => { element.pause(); element.removeAttribute("src"); element.load(); });
  elements.previewContent.replaceChildren();
  if (elements.dialog.open) elements.dialog.close();
}

function openPreview(item) {
  closePreview();
  const url = fileUrl(item.path);
  const mime = item.mime || "application/octet-stream";
  elements.previewTitle.textContent = item.name;
  elements.previewMeta.textContent = `${formatBytes(item.size)} · ${mime}`;
  let preview;

  if (mime.startsWith("image/")) {
    preview = document.createElement("img");
    preview.src = url;
    preview.alt = item.name;
  } else if (mime.startsWith("video/")) {
    preview = document.createElement("video");
    preview.src = url;
    preview.controls = true;
    preview.preload = "metadata";
    preview.playsInline = true;
  } else if (mime.startsWith("audio/")) {
    preview = document.createElement("audio");
    preview.src = url;
    preview.controls = true;
    preview.preload = "metadata";
  } else if (mime === "application/pdf") {
    preview = document.createElement("iframe");
    preview.src = url;
    preview.title = item.name;
    preview.loading = "lazy";
  } else if (mime.startsWith("text/") || ["application/json", "application/xml", "application/javascript"].includes(mime)) {
    preview = document.createElement("pre");
    preview.textContent = "Loading preview…";
    fetch(url, { cache: "no-store" }).then((response) => {
      if (!response.ok) throw new Error("Preview unavailable.");
      const length = Number(response.headers.get("Content-Length") || 0);
      if (length > 500_000) throw new Error("Text preview is limited to 500 KB.");
      return response.text();
    }).then((content) => {
      if (preview.isConnected) preview.textContent = content.slice(0, 500_000);
    }).catch((error) => {
      if (preview.isConnected) preview.textContent = error.message || "Preview unavailable.";
    });
  } else {
    preview = document.createElement("p");
    preview.className = "preview-note";
    preview.textContent = "This format cannot be previewed in your browser. No file changes are made by FileBridge.";
  }
  elements.previewContent.append(preview);
  if (typeof elements.dialog.showModal === "function") elements.dialog.showModal();
  else elements.dialog.setAttribute("open", "");
}

elements.search.addEventListener("input", (event) => {
  state.query = event.target.value;
  renderItems();
});
elements.refresh.addEventListener("click", () => loadFolder(state.path));
elements.closePreview.addEventListener("click", closePreview);
elements.dialog.addEventListener("click", (event) => {
  if (event.target === elements.dialog) closePreview();
});
elements.dialog.addEventListener("close", () => {
  elements.previewContent.querySelectorAll("video, audio").forEach((element) => {
    element.pause();
    element.removeAttribute("src");
    element.load();
  });
});
loadFolder();
