let state = null;
let selectedScene = 0;
let busy = false;
let draggedPhotoIndex = null;
let previewTimer = null;
let previewInFlight = false;
let previewPending = false;
const selectedPageByScene = {};
const LIVE_PREVIEW_DELAY = 450;

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
    ensureSceneDefaults(scene);
    const pages = paginateScenePhotos(scene);
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
  ensureSceneDefaults(scene);
  clampSelectedPage();

  const form = document.createElement("section");
  form.className = "scene-form";
  const layoutInput = selectInput(
    scene.layout || "auto",
    [
      ["auto", "自动网格"],
      ["grid", "规整网格"],
      ["photo_wall", "照片墙"],
    ],
    async (value) => {
      scene.layout = value;
      ensureSceneDefaults(scene);
      clampSelectedPage();
      render();
      await preview();
    }
  );
  form.append(
    field("场景标题", textInput(scene.title || "", (value) => (scene.title = value), true)),
    field("时长", numberInput(scene.duration || 6, 0.5, (value) => (scene.duration = value), 0, null, true)),
    field("布局", layoutInput),
    field("场景描述", textarea(scene.description || "", (value) => (scene.description = value), true))
  );

  const wallSettings = scene.layout === "photo_wall" ? renderWallSettings(scene) : null;
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

  if (wallSettings) {
    host.append(form, wallSettings, pageTabs, toolbar, grid);
  } else {
    host.append(form, pageTabs, toolbar, grid);
  }
}

