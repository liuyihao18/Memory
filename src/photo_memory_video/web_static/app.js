let state = null;
let selectedScene = 0;
let busy = false;
const selectedPageByScene = {};

const el = (id) => document.getElementById(id);

function setStatus(text) {
  el("statusText").textContent = text;
}

function setBusy(value) {
  busy = value;
  for (const id of ["saveBtn", "previewBtn", "renderBtn", "addSceneBtn", "chooseOutputBtn"]) {
    el(id).disabled = value;
  }
}

function setProgress(progress, message, visible = true) {
  const box = el("progressBox");
  const bar = el("renderProgress");
  const text = el("progressText");
  box.hidden = !visible;
  const percent = Math.round(Math.max(0, Math.min(1, progress || 0)) * 100);
  bar.value = percent;
  text.textContent = message ? `${percent}% · ${message}` : `${percent}%`;
}

async function api(path, payload = null) {
  const options = payload
    ? {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }
    : {};
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || `HTTP ${response.status}`);
  }
  return data;
}

async function loadProject() {
  setStatus("加载中");
  state = await api("/api/project");
  selectedScene = 0;
  render();
  await preview();
}

function render() {
  if (!state) return;
  el("configPath").textContent = state.configPath;
  el("outputPath").value = state.outputPath || "";
  el("videoTitle").value = state.video.title || "";
  el("videoWidth").value = state.video.resolution?.[0] || 1920;
  el("videoHeight").value = state.video.resolution?.[1] || 1080;
  el("videoFps").value = state.video.fps || 30;
  el("backgroundColor").value = state.video.background_color || "#181614";
  el("transitionDuration").value = state.video.transition_duration ?? 0.8;
  el("fadeDuration").value = state.video.fade_duration ?? 0.6;
  renderSceneList();
  renderSceneEditor();
}

function renderSceneList() {
  const list = el("sceneList");
  list.replaceChildren();
  state.scenes.forEach((scene, index) => {
    const pages = paginatePhotos(scene.photos);
    const item = document.createElement("div");
    item.className = `scene-item${index === selectedScene ? " active" : ""}`;

    const button = document.createElement("button");
    button.className = "scene-button";
    button.onclick = async () => {
      selectedScene = index;
      clampSelectedPage();
      render();
      await preview();
    };
    button.innerHTML = `
      <div class="scene-title">${escapeHtml(scene.title || `场景 ${index + 1}`)}</div>
      <div class="scene-meta">${scene.photos.length} 张 · ${pages.length} 页 · ${scene.duration || 0}s</div>
    `;

    const actions = document.createElement("div");
    actions.className = "mini-actions";
    actions.append(
      smallButton("↑", "上移场景", () => moveScene(index, -1)),
      smallButton("↓", "下移场景", () => moveScene(index, 1)),
      smallButton("×", "删除场景", () => deleteScene(index), "danger")
    );

    item.append(button, actions);
    list.append(item);
  });
}

function renderSceneEditor() {
  const host = el("sceneEditor");
  host.replaceChildren();
  const scene = state.scenes[selectedScene];
  if (!scene) return;
  clampSelectedPage();

  const form = document.createElement("section");
  form.className = "scene-form";
  form.append(
    field("场景标题", textInput(scene.title || "", (value) => (scene.title = value))),
    field("时长", numberInput(scene.duration || 6, 0.5, (value) => (scene.duration = value))),
    field("场景描述", textarea(scene.description || "", (value) => (scene.description = value)))
  );

  const pageTabs = renderPageTabs(scene);

  const toolbar = document.createElement("section");
  toolbar.className = "photo-toolbar";
  const photoPath = textInput("", () => {});
  photoPath.placeholder = "photos/001.jpg";
  const choosePhotoButton = document.createElement("button");
  choosePhotoButton.textContent = "选择";
  choosePhotoButton.onclick = () => choosePhotoFile(photoPath);
  const addButton = document.createElement("button");
  addButton.textContent = "添加";
  addButton.onclick = () => addPhoto(photoPath.value);
  const directoryPath = textInput("", () => {});
  directoryPath.placeholder = "photos";
  const chooseDirectoryButton = document.createElement("button");
  chooseDirectoryButton.textContent = "选择";
  chooseDirectoryButton.onclick = () => chooseDirectory(directoryPath);
  const importButton = document.createElement("button");
  importButton.textContent = "导入目录";
  importButton.onclick = () => importDirectory(directoryPath.value);
  toolbar.append(field("照片路径", photoPath), choosePhotoButton, addButton, field("目录", directoryPath), chooseDirectoryButton, importButton);

  const grid = document.createElement("section");
  grid.className = "photo-grid";
  scene.photos.forEach((photo, index) => grid.append(photoCard(photo, index)));

  host.append(form, pageTabs, toolbar, grid);
}

