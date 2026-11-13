const state = { path: "", items: [], query: "", requestId: 0, uploading: 0 };
const el = Object.fromEntries(["breadcrumbs","search","title","count","list","loading","empty","error","refresh","dialog","previewTitle","previewMeta","previewContent","closePreview","uploadFiles","uploadFolder","uploadStatus","newFolder","zipFolder"].map(id => [id, document.getElementById(id)]));

function formatBytes(bytes) {
  if (bytes === null || bytes === undefined) return "—";
  if (!bytes) return "0 B";
  const units = ["B","KB","MB","GB","TB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / (1024 ** index)).toFixed(index ? 1 : 0)} ${units[index]}`;
}
function fileUrl(path) { return `/api/file?${new URLSearchParams({path})}`; }
function setError(message = "") { el.error.hidden = !message; el.error.textContent = message; }
function requestJson(url, method = "GET", body = null) {
  return fetch(url, { method, headers: body ? {"Content-Type":"application/json"} : {}, body: body ? JSON.stringify(body) : undefined })
    .then(async response => { const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`); return data; });
}
function renderBreadcrumbs() {
  el.breadcrumbs.replaceChildren();
  const parts = state.path ? state.path.split("/").filter(Boolean) : [];
  const crumbs = [{label:"Shared folder",path:""}]; let current = "";
  parts.forEach(part => { current = current ? `${current}/${part}` : part; crumbs.push({label:part,path:current}); });
  crumbs.forEach((crumb,index) => {
    if (index) { const sep=document.createElement("span"); sep.className="crumb-separator"; sep.textContent="/"; el.breadcrumbs.append(sep); }
    const button=document.createElement("button"); button.type="button"; button.className=`crumb${index===crumbs.length-1?" current":""}`; button.textContent=crumb.label;
    button.addEventListener("click",()=>loadFolder(crumb.path)); el.breadcrumbs.append(button);
  });
}
function actionButton(label, title, callback) {
  const button=document.createElement("button"); button.type="button"; button.className="row-action"; button.textContent=label; button.title=title; button.setAttribute("aria-label",title); button.addEventListener("click",callback); return button;
}
function renderItems() {
  el.list.replaceChildren();
  const query=state.query.trim().toLocaleLowerCase();
  const visible=state.items.filter(item=>item.name.toLocaleLowerCase().includes(query));
  el.count.textContent=`${visible.length} item${visible.length===1?"":"s"}`;
  el.empty.hidden=visible.length!==0;
  visible.forEach(item=>{
    const row=document.createElement("div"); row.className="file-row";
    const main=document.createElement("div"); main.className="file-main";
    const icon=document.createElement("span"); icon.className=`file-icon${item.kind==="directory"?" folder":""}`; icon.textContent=item.kind==="directory"?"DIR":((item.extension||"FILE").replace(".","").slice(0,4));
    const wrap=document.createElement("div"); wrap.className="file-text";
    const name=document.createElement("button"); name.type="button"; name.className="file-name"; name.textContent=item.name; name.title=item.name;
    name.addEventListener("click",()=>item.kind==="directory"?loadFolder(item.path):openPreview(item));
    const sub=document.createElement("div"); sub.className="file-subtitle"; sub.textContent=item.kind==="directory"?"Folder":(item.mime||"File"); wrap.append(name,sub); main.append(icon,wrap);
    const size=document.createElement("span"); size.className="file-detail"; size.textContent=item.kind==="directory"?"—":formatBytes(item.size);
    const modified=document.createElement("span"); modified.className="file-detail modified-detail"; modified.textContent=item.modified?new Date(item.modified).toLocaleDateString():"—";
    const actions=document.createElement("div"); actions.className="row-actions";
    if(item.kind==="file") actions.append(actionButton("↓","Download",()=>{const link=document.createElement("a");link.href=fileUrl(item.path);link.download=item.name;document.body.append(link);link.click();link.remove();}));
    actions.append(actionButton("✎","Rename",()=>renameItem(item)),actionButton("×","Delete",()=>deleteItem(item)));
    if(item.kind==="directory") actions.append(actionButton("ZIP","Download folder as ZIP",()=>{window.location.href=`/api/archive?${new URLSearchParams({path:item.path})}`;}));
    row.append(main,size,modified,actions); el.list.append(row);
  });
}
async function loadFolder(path=state.path) {
  const id=++state.requestId; state.path=path; el.loading.hidden=false; el.list.replaceChildren(); el.empty.hidden=true; setError(); renderBreadcrumbs();
  try {
    const data=await requestJson(`/api/files?${new URLSearchParams({path})}`);
    if(id!==state.requestId)return; state.items=data.items||[];
    const parts=path.split("/").filter(Boolean); el.title.textContent=parts.length?parts.at(-1):"Shared folder"; renderItems();
  } catch(error) { if(id===state.requestId){state.items=[];setError(error.message);} }
  finally {if(id===state.requestId)el.loading.hidden=true;}
}
function closePreview() {
  el.previewContent.querySelectorAll("video,audio").forEach(media=>{media.pause();media.removeAttribute("src");media.load();});
  el.previewContent.replaceChildren(); if(el.dialog.open)el.dialog.close();
}
function openPreview(item) {
  closePreview(); el.previewTitle.textContent=item.name; el.previewMeta.textContent=`${formatBytes(item.size)} · ${item.mime}`;
  const url=fileUrl(item.path); let preview;
  if(item.mime?.startsWith("image/")){preview=document.createElement("img");preview.src=url;preview.alt=item.name;}
  else if(item.mime?.startsWith("video/")){preview=document.createElement("video");preview.src=url;preview.controls=true;preview.preload="metadata";preview.playsInline=true;}
  else if(item.mime?.startsWith("audio/")){preview=document.createElement("audio");preview.src=url;preview.controls=true;preview.preload="metadata";}
  else if(item.mime==="application/pdf"){preview=document.createElement("iframe");preview.src=url;preview.title=item.name;}
  else if(item.mime?.startsWith("text/")||["application/json","application/xml","application/javascript"].includes(item.mime)){
    preview=document.createElement("pre");preview.textContent="Loading preview…";
    fetch(url).then(response=>{if(!response.ok)throw Error("Preview unavailable");if(Number(response.headers.get("Content-Length")||0)>500000)throw Error("Preview limited to 500 KB");return response.text();})
      .then(value=>{if(preview.isConnected)preview.textContent=value.slice(0,500000);}).catch(error=>{if(preview.isConnected)preview.textContent=error.message;});
  } else {preview=document.createElement("p");preview.className="preview-note";preview.textContent="This file type cannot be previewed in your browser.";}
  el.previewContent.append(preview); el.dialog.showModal();
}
function renameItem(item) {
  const name=prompt("New name:",item.name); if(!name||name===item.name)return;
  requestJson("/api/rename","POST",{path:item.path,name}).then(()=>loadFolder()).catch(error=>setError(error.message));
}
function deleteItem(item) {
  if(!confirm(`Permanently delete "${item.name}"?${item.kind==="directory"?" This also deletes its contents.":""}`))return;
  requestJson("/api/delete","POST",{path:item.path}).then(()=>loadFolder()).catch(error=>setError(error.message));
}
function uploadOne(file, relativePath) {
  return new Promise((resolve,reject)=>{
    const xhr=new XMLHttpRequest();
    xhr.open("POST",`/api/upload?${new URLSearchParams({path:state.path})}`);
    xhr.setRequestHeader("X-Relative-Path",encodeURIComponent(relativePath));
    xhr.upload.onprogress=event=>{if(event.lengthComputable)el.uploadStatus.textContent=`Uploading ${file.name}: ${Math.round(event.loaded/event.total*100)}%`;};
    xhr.onload=()=>{if(xhr.status>=200&&xhr.status<300)resolve();else{let message="Upload failed";try{message=JSON.parse(xhr.responseText).error||message;}catch{}reject(Error(message));}};
    xhr.onerror=()=>reject(Error("Network error during upload."));
    xhr.send(file);
  });
}
async function uploadFiles(files) {
  const selected=Array.from(files); if(!selected.length)return;
  el.uploadStatus.hidden=false; let complete=0;
  for(const file of selected){
    const relative=file.webkitRelativePath||file.name;
    try{await uploadOne(file,relative);complete++;el.uploadStatus.textContent=`Uploaded ${complete}/${selected.length}`;}
    catch(error){setError(`${file.name}: ${error.message}`);break;}
  }
  el.uploadStatus.textContent=`Upload finished: ${complete}/${selected.length} files`;
  await loadFolder();
}
el.search.addEventListener("input",event=>{state.query=event.target.value;renderItems();});
el.refresh.addEventListener("click",()=>loadFolder());
el.closePreview.addEventListener("click",closePreview);
el.dialog.addEventListener("click",event=>{if(event.target===el.dialog)closePreview();});
el.uploadFiles.addEventListener("change",event=>{uploadFiles(event.target.files);event.target.value="";});
el.uploadFolder.addEventListener("change",event=>{uploadFiles(event.target.files);event.target.value="";});
el.newFolder.addEventListener("click",()=>{const name=prompt("Folder name:");if(!name)return;requestJson("/api/folder","POST",{path:state.path,name}).then(()=>loadFolder()).catch(error=>setError(error.message));});
el.zipFolder.addEventListener("click",()=>{if(!state.path){setError("Open a folder first to download it as ZIP.");return;}window.location.href=`/api/archive?${new URLSearchParams({path:state.path})}`;});
loadFolder("");