function renderPageTabs(scene) {
  const pages = paginateScenePhotos(scene);
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
  const scene = state.scenes[selectedScene];
  const card = document.createElement("article");
  card.className = "photo-card";
  card.dataset.index = index;
  card.addEventListener("dragover", (event) => {
    if (draggedPhotoIndex !== null) {
      event.preventDefault();
    }
  });
  card.addEventListener("drop", (event) => {
    if (draggedPhotoIndex === null) return;
    event.preventDefault();
    const source = draggedPhotoIndex;
    draggedPhotoIndex = null;
    document.querySelector(".photo-card.dragging")?.classList.remove("dragging");
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
  const timeInput = textInput(photo.time || "", (value) => (photo.time = value), true);
  const captionInput = textInput(photo.caption || "", (value) => (photo.caption = value), true);
  const descriptionInput = textarea(photo.description || "", (value) => (photo.description = value), true);

  const actions = document.createElement("div");
  actions.className = "photo-actions";
  actions.append(
    dragHandle(card, index),
    smallButton("↑", "上移照片", () => movePhoto(index, index - 1)),
    smallButton("↓", "下移照片", () => movePhoto(index, index + 1)),
    smallButton("⧉", "复制照片", () => duplicatePhoto(index)),
    smallButton("↻", "刷新预览", () => preview()),
    smallButton("×", "删除照片", () => deletePhoto(index), "danger")
  );

  const fields = [
    pathField("路径", pathInput, () => choosePhotoFile(pathInput)),
    field("时间", timeInput),
    field("标题", captionInput),
    field("描述", descriptionInput),
  ];
  if (scene?.layout === "photo_wall") {
    fields.push(transformControls(photo));
  }
  fields.push(actions);

  body.append(...fields);
  card.append(image, body);
  return card;
}

function dragHandle(card, index) {
  const button = smallButton("↕", "拖动排序", () => {});
  button.classList.add("drag-handle");
  button.draggable = true;
  button.addEventListener("dragstart", (event) => {
    draggedPhotoIndex = index;
    card.classList.add("dragging");
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", String(index));
    }
  });
  button.addEventListener("dragend", () => {
    draggedPhotoIndex = null;
    card.classList.remove("dragging");
  });
  return button;
}

function renderWallSettings(scene) {
  ensureSceneDefaults(scene);
  const wrapper = document.createElement("section");
  wrapper.className = "wall-settings";
  wrapper.append(
    field("每页张数", numberInput(scene.wall.max_per_page || 6, 1, (value) => {
      scene.wall.max_per_page = Math.max(1, Math.min(9, Math.round(value || 6)));
      clampSelectedPage();
      render();
      schedulePreview();
    }, 1, 9)),
    field("旋转强度", numberInput(scene.wall.rotation ?? 6, 0.5, (value) => (scene.wall.rotation = value), 0, 20, true)),
    field("错落重叠", numberInput(scene.wall.overlap ?? 0.12, 0.01, (value) => (scene.wall.overlap = value), 0, 0.45, true)),
    field(
      "卡片样式",
      selectInput(scene.wall.style || "print", [["print", "拍立得"], ["clean", "干净"]], (value) => (scene.wall.style = value), true)
    )
  );
  const actions = document.createElement("div");
  actions.className = "wall-actions";
  const applyButton = document.createElement("button");
  applyButton.type = "button";
  applyButton.textContent = "写入当前页自动参数";
  applyButton.onclick = applyAutoTransforms;
  const clearButton = document.createElement("button");
  clearButton.type = "button";
  clearButton.textContent = "清空当前页参数";
  clearButton.onclick = clearCurrentPageTransforms;
  actions.append(applyButton, clearButton);
  wrapper.append(actions);
  return wrapper;
}

function transformControls(photo) {
  const wrapper = document.createElement("section");
  wrapper.className = "transform-grid";
  wrapper.append(
    field("X", optionalNumberInput(photo.transform?.x, 0.01, (value) => setTransform(photo, "x", value), 0, 1, true)),
    field("Y", optionalNumberInput(photo.transform?.y, 0.01, (value) => setTransform(photo, "y", value), 0, 1, true)),
    field("宽度", optionalNumberInput(photo.transform?.width, 0.01, (value) => setTransform(photo, "width", value), 0.08, 0.95, true)),
    field("旋转", optionalNumberInput(photo.transform?.rotation, 0.5, (value) => setTransform(photo, "rotation", value), -45, 45, true)),
    field("层级", optionalNumberInput(photo.transform?.z_index, 1, (value) => setTransform(photo, "z_index", value), -20, 20, true)),
    field(
      "适配",
      selectInput(photo.transform?.fit || "", [["", "自动"], ["cover", "裁切"], ["contain", "完整"]], (value) => setTransform(photo, "fit", value || null), true)
    )
  );
  return wrapper;
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

function textInput(value, onChange, livePreview = false) {
  const input = document.createElement("input");
  input.value = value;
  input.addEventListener("input", () => {
    onChange(input.value);
    if (livePreview) schedulePreview();
  });
  return input;
}

function numberInput(value, step, onChange, min = 0, max = null, livePreview = false) {
  const input = document.createElement("input");
  input.type = "number";
  input.min = String(min);
  if (max !== null) input.max = String(max);
  input.step = String(step);
  input.value = value;
  input.addEventListener("input", () => {
    onChange(Number(input.value));
    if (livePreview) schedulePreview();
  });
  return input;
}

function optionalNumberInput(value, step, onChange, min = null, max = null, livePreview = false) {
  const input = document.createElement("input");
  input.type = "number";
  if (min !== null) input.min = String(min);
  if (max !== null) input.max = String(max);
  input.step = String(step);
  input.value = value ?? "";
  input.placeholder = "自动";
  input.addEventListener("input", () => {
    const text = input.value.trim();
    onChange(text === "" ? null : Number(text));
    if (livePreview) schedulePreview();
  });
  return input;
}

function selectInput(value, options, onChange, livePreview = false) {
  const select = document.createElement("select");
  for (const [optionValue, label] of options) {
    const option = document.createElement("option");
    option.value = optionValue;
    option.textContent = label;
    select.append(option);
  }
  select.value = value;
  select.addEventListener("change", () => {
    onChange(select.value);
    if (livePreview) schedulePreview();
  });
  return select;
}

function textarea(value, onChange, livePreview = false) {
  const input = document.createElement("textarea");
  input.value = value;
  input.addEventListener("input", () => {
    onChange(input.value);
    if (livePreview) schedulePreview();
  });
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
    layout: "auto",
    wall: defaultWall(),
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
  await refreshPreview({ lockControls: true });
}

async function refreshPreview({ lockControls = false } = {}) {
  if (previewInFlight) {
    previewPending = true;
    return;
  }
  if (busy && !lockControls) return;
  if (lockControls) {
    if (busy) return;
    setBusy(true);
  }
  previewInFlight = true;
  readVideoForm();
  clampSelectedPage();
  const pageIndex = currentPageIndex();
  setStatus("生成预览");
  try {
    const data = await api("/api/preview", { state, sceneIndex: selectedScene, pageIndex });
    el("previewImage").src = data.preview.url;
    const page = data.preview.page;
    setStatus(`预览：场景 ${selectedScene + 1} · 第 ${page.pageIndex + 1}/${page.pageCount} 页 · ${page.photoCount} 张`);
  } catch (error) {
    setStatus(error.message);
  } finally {
    previewInFlight = false;
    if (lockControls) setBusy(false);
    if (previewPending) {
      previewPending = false;
      schedulePreview(90);
    }
  }
}

function schedulePreview(delay = LIVE_PREVIEW_DELAY) {
  if (!state || busy) return;
  window.clearTimeout(previewTimer);
  previewTimer = window.setTimeout(() => refreshPreview(), delay);
}

async function renderVideo() {
  readVideoForm();
  await withBusy("渲染中", async () => {
    setProgress(0, "排队中");
    const data = await api("/api/render/start", { state, outputPath: state.outputPath });
    await pollRenderJob(data.job.id);
  });
}

async function applyAutoTransforms() {
  readVideoForm();
  clampSelectedPage();
  const pageIndex = currentPageIndex();
  await withBusy("写入自动参数", async () => {
    const data = await api("/api/layout/auto-transform", { state, sceneIndex: selectedScene, pageIndex });
    const photos = state.scenes[selectedScene].photos;
    for (const item of data.layout.transforms) {
      if (photos[item.photoIndex]) {
        photos[item.photoIndex].transform = { ...item.transform };
      }
    }
    render();
    await preview();
    setStatus("已写入当前页自动参数");
  });
}

async function clearCurrentPageTransforms() {
  const scene = state.scenes[selectedScene];
  const page = paginateScenePhotos(scene)[currentPageIndex()];
  if (!page) return;
  for (let index = page.start; index < page.end; index += 1) {
    delete scene.photos[index].transform;
  }
  render();
  await preview();
  setStatus("已清空当前页参数");
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
  const pageCount = paginateScenePhotos(scene).length;
  const saved = selectedPageByScene[selectedScene] ?? 0;
  return Math.max(0, Math.min(saved, pageCount - 1));
}

function clampSelectedPage() {
  selectedPageByScene[selectedScene] = currentPageIndex();
}

function paginateScenePhotos(scene) {
  ensureSceneDefaults(scene);
  const maxPerPage = scene.layout === "photo_wall" ? Number(scene.wall?.max_per_page || 6) : 4;
  return paginatePhotos(scene.photos, maxPerPage);
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

function ensureSceneDefaults(scene) {
  scene.layout = scene.layout || "auto";
  scene.wall = { ...defaultWall(), ...(scene.wall || {}) };
}

function defaultWall() {
  return { max_per_page: 6, rotation: 6, overlap: 0.12, style: "print" };
}

function setTransform(photo, key, value) {
  photo.transform = photo.transform || {};
  if (value === null || value === "" || Number.isNaN(value)) {
    delete photo.transform[key];
  } else {
    photo.transform[key] = value;
  }
  if (Object.keys(photo.transform).length === 0) {
    delete photo.transform;
  }
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

for (const id of ["videoTitle", "videoWidth", "videoHeight", "videoFps", "backgroundColor", "transitionDuration", "fadeDuration"]) {
  el(id).addEventListener("input", () => {
    readVideoForm();
    schedulePreview();
  });
}
el("outputPath").addEventListener("input", readVideoForm);
el("addSceneBtn").addEventListener("click", addScene);
el("chooseOutputBtn").addEventListener("click", chooseOutputPath);
el("saveBtn").addEventListener("click", save);
el("previewBtn").addEventListener("click", preview);
el("renderBtn").addEventListener("click", renderVideo);

loadProject().catch((error) => setStatus(error.message));