function renderPageTabs(scene) {
  const pages = paginatePhotos(scene.photos);
  const selectedPage = currentPageIndex();
  const wrapper = document.createElement("section");
  wrapper.className = "page-preview-bar";

  const label = document.createElement("div");
  label.className = "page-preview-label";
  label.textContent = "分页预览";
  wrapper.append(label);

  pages.forEach((page, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `page-tab${index === selectedPage ? " active" : ""}`;
    button.textContent = `第 ${index + 1} 页 · ${page.photos.length} 张`;
    button.title = page.photos.map((photo) => photo.path || "未设置路径").join("\n");
    button.onclick = async () => {
      selectedPageByScene[selectedScene] = index;
      render();
      await preview();
    };
    wrapper.append(button);
  });

  return wrapper;
}

function photoCard(photo, index) {
  const card = document.createElement("article");
  card.className = "photo-card";
  card.draggable = true;
  card.dataset.index = index;
  card.addEventListener("dragstart", () => card.classList.add("dragging"));
  card.addEventListener("dragend", () => card.classList.remove("dragging"));
  card.addEventListener("dragover", (event) => event.preventDefault());
  card.addEventListener("drop", (event) => {
    event.preventDefault();
    const source = Number(document.querySelector(".photo-card.dragging")?.dataset.index);
    if (!Number.isNaN(source)) movePhoto(source, index);
  });

  const image = document.createElement("img");
  image.className = "thumb";
  image.alt = photo.caption || photo.path || "photo";
  image.src = mediaUrl(photo.path);

  const body = document.createElement("div");
  body.className = "photo-body";
  const pathInput = textInput(photo.path || "", (value) => {
    photo.path = value;
    photo.resolvedPath = "";
    photo.mediaUrl = mediaUrl(value);
    image.src = photo.mediaUrl;
  });
  const timeInput = textInput(photo.time || "", (value) => (photo.time = value));
  const captionInput = textInput(photo.caption || "", (value) => (photo.caption = value));
  const descriptionInput = textarea(photo.description || "", (value) => (photo.description = value));

  const actions = document.createElement("div");
  actions.className = "photo-actions";
  actions.append(
    smallButton("↑", "上移照片", () => movePhoto(index, index - 1)),
    smallButton("↓", "下移照片", () => movePhoto(index, index + 1)),
    smallButton("⧉", "复制照片", () => duplicatePhoto(index)),
    smallButton("↻", "刷新预览", () => preview()),
    smallButton("×", "删除照片", () => deletePhoto(index), "danger")
  );

  body.append(
    pathField("路径", pathInput, () => choosePhotoFile(pathInput)),
    field("时间", timeInput),
    field("标题", captionInput),
    field("描述", descriptionInput),
    actions
  );
  card.append(image, body);
  return card;
}

function field(labelText, control) {
  const label = document.createElement("label");
  label.textContent = labelText;
  label.append(control);
  return label;
}

function pathField(labelText, input, onChoose) {
  const label = document.createElement("label");
  label.textContent = labelText;
  const row = document.createElement("div");
  row.className = "path-picker";
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "选择";
  button.onclick = onChoose;
  row.append(input, button);
  label.append(row);
  return label;
}

