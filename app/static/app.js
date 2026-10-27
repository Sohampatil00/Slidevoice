const element = (id) => document.getElementById(id);
const state = { project: null, slide: 0, dirty: false, health: {}, polling: null, pending: false };
const fullScript = { preview: null, projectId: null, busy: false };
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character]));
const durationLabel = (seconds) => `${Math.floor(Math.round(seconds) / 60)}:${String(Math.round(seconds) % 60).padStart(2, "0")}`;

async function api(path, options = {}) {
  const headers = { "X-SlideVoice": "local", ...options.headers };
  if (options.body && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.body);
  }
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    let message = "Something went wrong. Please try again.";
    try {
      const error = await response.json();
      message = typeof error.detail === "string" ? error.detail : "Please check your input and try again.";
    } catch {}
    throw new Error(message);
  }
  return response.json();
}

function showError(message) {
  element("error").textContent = message;
  element("error").hidden = !message;
  if (message) element("error").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function action(operation) {
  if (state.pending) return;
  showError("");
  state.pending = true;
  updateButtons();
  try { await operation(); } catch (error) { showError(error.message); }
  finally { state.pending = false; updateButtons(); }
}

function updateButtons() {
  const running = state.pending || state.project?.job.status === "running";
  const noSlides = !state.project?.slides.length;
  for (const id of ["ai-one", "ai-all", "audio-one", "generate-audio", "save-script", "render-video", "import-script"]) {
    element(id).disabled = running || noSlides;
  }
  element("ai-one").disabled ||= !state.health.scripts;
  element("ai-all").disabled ||= !state.health.scripts;
  element("render-video").disabled ||= !state.project?.slides.every((slide) => slide.audio_ready);
  element("script").disabled = running;
  element("slide-title").disabled = running;
  element("audio-upload").disabled = running;
  element("reference-upload").disabled = running;
  for (const id of ["new-project", "sidebar-new", "try-demo", "empty-upload"]) element(id).disabled = state.pending;
  element("present-slides").disabled = running || noSlides;
  updateImportButtons();
}

async function refreshProjects() {
  const projects = await api("/api/projects");
  element("project-list").innerHTML = projects.length ? projects.map((project) => `<button class="project-item ${project.id === state.project?.id ? "active" : ""}" data-project="${project.id}" title="${escapeHtml(project.title)}">${escapeHtml(project.title)}</button>`).join("") : '<p class="muted small">Your presentations will live here.</p>';
}

function acceptProject(project) {
  if (state.project?.id !== project.id) element("voice-consent").checked = false;
  state.project = project;
  state.slide = Math.min(state.slide, Math.max(0, project.slides.length - 1));
  state.dirty = false;
  localStorage.setItem("slidevoice-project", project.id);
  render();
  clearTimeout(state.polling);
  if (project.job.status === "running") pollProject(project.id);
}

function pollProject(projectId) {
  state.polling = setTimeout(async () => {
    try {
      if (state.project?.id !== projectId) return;
      const project = await api(`/api/projects/${projectId}`);
      acceptProject(project);
      if (project.job.status !== "running") await refreshProjects();
    } catch (error) {
      showError(error.message);
      if (state.project?.id === projectId) pollProject(projectId);
    }
  }, 1400);
}

function render() {
  const project = state.project;
  const slides = project?.slides || [];
  const audioCount = slides.filter((slide) => slide.audio_ready).length;
  element("welcome").hidden = Boolean(project);
  element("slide-count").textContent = slides.length || "—";
  element("audio-count").textContent = slides.length ? `${audioCount} / ${slides.length}` : "—";
  const approximateDuration = slides.reduce((total, slide) => total + (slide.duration || 0) + (slide.duration ? Number(element("pause").value) : 0), 0);
  element("duration-count").textContent = project?.export ? durationLabel(project.export.duration) : approximateDuration ? `~${durationLabel(approximateDuration)}` : "—";
  element("duration-hint").textContent = project?.export ? "Final video length" : "Timed to your voice";
  element("project-title").textContent = project?.title || "Your next great explanation";
  element("project-subtitle").textContent = project ? `${slides.length} slides · English narration · Saved on your computer` : "Start with a presentation or explore the example.";
  element("project-status").textContent = project?.job.status === "running" ? "WORKING ON IT" : project?.export ? "VIDEO READY" : slides.length ? "IN YOUR HANDS" : "READY WHEN YOU ARE";
  element("empty-state").hidden = slides.length > 0 || project?.job.status === "running";
  element("editor").hidden = !slides.length;
  element("full-script-bar").hidden = !slides.length;
  element("script-generation-bar").hidden = !slides.length;
  element("controls").hidden = !slides.length;
  element("step-import").classList.toggle("done", slides.length > 0);
  element("step-script").classList.toggle("done", slides.length > 0 && slides.every((slide) => slide.script));
  element("step-voice").classList.toggle("done", slides.length > 0 && audioCount === slides.length);
  element("step-export").classList.toggle("done", Boolean(project?.export));
  const job = project?.job;
  element("job-panel").hidden = !job || !["running", "failed"].includes(job.status);
  element("job-panel").classList.toggle("failed", job?.status === "failed");
  element("job-message").textContent = job?.message || "";
  element("job-percent").textContent = job?.status === "running" ? `${job.progress}%` : "";
  element("job-progress").value = job?.progress || 0;
  element("rail-count").textContent = String(slides.length).padStart(2, "0");
  element("slides").innerHTML = slides.map((slide, index) => `<button class="slide-tile ${index === state.slide ? "active" : ""}" data-slide="${index}" aria-label="Slide ${slide.number}: ${escapeHtml(slide.title)}" ${index === state.slide ? 'aria-current="true"' : ""}><img src="${slide.image_url}" alt="" loading="lazy"><span class="tile-caption"><span>${String(slide.number).padStart(2, "0")}</span><span class="tile-title">${escapeHtml(slide.title)}</span><span class="tile-status" aria-label="${slide.audio_ready ? "Audio ready" : slide.script ? "Script ready" : "Needs script"}">${slide.audio_ready ? "✓" : slide.script ? "◦" : ""}</span></span></button>`).join("");
  renderSelectedSlide();
  const reference = project?.voice_reference;
  element("reference-status").textContent = reference ? `Your sample is ready · ${reference.duration.toFixed(1)} seconds · used next time you generate narration` : "No voice sample uploaded yet.";
  element("reference-player").hidden = !reference;
  if (reference) {
    if (element("reference-player").getAttribute("src") !== reference.audio_url) element("reference-player").src = reference.audio_url;
  } else element("reference-player").removeAttribute("src");
  const exported = project?.export;
  element("downloads").hidden = !exported;
  if (exported) {
    const player = element("video-player");
    if (player.getAttribute("src") !== exported.video_url) player.src = exported.video_url;
    element("download-video").href = exported.video_url;
    element("download-timings").href = exported.timings_url;
  } else {
    element("video-player").removeAttribute("src");
  }
  updateButtons();
}

function renderSelectedSlide() {
  const slide = state.project?.slides[state.slide];
  if (!slide) return;
  element("slide-image").src = slide.image_url;
  element("slide-image").alt = `Slide ${slide.number}: ${slide.title}`;
  element("slide-number").textContent = `${slide.number} / ${state.project.slides.length}`;
  element("slide-title").value = slide.title;
  element("script").value = slide.script;
  element("save-status").textContent = "All changes saved";
  element("source-text").textContent = [slide.text || "No extracted text. The script generator can still read the slide image.", slide.notes ? `SPEAKER NOTES\n${slide.notes}` : ""].filter(Boolean).join("\n\n");
  element("audio-preview").hidden = !slide.audio_ready;
  const player = element("audio-player");
  if (slide.audio_ready) {
    if (player.getAttribute("src") !== slide.audio_url) player.src = slide.audio_url;
    const sources = { preview: "Mac preview · not your voice", indic_mio: "Indic-MIO narration", lux_tts: "LuxTTS narration", uploaded: "Your uploaded recording" };
    element("audio-source").textContent = `${sources[slide.audio_source] || ""} · ${durationLabel(slide.duration)}`;
  } else player.removeAttribute("src");
  countWords();
}

function countWords() {
  const words = element("script").value.trim().split(/\s+/).filter(Boolean).length;
  element("word-count").textContent = `${words} words${words ? ` · ~${Math.ceil(words / 2.6)} sec spoken` : ""}`;
}

async function saveScript() {
  if (!state.dirty || !state.project) return;
  const slide = state.project.slides[state.slide];
  const project = await api(`/api/projects/${state.project.id}/slides/${slide.id}`, {
    method: "PATCH", body: { script: element("script").value, title: element("slide-title").value || `Slide ${slide.number}` },
  });
  acceptProject(project);
}

function confirmDiscard() {
  return !state.dirty || confirm("You have an unsaved script. Discard those changes?");
}

async function selectProject(projectId) {
  if (!confirmDiscard()) return;
  state.slide = 0;
  acceptProject(await api(`/api/projects/${projectId}`));
  await refreshProjects();
}

async function uploadDeck(files) {
  if (!files.length || !confirmDiscard()) return;
  const form = new FormData();
  for (const file of files) form.append("files", file);
  if ([...files].reduce((total, file) => total + file.size, 0) > 80 * 1024 * 1024) throw new Error("Please keep the total upload below 80 MB.");
  state.slide = 0;
  acceptProject(await api("/api/projects", { method: "POST", body: form }));
  await refreshProjects();
}

async function generateScripts(selectedOnly) {
  await saveScript();
  if (!state.health.scripts) { element("setup-dialog").showModal(); return; }
  const provider = "Gemini";
  const slide = state.project.slides[state.slide];
  if (selectedOnly && slide.script && !confirm(`Send this slide to ${provider} and replace its script? Its existing narration will be cleared. API charges may apply.`)) return;
  if (!selectedOnly) {
    const replacing = state.project.slides.some((entry) => entry.script.trim() || entry.audio_ready);
    const replacementNotice = replacing ? " Existing scripts will be replaced and their narration audio cleared." : "";
    if (!confirm(`Generate scripts for all ${state.project.slides.length} slides with ${provider}?${replacementNotice} Slide content will be sent to ${provider}. API charges may apply.`)) return;
  }
  const body = { instructions: element("instructions").value || "Explain clearly in English. Keep the explanation around 70 to 100 words, using short sentences." };
  body.slide_ids = selectedOnly ? [slide.id] : state.project.slides.map((entry) => entry.id);
  acceptProject(await api(`/api/projects/${state.project.id}/scripts`, { method: "POST", body }));
}

function resetScriptPreview() {
  fullScript.preview = null;
  element("script-assignment-preview").hidden = true;
  element("script-assignments").replaceChildren();
  element("split-status").textContent = "";
  element("full-script-error").hidden = true;
  updateImportButtons();
}

function updateSplitHelp() {
  element("split-help").textContent = "Use a heading on its own line: Slide 1, then its narration, then Slide 2, and so on. Include every slide in order. This runs locally.";
  element("preview-script").textContent = "Preview slide assignments";
}

function updateImportButtons() {
  const busy = fullScript.busy || state.pending;
  for (const id of ["close-full-script", "full-script-input", "split-method"]) element(id).disabled = busy;
  element("preview-script").disabled = busy || !element("full-script-input").value.trim();
  const entries = [...element("script-assignments").querySelectorAll("textarea")];
  const invalid = entries.filter((entry) => !entry.value.trim() || entry.value.length > 12000);
  for (const entry of entries) {
    entry.disabled = busy;
    entry.setAttribute("aria-invalid", String(!entry.value.trim() || entry.value.length > 12000));
  }
  element("apply-script").disabled = busy || !fullScript.preview || invalid.length > 0;
  if (fullScript.preview) {
    const changed = entries.filter((entry, index) => entry.value.trim() !== state.project.slides[index].script).length;
    element("assignment-summary").textContent = invalid.length
      ? `${invalid.length} slide${invalid.length === 1 ? " needs" : "s need"} narration before applying. Fill in each blank section below (up to 12,000 characters per slide).`
      : `${entries.length} slides assigned · ${changed} script${changed === 1 ? "" : "s"} will change. You can edit each section below.`;
  }
}

async function importAction(operation) {
  if (state.pending || fullScript.busy) return;
  fullScript.busy = true;
  state.pending = true;
  element("full-script-error").hidden = true;
  updateButtons();
  try { await operation(); }
  catch (error) {
    element("full-script-error").textContent = error.message;
    element("full-script-error").hidden = false;
    element("full-script-error").scrollIntoView({ block: "nearest" });
  } finally {
    fullScript.busy = false;
    state.pending = false;
    element("split-status").textContent = "";
    updateButtons();
  }
}

async function previewFullScript() {
  resetScriptPreview();
  element("split-status").textContent = "Splitting at slide headings…";
  const preview = await api(`/api/projects/${fullScript.projectId}/scripts/preview`, {
    method: "POST", body: { script: element("full-script-input").value, method: element("split-method").value },
  });
  fullScript.preview = preview;
  element("script-assignments").innerHTML = preview.slides.map((slide) => {
    const original = state.project.slides.find((entry) => entry.id === slide.id);
    return `<div class="script-assignment"><div class="assignment-heading"><img src="${original.image_url}" alt=""><label for="assignment-${slide.id}">Slide ${slide.number} · ${escapeHtml(slide.title)}</label></div><textarea id="assignment-${slide.id}" maxlength="12000" data-assignment="${slide.id}" placeholder="Add narration for this slide">${escapeHtml(slide.script)}</textarea></div>`;
  }).join("");
  element("script-assignment-preview").hidden = false;
  updateImportButtons();
  element("script-assignment-preview").scrollIntoView({ block: "start" });
}

async function applyFullScript() {
  const slides = [...element("script-assignments").querySelectorAll("textarea")].map((entry) => ({ id: entry.dataset.assignment, script: entry.value }));
  const project = await api(`/api/projects/${fullScript.projectId}/scripts/apply`, {
    method: "POST", body: { revision: fullScript.preview.revision, slides },
  });
  fullScript.preview = null;
  acceptProject(project);
  element("full-script-dialog").close();
  await refreshProjects();
}

async function generateAudio(selectedOnly) {
  await saveScript();
  const provider = element("voice-provider").value;
  const name = "LuxTTS";
  const startupNotice = provider === "lux_tts" && state.health.lux_tts_autostart && !state.health.lux_tts ? " LuxTTS will start automatically; first use may install packages and download model weights." : "";
  if (provider !== "preview" && !confirm(`Generate narration with ${name}? Your script and selected voice sample will be sent to your configured model server (your computer by default).${startupNotice}`)) return;
  const useReference = provider === "lux_tts";
  const body = { provider, voice_id: "", speed: Number(element("voice-speed").value), consent: element("voice-consent").checked, use_reference: useReference };
  if (selectedOnly) body.slide_ids = [state.project.slides[state.slide].id];
  acceptProject(await api(`/api/projects/${state.project.id}/audio`, { method: "POST", body }));
}

function voiceSourceChanged() {
  const provider = element("voice-provider").value;
  element("personal-voice").hidden = provider === "preview";
  element("voice-help").textContent = provider === "lux_tts" ? "LuxTTS starts automatically. First use prepares the model; later slides reuse your voice sample. Audition one slide first." : "A free local Mac voice for quick previews. This does not clone your voice.";
}

function renderConnections() {
  const provider = "Gemini";
  element("ai-one").textContent = `✧ Write with ${provider}`;
  const connections = [["Gemini scripts", state.health.gemini], ["LuxTTS server", state.health.lux_tts], ["PowerPoint rendering", state.health.pptx]];
  element("connection-status").innerHTML = connections.map(([name, ready]) => `<div class="connection">${name}<span class="${ready ? "ready" : ""}">${ready ? "✓ Ready" : name === "LuxTTS server" && state.health.lux_tts_autostart ? "Starts automatically" : "Not connected"}</span></div>`).join("");
}

for (const id of ["new-project", "sidebar-new", "empty-upload"]) element(id).addEventListener("click", () => element("deck-upload").click());
element("studio-nav").addEventListener("click", () => element("studio").scrollIntoView({ behavior: "smooth" }));
element("deck-upload").addEventListener("change", (event) => action(async () => { await uploadDeck(event.target.files); event.target.value = ""; }));
element("try-demo").addEventListener("click", () => action(async () => {
  if (!confirmDiscard()) return;
  state.slide = 0;
  acceptProject(await api("/api/demo", { method: "POST" }));
  await refreshProjects();
}));
element("project-list").addEventListener("click", (event) => { const button = event.target.closest("[data-project]"); if (button) action(() => selectProject(button.dataset.project)); });
element("slides").addEventListener("click", (event) => {
  const button = event.target.closest("[data-slide]");
  if (!button || !confirmDiscard()) return;
  state.slide = Number(button.dataset.slide); state.dirty = false; render();
});
for (const id of ["script", "slide-title"]) element(id).addEventListener("input", () => { state.dirty = true; element("save-status").textContent = "Unsaved changes"; countWords(); });
element("save-script").addEventListener("click", () => action(saveScript));
element("ai-one").addEventListener("click", () => action(() => generateScripts(true)));
element("ai-all").addEventListener("click", () => action(() => generateScripts(false)));
element("import-script").addEventListener("click", () => action(async () => {
  await saveScript();
  if (fullScript.projectId !== state.project.id) element("full-script-input").value = "";
  fullScript.projectId = state.project.id;
  resetScriptPreview();
  element("split-method").value = "headings";
  updateSplitHelp();
  element("full-script-dialog").showModal();
}));
element("close-full-script").addEventListener("click", () => element("full-script-dialog").close());
element("full-script-dialog").addEventListener("cancel", (event) => { if (fullScript.busy || state.pending) event.preventDefault(); });
element("full-script-input").addEventListener("input", resetScriptPreview);
element("split-method").addEventListener("change", () => { resetScriptPreview(); updateSplitHelp(); });
element("preview-script").addEventListener("click", () => importAction(previewFullScript));
element("script-assignments").addEventListener("input", updateImportButtons);
element("apply-script").addEventListener("click", () => importAction(applyFullScript));
element("audio-one").addEventListener("click", () => action(() => generateAudio(true)));
element("generate-audio").addEventListener("click", () => action(() => generateAudio(false)));
element("voice-provider").addEventListener("change", voiceSourceChanged);
element("reference-upload").addEventListener("change", (event) => action(async () => {
  const file = event.target.files[0];
  event.target.value = "";
  if (!file) return;
  if (!element("voice-consent").checked) throw new Error("Confirm you own this recording or have permission to clone this voice first.");
  if (file.size > 20 * 1024 * 1024) throw new Error("Keep the voice sample below 20 MB and between 3 and 20 seconds.");
  await saveScript();
  const form = new FormData(); form.append("file", file); form.append("consent", "true");
  acceptProject(await api(`/api/projects/${state.project.id}/reference`, { method: "POST", body: form }));
  event.target.value = "";
}));
element("voice-speed").addEventListener("input", () => { element("speed-label").textContent = `${Number(element("voice-speed").value).toFixed(2).replace(/0$/, "")}×`; });
element("audio-upload").addEventListener("change", (event) => action(async () => {
  if (!event.target.files.length) return;
  await saveScript();
  const form = new FormData(); form.append("file", event.target.files[0]);
  const slide = state.project.slides[state.slide];
  acceptProject(await api(`/api/projects/${state.project.id}/slides/${slide.id}/audio`, { method: "POST", body: form }));
  event.target.value = "";
}));
element("render-video").addEventListener("click", () => action(async () => {
  await saveScript();
  acceptProject(await api(`/api/projects/${state.project.id}/render`, { method: "POST", body: { pause: Number(element("pause").value), resolution: element("resolution").value } }));
}));
element("pause").addEventListener("change", () => { if (!state.dirty) render(); });
element("setup-button").addEventListener("click", () => {
  element("setup-dialog").showModal();
  api("/api/health").then((health) => { state.health = health; renderConnections(); updateButtons(); }).catch((error) => showError(error.message));
});
element("close-setup").addEventListener("click", () => element("setup-dialog").close());
window.addEventListener("beforeunload", (event) => { if (state.dirty) { event.preventDefault(); event.returnValue = ""; } });
document.addEventListener("dragover", (event) => { if (event.dataTransfer.types.includes("Files")) { event.preventDefault(); document.body.classList.add("dragging"); } });
document.addEventListener("dragleave", (event) => { if (!event.relatedTarget) document.body.classList.remove("dragging"); });
document.addEventListener("drop", (event) => { event.preventDefault(); document.body.classList.remove("dragging"); if (event.dataTransfer.files.length) action(() => uploadDeck(event.dataTransfer.files)); });

async function initialize() {
  state.health = await api("/api/health");
  if (!state.health.preview) {
    element("voice-provider").querySelector('[value="preview"]').disabled = true;
    element("voice-provider").value = "lux_tts";
  }
  voiceSourceChanged();
  renderConnections();
  const previous = localStorage.getItem("slidevoice-project");
  if (previous) {
    try { acceptProject(await api(`/api/projects/${previous}`)); }
    catch { localStorage.removeItem("slidevoice-project"); }
  }
  render();
  await refreshProjects();
}
initialize().catch((error) => showError(error.message));