function textInput(value, onChange) {
  const input = document.createElement("input");
  input.value = value;
  input.addEventListener("input", () => onChange(input.value));
  return input;
}

function numberInput(value, step, onChange) {
  const input = document.createElement("input");
  input.type = "number";
  input.min = "0";
  input.step = String(step);
  input.value = value;
  input.addEventListener("input", () => onChange(Number(input.value)));
  return input;
}

function textarea(value, onChange) {
  const input = document.createElement("textarea");
  input.value = value;
  input.addEventListener("input", () => onChange(input.value));
  return input;
}

function smallButton(text, title, onClick, extraClass = "") {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = text;
  button.title = title;
  button.className = extraClass;
  button.onclick = (event) => {
    event.stopPropagation();
    onClick();
  };
  return button;
}

function readVideoForm() {
  state.outputPath = el("outputPath").value.trim();
  state.video.title = el("videoTitle").value.trim();
  state.video.resolution = [Number(el("videoWidth").value), Number(el("videoHeight").value)];
  state.video.fps = Number(el("videoFps").value);
  state.video.background_color = el("backgroundColor").value;
  state.video.transition_duration = Number(el("transitionDuration").value);
  state.video.fade_duration = Number(el("fadeDuration").value);
}

function addScene() {
  state.scenes.push({
    title: `场景 ${state.scenes.length + 1}`,
    description: "",
    duration: 6,
    photos: [{ path: "", time: "", caption: "", description: "" }],
  });
  selectedScene = state.scenes.length - 1;
  selectedPageByScene[selectedScene] = 0;
  render();
}

function moveScene(index, delta) {
  const next = index + delta;
  if (next < 0 || next >= state.scenes.length) return;
  const [scene] = state.scenes.splice(index, 1);
  state.scenes.splice(next, 0, scene);
  selectedScene = next;
  clampSelectedPage();
  render();
}

function deleteScene(index) {
  if (state.scenes.length <= 1) return;
  state.scenes.splice(index, 1);
  selectedScene = Math.max(0, Math.min(selectedScene, state.scenes.length - 1));
  clampSelectedPage();
  render();
}

function addPhoto(path) {
  const scene = state.scenes[selectedScene];
  if (!path.trim()) return;
  scene.photos.push({ path: path.trim(), time: "", caption: "", description: "", mediaUrl: mediaUrl(path.trim()) });
  clampSelectedPage();
  render();
}

async function importDirectory(directory) {
  if (!directory.trim()) return;
  await withBusy("读取目录", async () => {
    const data = await api("/api/list-images", { directory });
    const scene = state.scenes[selectedScene];
    scene.photos.push(...data.photos.map((photo) => ({ ...photo, time: "", caption: "", description: "" })));
    clampSelectedPage();
    render();
    setStatus(`导入 ${data.photos.length} 张`);
  });
}

async function choosePhotoFile(input) {
  await withBusy("选择照片", async () => {
    const data = await api("/api/choose-file", { purpose: "photo" });
    if (!data.selection.path) {
      setStatus("已取消");
      return;
    }
    input.value = data.selection.path;
    input.dispatchEvent(new Event("input"));
    setStatus("已选择照片");
  });
}

async function chooseDirectory(input) {
  await withBusy("选择目录", async () => {
    const data = await api("/api/choose-directory", {});
    if (!data.selection.path) {
      setStatus("已取消");
      return;
    }
    input.value = data.selection.path;
    input.dispatchEvent(new Event("input"));
    setStatus("已选择目录");
  });
}

async function chooseOutputPath() {
  readVideoForm();
  await withBusy("选择输出", async () => {
    const data = await api("/api/choose-file", { purpose: "output" });
    if (!data.selection.path) {
      setStatus("已取消");
      return;
    }
    state.outputPath = data.selection.path;
    el("outputPath").value = data.selection.path;
    setStatus("已选择输出");
  });
}

function movePhoto(from, to) {
  const photos = state.scenes[selectedScene].photos;
  if (to < 0 || to >= photos.length || from === to) return;
  const [photo] = photos.splice(from, 1);
  photos.splice(to, 0, photo);
  clampSelectedPage();
  render();
}

function duplicatePhoto(index) {
  const photos = state.scenes[selectedScene].photos;
  photos.splice(index + 1, 0, { ...photos[index] });
  clampSelectedPage();
  render();
}

function deletePhoto(index) {
  const photos = state.scenes[selectedScene].photos;
  if (photos.length <= 1) return;
  photos.splice(index, 1);
  clampSelectedPage();
  render();
}

async function save() {
  readVideoForm();
  await withBusy("保存中", async () => {
    const data = await api("/api/project", { state });
    state = data.state;
    clampSelectedPage();
    render();
    setStatus("已保存");
  });
}

async function preview() {
  readVideoForm();
  clampSelectedPage();
  const pageIndex = currentPageIndex();
  await withBusy("生成预览", async () => {
    const data = await api("/api/preview", { state, sceneIndex: selectedScene, pageIndex });
    el("previewImage").src = data.preview.url;
    const page = data.preview.page;
    setStatus(`预览：场景 ${selectedScene + 1} · 第 ${page.pageIndex + 1}/${page.pageCount} 页 · ${page.photoCount} 张`);
  });
}

async function renderVideo() {
  readVideoForm();
  await withBusy("渲染中", async () => {
    setProgress(0, "排队中");
    const data = await api("/api/render/start", { state, outputPath: state.outputPath });
    await pollRenderJob(data.job.id);
  });
}

async function pollRenderJob(jobId) {
  while (true) {
    const data = await api(`/api/render/status?id=${encodeURIComponent(jobId)}`);
    const job = data.job;
    setProgress(job.progress, job.message);
    setStatus(job.message);
    if (job.status === "done") {
      el("videoLink").href = job.url;
      el("videoLink").textContent = job.path;
      setStatus("渲染完成");
      setProgress(1, "渲染完成");
      return;
    }
    if (job.status === "failed") {
      throw new Error(job.error || "渲染失败");
    }
    await sleep(600);
  }
}

function currentPageIndex() {
  const scene = state.scenes[selectedScene];
  const pageCount = paginatePhotos(scene.photos).length;
  const saved = selectedPageByScene[selectedScene] ?? 0;
  return Math.max(0, Math.min(saved, pageCount - 1));
}

function clampSelectedPage() {
  selectedPageByScene[selectedScene] = currentPageIndex();
}

function paginatePhotos(photos, maxPerPage = 4) {
  if (photos.length <= maxPerPage) {
    return [{ start: 0, end: photos.length, photos: photos.slice() }];
  }
  const pageCount = Math.ceil(photos.length / maxPerPage);
  const baseSize = Math.floor(photos.length / pageCount);
  const extra = photos.length % pageCount;
  const pages = [];
  let cursor = 0;
  for (let pageIndex = 0; pageIndex < pageCount; pageIndex += 1) {
    const pageSize = baseSize + (pageIndex < extra ? 1 : 0);
    pages.push({ start: cursor, end: cursor + pageSize, photos: photos.slice(cursor, cursor + pageSize) });
    cursor += pageSize;
  }
  return pages;
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function withBusy(label, task) {
  if (busy) return;
  setBusy(true);
  setStatus(label);
  try {
    await task();
  } catch (error) {
    setStatus(error.message);
  } finally {
    setBusy(false);
  }
}

function mediaUrl(path) {
  return `/media?path=${encodeURIComponent(path || "")}&v=${Date.now()}`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

for (const id of ["videoTitle", "videoWidth", "videoHeight", "videoFps", "backgroundColor", "transitionDuration", "fadeDuration", "outputPath"]) {
  el(id).addEventListener("input", readVideoForm);
}
el("addSceneBtn").addEventListener("click", addScene);
el("chooseOutputBtn").addEventListener("click", chooseOutputPath);
el("saveBtn").addEventListener("click", save);
el("previewBtn").addEventListener("click", preview);
el("renderBtn").addEventListener("click", renderVideo);

loadProject().catch((error) => setStatus(error.message));
