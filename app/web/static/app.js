"use strict";

const $ = (id) => document.getElementById(id);
const PAGE = 120;
const state = { libraryId: null, offset: 0, total: 0, pollTimer: null, lastJobStatus: null };

const SIGNAL_HE = {
  "Best of duplicate group": ["הטובה מהקבוצה", "best"],
  "Duplicate — alternate": ["עותק כפול", "warn"],
  "Blurry": ["איכות ירודה · מטושטשת", "warn"],
  "Extremely low resolution": ["איכות ירודה · קטנה מדי", "warn"],
  "Screenshot": ["צילום מסך", "warn"],
  "Underexposed": ["חשוכה", "warn"],
  "Overexposed": ["בהירה מדי", "warn"],
};
const PHASE_HE = { starting: "מתחיל", scanning: "סורק תיקיות", analyzing: "מנתח תמונות",
  deduplicating: "מאתר כפילויות", done: "הסתיים", failed: "נכשל", cancelled: "בוטל" };
const DATE_SRC_HE = { exif: "EXIF (מהמצלמה)", filename: "משם הקובץ", file_mtime: "תאריך שינוי קובץ (לא אמין)" };

async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch (_) {}
    throw new Error(msg);
  }
  return res.json();
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
const fmtDate = (iso) => (iso ? iso.replace("T", " ").slice(0, 16) : "—");
const num = (n) => (n ?? 0).toLocaleString("he-IL");

// ------------------------------------------------------------------ health
// Build of the page currently shown (filled in by the server). If the server now runs another
// build, the page is outdated: offer a reload instead of silently running old UI code (ADR-015).
const PAGE_BUILD = document.querySelector('meta[name="app-build"]')?.content || "";

async function checkForUpdate() {
  try {
    const h = await api("/api/health");
    $("updateBanner").hidden = !h.build || h.build === PAGE_BUILD;
  } catch (_) { /* server restarting; check again later */ }
}

async function loadHealth() {
  try {
    const h = await api("/api/health");
    $("updateBanner").hidden = !h.build || h.build === PAGE_BUILD;
    $("health").textContent = `v${h.version} (build ${h.build}) · מסד נתונים: ${h.database === "ok" ? "תקין" : "שגיאה"} · HEIC: ${h.heic_supported ? "נתמך" : "לא נתמך"}`;
  } catch (e) { $("health").textContent = "השרת לא זמין"; }
}

// --------------------------------------------------------------- libraries
async function loadLibraries(selectId) {
  const libs = await api("/api/libraries");
  const sel = $("librarySelect");
  sel.innerHTML = libs.map((l) => `<option value="${l.id}">${esc(l.name)} (${num(l.photo_count)}) — ${esc(l.root_path)}</option>`).join("");
  $("librariesCard").hidden = libs.length === 0;
  // The old M1 gallery (metadata filters: GPS, no date, sort, year) is a developer tool: ?debug only.
  $("galleryCard").hidden = libs.length === 0 || !DEBUG;
  if (!libs.length) { resetLibraryUI(); return; }
  const id = selectId ?? state.libraryId ?? libs[libs.length - 1].id;
  sel.value = String(id);
  await selectLibrary(Number(sel.value));
}

// Clear everything that shows one library's data (filter screen, stats, gallery, open viewer), so a
// deleted or previously selected library can never stay on screen.
function resetLibraryUI() {
  state.libraryId = null; state.offset = 0; state.total = 0;
  fs.tab = null; fs.offset = 0; fs.total = 0; fs.items.clear(); fs.token++;
  if ($("viewer").open) $("viewer").close();
  $("reviewCard").hidden = true;
  ["fsHeadline", "fsFeedback", "fsReasons", "fsHint", "fsGrid", "fsDups", "reviewSummary",
   "stats", "years", "grid", "dupList", "errorList", "resultInfo"].forEach((id) => { $(id).innerHTML = ""; });
  $("fsMore").hidden = true; $("moreBtn").hidden = true;
}

async function selectLibrary(id) {
  if (state.libraryId !== id) resetLibraryUI();  // never show the previous library's data
  state.libraryId = id;
  await refreshStats();
  await reloadGallery();
}

async function addLibrary() {
  const path = $("pathInput").value.trim();
  $("formError").textContent = "";
  if (!path) { $("formError").textContent = "יש להזין נתיב לתיקייה"; return; }
  $("addBtn").disabled = true;
  try {
    const res = await api("/api/libraries", { method: "POST", body: JSON.stringify({ path }) });
    await loadLibraries(res.library.id);
  } catch (e) { $("formError").textContent = e.message; }
  finally { $("addBtn").disabled = false; }
}

async function browse(ev) {
  ev?.preventDefault();
  try {
    const res = await api("/api/system/pick-folder", { method: "POST" });
    if (res.path) $("pathInput").value = res.path;
  } catch (e) { $("formError").textContent = e.message; }
}

// ----------------------------------------------------------- folder browser
// Read-only in-app folder browser (ADR-014): navigate folders and scroll through their photos
// before choosing. Pages of items are fetched as the user scrolls; thumbnails are requested only
// when a tile comes near the visible area.
const FB_PAGE = 200;
const fb = { path: null, offset: 0, total: 0, loading: false, token: 0, imgObserver: null, pageObserver: null };
const fmtSize = (b) => (b >= 1073741824 ? `${(b / 1073741824).toFixed(1)}GB` : b >= 1048576 ? `${(b / 1048576).toFixed(1)}MB` : `${Math.max(1, Math.round(b / 1024))}KB`);

async function openFolderBrowser() {
  $("fbDialog").showModal();
  if (!fb.imgObserver) {
    fb.imgObserver = new IntersectionObserver((entries) => entries.forEach((en) => {
      if (!en.isIntersecting) return;
      const img = en.target; img.src = img.dataset.src; fb.imgObserver.unobserve(img);
    }), { root: $("fbMain"), rootMargin: "600px 0px" });
    fb.pageObserver = new IntersectionObserver((entries) => {
      if (entries.some((en) => en.isIntersecting)) fbLoadPage();
    }, { root: $("fbMain"), rootMargin: "800px 0px" });
    fb.pageObserver.observe($("fbSentinel"));
  }
  let places = [];
  try { places = (await api("/api/browse/roots")).locations; } catch (e) { $("fbMsg").textContent = e.message; }
  const icon = { pictures: "🖼️", desktop: "🖥️", cloud: "☁️", home: "🏠", drive: "💽" };
  $("fbPlaces").innerHTML = places.map((p) =>
    `<button class="fb-place" data-path="${esc(p.path)}" title="${esc(p.path)}">${icon[p.kind] || "📁"} <span>${esc(p.label)}</span></button>`).join("");
  $("fbPlaces").querySelectorAll(".fb-place").forEach((b) => b.addEventListener("click", () => fbNavigate(b.dataset.path)));
  const typed = $("pathInput").value.trim().replace(/^"|"$/g, "");
  const start = fb.path || typed || places[0]?.path;
  if (start) fbNavigate(start, typed && !fb.path ? places[0]?.path : null);
}

async function fbNavigate(path, fallback = null) {
  const token = ++fb.token;
  fb.path = null; fb.offset = 0; fb.total = 0; fb.loading = false;
  fb.imgObserver.disconnect();  // tiles of the previous folder are about to be removed
  $("fbGrid").innerHTML = ""; $("fbFolders").innerHTML = ""; $("fbMsg").textContent = "טוען…";
  $("fbChoose").disabled = true; $("fbMain").scrollTop = 0;
  let res;
  try { res = await api(`/api/browse?${new URLSearchParams({ path, offset: 0, limit: FB_PAGE })}`); }
  catch (e) {
    if (token !== fb.token) return;
    if (fallback) return fbNavigate(fallback);
    $("fbMsg").textContent = `לא ניתן לפתוח את התיקייה: ${e.message}`; return;
  }
  if (token !== fb.token) return;  // the user already navigated elsewhere
  fb.path = res.path;
  $("fbChoose").disabled = false;
  $("fbUp").disabled = !res.parent;
  $("fbUp").dataset.path = res.parent || "";
  $("fbCrumbs").innerHTML = res.breadcrumbs.map((c) => `<a href="#" data-path="${esc(c.path)}">${esc(c.name)}</a>`).join(" ‹ ");
  $("fbCrumbs").querySelectorAll("a").forEach((a) => a.addEventListener("click", (e) => { e.preventDefault(); fbNavigate(a.dataset.path); }));
  $("fbCrumbs").scrollLeft = -$("fbCrumbs").scrollWidth;  // RTL: keep the current folder in view
  $("fbFolders").innerHTML = res.folders.map((f) => `<button class="fb-folder" data-path="${esc(f.path)}" title="${esc(f.name)}">📁 <span>${esc(f.name)}</span></button>`).join("");
  $("fbFolders").querySelectorAll(".fb-folder").forEach((b) => b.addEventListener("click", () => fbNavigate(b.dataset.path)));
  const c = res.counts;
  $("fbCounts").textContent = [`${num(c.images)} תמונות`, `${num(c.videos)} סרטונים`, c.folders ? `${num(c.folders)} תתי-תיקיות (ייכללו בסריקה)` : "אין תתי-תיקיות"]
    .concat(c.cloud_only ? [`${num(c.cloud_only)} נמצאים רק בענן`] : []).join(" · ");
  fbAppend(res);
}

function fbAppend(res) {
  fb.total = res.total;
  fb.offset = res.offset + res.items.length;
  $("fbGrid").insertAdjacentHTML("beforeend", res.items.map((it) => {
    let inner;
    if (it.kind === "video") inner = `<div class="fb-icon">🎬</div><span class="badge">וידאו</span>`;
    else if (it.cloud_only) inner = `<div class="fb-icon">☁️</div><span class="badge">רק בענן — לא הורד</span>`;
    else inner = `<img data-src="${esc(it.thumbnail_url)}" alt="" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'fb-icon',textContent:'⚠️'}))">`;
    return `<div class="fb-tile ${it.kind}" title="${esc(it.name)} · ${fmtSize(it.size)}">${inner}<div class="fb-name">${esc(it.name)}</div></div>`;
  }).join(""));
  $("fbGrid").querySelectorAll("img[data-src]:not([src])").forEach((img) => fb.imgObserver.observe(img));
  $("fbMsg").textContent = fb.total === 0
    ? (res.folders?.length ? "אין תמונות או סרטונים ישירות בתיקייה הזו — ראו תתי-תיקיות למעלה" : "התיקייה ריקה מתמונות וסרטונים")
    : fb.offset < fb.total ? `מוצגים ${num(fb.offset)} מתוך ${num(fb.total)} — גללו לעוד` : "";
}

async function fbLoadPage() {
  if (!fb.path || fb.loading || fb.offset >= fb.total) return;
  const token = fb.token;
  fb.loading = true;
  try {
    const res = await api(`/api/browse?${new URLSearchParams({ path: fb.path, offset: fb.offset, limit: FB_PAGE })}`);
    if (token === fb.token) fbAppend(res);
  } catch (e) { if (token === fb.token) $("fbMsg").textContent = e.message; }
  finally { if (token === fb.token) fb.loading = false; }
  // If the new page still does not fill the view, keep going.
  if (token === fb.token) { const s = $("fbSentinel").getBoundingClientRect(), m = $("fbMain").getBoundingClientRect(); if (s.top < m.bottom + 800) fbLoadPage(); }
}

// ------------------------------------------------------------------- stats
function statTile(value, label, filter) {
  return `<div class="stat" ${filter ? `data-filter="${filter}"` : ""}><b>${value}</b><span>${label}</span></div>`;
}

async function refreshStats() {
  if (!state.libraryId) return;
  const { stats: s, latest_job: job } = await api(`/api/libraries/${state.libraryId}/stats`);
  const perK = job?.stats?.seconds_per_1000;
  $("stats").innerHTML = [
    statTile(num(s.indexed), "תמונות באינדקס", "all"),
    statTile(num(s.unique_photos), "ייחודיות", "unique"),
    statTile(`${num(s.redundant_duplicates)} <small>(${s.duplicate_reduction_pct}%)</small>`, "כפילויות מיותרות", "duplicates"),
    statTile(num(s.blurry), "מטושטשות", "blurry"),
    statTile(num(s.extreme_low_res), "איכות נמוכה מדי", "extreme_low_res"),
    statTile(num(s.screenshots), "צילומי מסך", "screenshots"),
    statTile(num(s.exposure_issues), "בעיות חשיפה", "exposure"),
    statTile(num(s.with_gps), "עם GPS", "gps"),
    statTile(num(s.date_from_file_mtime), "ללא תאריך צילום", "no_date"),
    statTile(num(s.errors), "נכשלו", "errors"),
    statTile(`${fmtDate(s.earliest).slice(0, 7)} ← ${fmtDate(s.latest).slice(0, 7)}`, "טווח תאריכים"),
    statTile(perK != null ? `${perK} שנ׳` : "—", "זמן עיבוד ל-1,000 תמונות"),
  ].join("");
  $("stats").querySelectorAll("[data-filter]").forEach((el) =>
    el.addEventListener("click", () => { $("viewSelect").value = "grid"; $("filterSelect").value = el.dataset.filter; reloadGallery(); }));

  const max = Math.max(1, ...s.years.map((y) => y.count));
  $("years").innerHTML = s.years.map((y) =>
    `<div class="bar" data-year="${y.year}" title="${y.year}: ${y.count}" style="height:${Math.max(4, (y.count / max) * 80)}px"><small>${y.year}</small></div>`).join("");
  $("years").querySelectorAll(".bar").forEach((b) => b.addEventListener("click", () => { $("yearSelect").value = b.dataset.year; reloadGallery(); }));

  const cur = $("yearSelect").value;
  $("yearSelect").innerHTML = `<option value="">כל השנים</option>` + s.years.map((y) => `<option value="${y.year}">${y.year} (${y.count})</option>`).join("");
  $("yearSelect").value = s.years.some((y) => y.year === cur) ? cur : "";

  showJob(job);
  refreshReview();
}

// --------------------------------------------------------------------- jobs
function showJob(job) {
  const active = job && (job.status === "queued" || job.status === "running");
  $("jobBox").hidden = !job;
  $("rescanBtn").disabled = active;
  $("deleteBtn").disabled = active;
  $("cancelBtn").hidden = !active;
  if (!job) return;
  const pct = job.total ? Math.round((100 * job.processed) / job.total) : (job.status === "done" ? 100 : 0);
  $("progressBar").style.width = `${pct}%`;
  let text = `${PHASE_HE[job.phase] || job.phase || job.status} · ${num(job.processed)}/${num(job.total)}`;
  if (job.errors) text += ` · ${num(job.errors)} שגיאות`;
  if (job.status === "done" && job.stats) {
    text = `הסריקה האחרונה הסתיימה · ${num(job.stats.files_found)} קבצים · ${num(job.stats.analyzed)} נותחו · ${num(job.stats.skipped_unchanged)} ללא שינוי · ${job.stats.elapsed_s} שניות`;
  }
  if (job.status === "failed") text = `הסריקה נכשלה: ${job.message}`;
  if (job.status === "interrupted") text = "הסריקה הקודמת נקטעה — לחץ 'סריקה מחדש'";
  $("jobText").textContent = text;

  if (active && !state.pollTimer) {
    state.pollTimer = setInterval(pollJob, 1000);
  }
  state.lastJob = job;
}

async function pollJob() {
  const job = state.lastJob;
  if (!job) return;
  const fresh = await api(`/api/jobs/${job.id}`).catch(() => null);
  if (!fresh) return;
  showJob(fresh);
  if (fresh.status !== "queued" && fresh.status !== "running") {
    clearInterval(state.pollTimer); state.pollTimer = null;
    await loadLibraries(state.libraryId);
  } else if (fresh.processed && fresh.processed % 200 < 20) {
    // Occasionally refresh counts while scanning.
    refreshStats();
  }
}

// ------------------------------------------------------------------ gallery
function tileHtml(p, extraClass = "") {
  const badges = (p.signals || []).map((s) => { const [t, cls] = SIGNAL_HE[s] || [s, ""]; return `<span class="badge ${cls}">${esc(t)}</span>`; }).join("");
  const img = p.thumbnail_url ? `<img loading="lazy" src="${p.thumbnail_url}" alt="">` : "";
  const rv = p.review_verdict ? reviewMark(p.review_verdict) : "";
  return `<div class="tile ${extraClass}" data-id="${p.id}">${img}<div class="badges">${badges}</div><div class="date">${fmtDate(p.capture_time)}</div>${rv}</div>`;
}

const reviewMark = (verdict) => `<span class="rv ${verdict}" title="${verdict === "good" ? "נבדקה: נראית טוב" : "נבדקה: לא מתאימה"}">${verdict === "good" ? "✓" : "✗"}</span>`;

function bindTiles(root) {
  root.querySelectorAll(".tile").forEach((t) => t.addEventListener("click", () => openViewer(Number(t.dataset.id), root)));
}

async function reloadGallery() {
  state.offset = 0;
  $("grid").innerHTML = ""; $("dupList").innerHTML = ""; $("errorList").innerHTML = "";
  await loadMore();
}

async function loadMore() {
  if (!state.libraryId) return;
  const view = $("viewSelect").value;
  ["filterSelect", "yearSelect", "sortSelect"].forEach((id) => ($(id).disabled = view === "dups"));
  if (view === "dups") {
    const res = await api(`/api/libraries/${state.libraryId}/duplicates?offset=${state.offset}&limit=30`);
    state.total = res.total;
    const html = res.groups.map((g) => `
      <div class="dup-group">
        <div class="muted">${g.kind === "exact" ? "כפילות מדויקת (אותו קובץ)" : "כמעט-זהות (גודל/דחיסה/צילום רצף)"} · ${g.size} תמונות · הירוקה נבחרה כטובה ביותר</div>
        <div class="grid">${g.members.map((m) => tileHtml(m, m.is_group_best ? "best" : "")).join("")}</div>
      </div>`).join("");
    $("dupList").insertAdjacentHTML("beforeend", html);
    bindTiles($("dupList"));
    state.offset += res.groups.length;
    $("resultInfo").textContent = `${num(res.total)} קבוצות כפילויות`;
  } else {
    const params = new URLSearchParams({ library_id: state.libraryId, filter: $("filterSelect").value, sort: $("sortSelect").value, offset: state.offset, limit: PAGE });
    if ($("yearSelect").value) params.set("year", $("yearSelect").value);
    const res = await api(`/api/photos?${params}`);
    state.total = res.total;
    if ($("filterSelect").value === "errors" || $("filterSelect").value === "missing") {
      $("errorList").insertAdjacentHTML("beforeend", res.items.map((p) =>
        `<div class="errrow"><span class="ltr">${esc(p.rel_path)}</span><br><span class="muted ltr">${esc(p.error || "הקובץ לא נמצא בתיקייה")}</span></div>`).join(""));
    } else {
      $("grid").insertAdjacentHTML("beforeend", res.items.map((p) => tileHtml(p)).join(""));
      bindTiles($("grid"));
    }
    state.offset += res.items.length;
    $("resultInfo").textContent = `${num(res.total)} תמונות`;
  }
  $("moreBtn").hidden = state.offset >= state.total;
}

// ------------------------------------------------------------ review viewer
// Full-screen viewer for human review (ADR-018), designed for a non-technical reviewer:
// the photo fills the screen, ONE plain verdict (the filter's decision) and two big buttons.
// Print sizes are never shown to customers (ADR-017); measurements are developer-only (?debug).
const REASONS_HE = { blurry: "מטושטשת", exposure: "חשוכה / בהירה מדי", low_res: "איכות נמוכה", other: "אחר" };
const LEVEL_HE = { excellent: ["מצוין", "lv-excellent"], good: ["טוב", "lv-good"], acceptable: ["סביר", "lv-acceptable"],
  poor: ["לא מומלץ בגודל הזה", "lv-poor"] };
const viewer = { ids: [], index: -1, photo: null, zoomed: false, token: 0, container: null };
// Developer-only: technical measurements (incl. print suitability) appear with ?debug in the URL.
const DEBUG = new URLSearchParams(location.search).has("debug");
$("vTech").hidden = !DEBUG;
$("stats").hidden = $("years").hidden = !DEBUG;  // technical counts; customers use the filter screen
try { $("vAdvance").checked = localStorage.getItem("reviewAdvance") !== "0"; } catch (_) { $("vAdvance").checked = true; }

function openViewer(id, container) {
  viewer.container = container || null;
  viewer.ids = container ? [...container.querySelectorAll(".tile")].map((t) => Number(t.dataset.id)) : [id];
  viewer.index = viewer.ids.indexOf(id);
  if (!$("viewer").open) $("viewer").showModal();
  showInViewer(id);
}

async function showInViewer(id) {
  const token = ++viewer.token;
  let p;
  try { p = await api(`/api/photos/${id}`); }
  catch (e) { $("vVerdict").innerHTML = `<div class="error">${esc(e.message)}</div>`; return; }
  if (token !== viewer.token) return;  // the user already moved on
  viewer.photo = p;
  const i = viewer.ids.indexOf(id);
  if (i >= 0) viewer.index = i;
  showPhotoMode();
  $("vPos").textContent = viewer.index >= 0 ? `${viewer.index + 1} / ${num(Math.max(viewer.ids.length, state.total))}` : "";
  $("vPrev").disabled = viewer.index <= 0;
  $("vNext").disabled = viewer.index < 0 || (viewer.index >= viewer.ids.length - 1 && !canLoadMore());
  renderVerdict(p);
  renderReview(p);
  renderInfo(p);
}

const canLoadMore = () => viewer.container === $("grid") && state.offset < state.total;

async function stepViewer(delta) {
  if (viewer.index < 0) return;
  const next = viewer.index + delta;
  if (next >= viewer.ids.length && canLoadMore()) {
    await loadMore();
    viewer.ids = [...$("grid").querySelectorAll(".tile")].map((t) => Number(t.dataset.id));
  }
  if (next < 0 || next >= viewer.ids.length) return;
  viewer.index = next;
  showInViewer(viewer.ids[next]);
}

// --- stage: the photo always fills the available area
function showPhotoMode() {
  const p = viewer.photo, img = $("vImg");
  viewer.zoomed = false;
  $("vStage").classList.remove("zoomed");
  $("vZoom").textContent = "🔍 100%";
  img.onload = () => { $("vLoading").hidden = true; updateUpscaleNote(); };
  img.onerror = () => { $("vLoading").hidden = true; };
  const src = p?.preview_url || p?.thumbnail_url || "";
  if (img.getAttribute("src") !== src) { $("vLoading").hidden = false; img.src = src; } else updateUpscaleNote();
}

function updateUpscaleNote() {
  // A small photo is enlarged to fill the screen and drawn with visible pixels on purpose:
  // that blockiness is the honest picture of how little detail the file has.
  const p = viewer.photo, img = $("vImg"), stage = $("vStage");
  if (!p || viewer.zoomed) return;
  const scale = Math.min(stage.clientWidth / p.width, stage.clientHeight / p.height);
  const upscaled = scale > 1.5;
  img.classList.toggle("pixelated", upscaled);
  $("vStageNote").hidden = !upscaled;
  if (upscaled) $("vStageNote").textContent = "הקובץ הזה שמור באיכות נמוכה מאוד — לכן הוא נראה מפוקסל כשמגדילים אותו";
}

function setZoom(on) {
  const p = viewer.photo;
  if (!p?.original_url) return;
  if (!on) { showPhotoMode(); return; }
  viewer.zoomed = true;
  $("vStage").classList.add("zoomed");
  $("vStageNote").hidden = true;
  $("vImg").classList.remove("pixelated");
  $("vZoom").textContent = "↩ התאמה למסך";
  $("vLoading").hidden = false;
  $("vImg").onload = () => {
    $("vLoading").hidden = true;
    const stage = $("vStage"), img = $("vImg");
    stage.scrollLeft = (img.naturalWidth - stage.clientWidth) / 2;  // stage is direction: ltr
    stage.scrollTop = (img.naturalHeight - stage.clientHeight) / 2;
  };
  $("vImg").src = p.original_url;
}

// --- plain verdict (traffic light) + at most two short issues
const isDupAlt = (p) => !!p.duplicate_group_id && !p.is_group_best;

// Technical reasons only (never a judgment about content, ADR-018). Duplicates are separate.
function issuesOf(p) {
  const out = [];
  if (p.is_screenshot) out.push("צילום מסך");
  if (p.print?.extremely_low) out.push("איכות ירודה (קטנה מדי)");
  else if (p.is_blurry) out.push("איכות ירודה (מטושטשת)");
  if (p.exposure_issue === "underexposed") out.push("חשוכה");
  if (p.exposure_issue === "overexposed") out.push("בהירה מדי");
  return out;
}

function renderVerdict(p) {
  // Customers never see print sizes (ADR-017 revision): the box shows only the filter's decision.
  // Same rule as the server: duplicates are resolved per group; a label overrides technical reasons.
  let issues = issuesOf(p);
  const r = p.review?.verdict;
  let cls, text;
  if (isDupAlt(p)) { cls = "amber"; text = "הסינון הציע להוציא — עותק כפול"; issues = ["נשאר עותק אחר שלה · אפשר להחליף בלשונית עותקים כפולים"]; }
  else if (r === "bad") { cls = "red"; text = "✗ הוצאת אותה מהבחירה"; }
  else if (r === "good" && issues.length) { cls = "green"; text = "↩ החזרת אותה לבחירה"; }
  else if (issues.length) { cls = "amber"; text = "הסינון הציע להוציא — פחות מתאימה כרגע לאלבום"; }
  else { cls = "green"; text = "✅ נשארה בבחירה"; }
  $("vVerdict").className = `v-verdict ${cls}`;
  $("vVerdict").textContent = text;
  $("vIssues").innerHTML = issues.length
    ? `${r === "good" && !isDupAlt(p) ? "למרות:" : "סיבה:"} ${issues.map((s) => `<span class="v-issue">${s}</span>`).join(" ")}`
    : "";
}

// --- human label: two big buttons; reasons only after "not good"
function renderReview(p) {
  const r = p.review;
  $("vReviewState").textContent = !r ? "" : r.verdict === "good" ? "✓ סימנת: טובה" : "✗ סימנת: לא טובה";
  $("vReviewState").className = `v-state ${r ? r.verdict : ""}`;
  $("vGood").classList.toggle("active", r?.verdict === "good");
  $("vBad").classList.toggle("active", r?.verdict === "bad");
  $("vAfterBad").hidden = r?.verdict !== "bad";
  const chosen = new Set(r?.reasons || []);
  $("vReasons").innerHTML = Object.entries(REASONS_HE).map(([k, t]) =>
    `<button class="chip ${chosen.has(k) ? "on" : ""}" data-reason="${k}">${t}</button>`).join("");
  $("vReasons").querySelectorAll(".chip").forEach((b) => b.addEventListener("click", () => toggleReason(b.dataset.reason)));
  $("vNote").value = r?.note || "";
  $("vNote").hidden = !r?.note;
  $("vNoteLink").hidden = !!r?.note;
  $("vClear").hidden = !r;
}

async function saveReview(verdict, reasons) {
  const p = viewer.photo;
  if (!p) return false;
  try {
    p.review = await api(`/api/photos/${p.id}/review`, { method: "PUT",
      body: JSON.stringify({ verdict, reasons: [...reasons], note: $("vNote").value }) });
  } catch (e) { alert(`השמירה נכשלה: ${e.message}`); return false; }
  renderReview(p);
  renderVerdict(p);
  markTile(p.id, verdict);
  refreshReview();
  return true;
}

async function markGood() {
  if (await saveReview("good", []) && $("vAdvance").checked) stepViewer(1);
}

async function markBad() {
  const p = viewer.photo;
  // "Not good" stays on the photo so the optional reasons can be picked; "המשך" / ← moves on.
  if (p?.review?.verdict === "bad") { stepViewer(1); return; }  // pressing 2 again = continue
  await saveReview("bad", []);
}

function toggleReason(reason) {
  const reasons = new Set(viewer.photo?.review?.reasons || []);
  reasons.has(reason) ? reasons.delete(reason) : reasons.add(reason);
  saveReview("bad", reasons);
}

async function clearReview() {
  const p = viewer.photo;
  if (!p?.review) return;
  await api(`/api/photos/${p.id}/review`, { method: "DELETE" }).catch((e) => alert(e.message));
  p.review = null;
  renderReview(p);
  markTile(p.id, null);
  refreshReview();
}

function markTile(id, verdict, fromFilterScreen = false) {
  if (!fromFilterScreen) fsOnLabel(id, verdict);
  document.querySelectorAll(`.tile:not(.fs-tile)[data-id="${id}"]`).forEach((t) => {
    t.querySelector(".rv")?.remove();
    if (verdict) t.insertAdjacentHTML("beforeend", reviewMark(verdict));
  });
}

// --- technical details (collapsed by default)
function row(label, value, status = "") {
  return `<tr class="${status}"><td>${label}</td><td>${value}</td></tr>`;
}
const flagCell = (on, yes, no = "תקין") => (on ? `<b class="flag">⚠ ${yes}</b>` : `<span class="okv">✓ ${no}</span>`);
const pct = (x) => (x == null ? "—" : `${(x * 100).toFixed(1)}%`);

function renderInfo(p) {
  const a = p.analysis, pr = p.print;
  let html = "";
  if (pr) {
    const lv = pr.policy.levels_ppi;
    html += `<section><h3>הדפסה</h3><table>${row("פיקסלים", `<span class="ltr">${pr.width}×${pr.height}</span> · ${pr.megapixels}MP`)}
      ${row(`מקסימום ב-${lv.excellent} PPI`, `<span class="ltr">${pr.max_size_cm.excellent.join("×")} ס״מ</span>`)}
      ${row(`מקסימום ב-${lv.good} PPI`, `<span class="ltr">${pr.max_size_cm.good.join("×")} ס״מ</span>`)}
      ${row(`מקסימום ב-${lv.acceptable} PPI`, `<span class="ltr">${pr.max_size_cm.acceptable.join("×")} ס״מ</span>`)}</table>
      <table class="print-sizes"><tr><th>גודל</th><th>PPI</th><th>איכות</th></tr>
      ${pr.sizes.map((s) => { const [t, cls] = LEVEL_HE[s.level]; return `<tr><td class="ltr">${esc(s.label)}</td><td>${s.ppi}</td><td><span class="lv ${cls}">${t}</span></td></tr>`; }).join("")}</table>
      <div class="muted">מילוי משבצת (חיתוך העודף). ${lv.excellent}/${lv.good}/${lv.acceptable} PPI וגודל המשבצת הקטנה (${esc(pr.policy.min_slot)}) הם ברירות מחדל זמניות — יוחלפו במפרט ספק ההדפסה. רזולוציה לעולם לא מוציאה תמונה.</div></section>`;
  }
  if (a) {
    const s = a.sharpness, ex = a.exposure, q = a.quality;
    const dupState = !p.duplicate_group_id ? "אין" : p.is_group_best ? "הטובה בקבוצה" : "חלופה — יש עותק טוב יותר";
    html += `<section><h3>ניתוח אוטומטי <span class="muted">(כללים קלאסיים, לא AI · ${esc(a.analyzer)})</span></h3><table>
      ${row("חדות", `${s.value} <span class="muted">(סף טשטוש: מתחת ל-${s.blur_threshold})</span> ${flagCell(s.is_blurry, "מטושטשת")}`)}
      ${row("בהירות ממוצעת", `${ex.brightness} <span class="muted">/255</span>`)}
      ${row("פיקסלים כהים / בהירים", `${pct(ex.dark_fraction)} / ${pct(ex.bright_fraction)}`)}
      ${row("חשיפה", `${flagCell(!!ex.issue, ex.issue === "underexposed" ? "חשוכה" : "בהירה מדי")}<br><span class="muted ltr">${esc(ex.issue ? ex.rules[ex.issue] : `${ex.rules.underexposed}; ${ex.rules.overexposed}`)}</span>`)}
      ${row("ניגודיות", a.contrast)}
      ${row("צילום מסך", flagCell(a.screenshot.is_screenshot, `כן (${esc(a.screenshot.reason || "")})`, "לא"))}
      ${row("כפילות", dupState)}
      ${row("ציון איכות טכנית", `${Math.round(q.score * 100)}/100 <span class="muted ltr">= ${Object.entries(q.weights).map(([k, w]) => `${w}·${k}(${q.components[k]})`).join(" + ")}</span>`)}
      </table></section>`;
  }
  const mismatch = p.extension_matches_format ? "" : ` <b class="flag">⚠ הסיומת לא תואמת את התוכן</b>`;
  html += `<section><h3>קובץ</h3><table>
    ${row("נתיב", `<span class="ltr">${esc(p.rel_path)}</span>`)}
    ${row("פורמט אמיתי", `${esc(p.format)}${mismatch}`)}
    ${row("גודל קובץ", fmtSize(p.file_size || 0))}
    ${row("תאריך צילום", `${fmtDate(p.capture_time)} · <span class="muted">${DATE_SRC_HE[p.capture_time_source] || "—"}</span>`)}
    ${row("מצלמה", esc([p.camera_make, p.camera_model].filter(Boolean).join(" ") || "—"))}
    ${row("מיקום", p.gps_lat != null ? `<a target="_blank" rel="noopener" href="https://www.openstreetmap.org/?mlat=${p.gps_lat}&mlon=${p.gps_lon}#map=15/${p.gps_lat}/${p.gps_lon}">${p.gps_lat.toFixed(5)}, ${p.gps_lon.toFixed(5)}</a>` : "—")}
    </table></section>`;
  if (p.duplicates?.length) {
    html += `<section><h3>תמונות דומות (${p.duplicates.length})</h3><div class="grid v-dups">${p.duplicates.map((m) => tileHtml(m, m.is_group_best ? "best" : "")).join("")}</div></section>`;
  }
  $("vInfo").innerHTML = html;
  $("vInfo").querySelectorAll(".tile").forEach((t) => t.addEventListener("click", () => showInViewer(Number(t.dataset.id))));
}

// ----------------------------------------------------- "what did the filter do?"
// The main review flow (ADR-018): a summary of the automatic filter's decisions per reason, big
// thumbnails, and one-tap corrections. Nothing is deleted: a filtered photo is always one click away,
// and a correction is a human label that overrides the automatic decision.
const FS_TABS = [
  // key, label, API filter ("dups" = duplicate groups view), mode
  // Every filtered photo sits in exactly one tab: its primary reason (server-side `reason_*`).
  ["duplicate", "עותקים כפולים", "dups", "filtered"],
  ["screenshot", "צילומי מסך", "reason_screenshot", "filtered"],
  ["low_quality", "איכות ירודה", "reason_low_quality", "filtered"],
  ["exposure", "חשוכות / בהירות מדי", "reason_exposure", "filtered"],
  ["manual", "הוצאת ידנית", "reason_manual", "filtered"],
  ["kept", "נשארו בבחירה", "kept", "kept"],
  ["mistakes", "השינויים שלך", "changes", "mixed"],
];
const FS_HINTS = {
  filtered: "הסינון הציע להוציא את אלה מסיבה טכנית בלבד. רוצים תמונה בבחירה? לחצו ↩ להחזיר לבחירה.",
  kept: "אלה התמונות שנשארו בבחירה. תמונה שלא רוצים? לחצו ✗ להוציא מהבחירה.",
  dups: "מכל קבוצת עותקים נשארת תמונה אחת בלבד (⭐). רוצים עותק אחר? לחצו שמור את זו במקום.",
  mixed: "כאן כל התמונות שבהן שינית את הצעת הסינון. אפשר לבטל כל שינוי.",
};
const fs = { tab: null, offset: 0, total: 0, items: new Map(), token: 0 };

async function refreshFilterSummary() {
  const lib = state.libraryId;
  if (!lib) return;
  let s;
  try { s = await api(`/api/libraries/${lib}/filter/summary`); } catch (_) { return; }
  if (lib !== state.libraryId) return;  // the library changed or was deleted meanwhile
  $("reviewCard").hidden = false;
  $("fsHeadline").innerHTML = `מתוך <b>${num(s.total)}</b> תמונות: <span class="fs-kept">${num(s.kept)} נשארו בבחירה</span> · <span class="fs-filtered">הסינון הציע להוציא ${num(s.filtered)}</span>
    <div class="fs-sub">שום דבר לא נמחק · אפשר להחזיר כל תמונה · הסינון בודק רק דברים טכניים: עותקים כפולים, צילומי מסך, איכות ותאורה</div>`;
  const f = s.feedback, fixes = f.restored + f.should_filter + f.duplicate_picks_changed;
  $("fsFeedback").innerHTML = fixes
    ? `✍️ שינית <b>${num(fixes)}</b> הצעות של הסינון` + [
      f.restored ? `${num(f.restored)} הוחזרו לבחירה` : "", f.should_filter ? `${num(f.should_filter)} הוצאו ידנית` : "",
      f.duplicate_picks_changed ? `${num(f.duplicate_picks_changed)} החלפות עותק` : ""].filter(Boolean).map((x) => ` · ${x}`).join("")
    : "עוד לא שינית כלום. עברו על הסיבות למטה — זה מהיר.";
  const counts = { ...s.by_reason, kept: s.kept, mistakes: f.restored + f.should_filter };
  $("fsReasons").innerHTML = FS_TABS.map(([key, label]) =>
    `<button class="fs-tab ${key === fs.tab ? "on" : ""} ${key === "kept" ? "kept" : key === "mistakes" ? "mistakes" : ""}" data-tab="${key}" ${counts[key] ? "" : "disabled"}>${label} <b>${num(counts[key])}</b></button>`).join("");
  $("fsReasons").querySelectorAll(".fs-tab").forEach((b) => b.addEventListener("click", () => fsOpenTab(b.dataset.tab)));
  if (!fs.tab) {  // first visit: open the first reason that has photos
    const first = FS_TABS.find(([key, , , mode]) => mode === "filtered" && counts[key]) || FS_TABS.find(([key]) => key === "kept");
    if (first) fsOpenTab(first[0]);
  }
}

function fsOpenTab(key) {
  fs.tab = key; fs.offset = 0; fs.total = 0; fs.items.clear(); fs.token++;
  $("fsGrid").innerHTML = ""; $("fsDups").innerHTML = "";
  $("fsReasons").querySelectorAll(".fs-tab").forEach((b) => b.classList.toggle("on", b.dataset.tab === key));
  const [, , filter, mode] = FS_TABS.find(([k]) => k === key);
  $("fsHint").textContent = FS_HINTS[filter === "dups" ? "dups" : mode];
  fsLoadMore();
}

async function fsLoadMore() {
  const [, , filter, mode] = FS_TABS.find(([k]) => k === fs.tab);
  const token = fs.token;
  if (filter === "dups") {
    const res = await api(`/api/libraries/${state.libraryId}/duplicates?offset=${fs.offset}&limit=20`);
    if (token !== fs.token) return;
    fs.total = res.total;
    res.groups.forEach((g) => { g.members.forEach((m) => fs.items.set(m.id, m)); $("fsDups").insertAdjacentHTML("beforeend", fsGroupHtml(g)); });
    fs.offset += res.groups.length;
    fsBindGroups();
  } else {
    const res = await api(`/api/photos?${new URLSearchParams({ library_id: state.libraryId, filter, sort: "date", offset: fs.offset, limit: 60 })}`);
    if (token !== fs.token) return;
    fs.total = res.total;
    res.items.forEach((p) => fs.items.set(p.id, p));
    $("fsGrid").insertAdjacentHTML("beforeend", res.items.map((p) => fsTileHtml(p, mode)).join(""));
    fs.offset += res.items.length;
    fsBindTiles($("fsGrid"));
  }
  $("fsMore").hidden = fs.offset >= fs.total;
}

function fsTileHtml(p, mode) {
  const v = p.review_verdict;
  const m = mode === "mixed" ? (v === "good" ? "filtered" : "kept") : mode;
  const badges = (p.signals || []).filter((s) => s !== "Best of duplicate group")
    .map((s) => { const [t, cls] = SIGNAL_HE[s] || [s, ""]; return `<span class="badge ${cls}">${esc(t)}</span>`; }).join("");
  let action, stateCls = "";
  if (m === "filtered") {
    if (v === "good") { stateCls = "restored"; action = `<span class="fs-state">✓ הוחזרה לבחירה</span><button class="fs-undo" data-act="undo">ביטול</button>`; }
    else if (v === "bad") { stateCls = "removed"; action = `<span class="fs-state">✗ הוצאת אותה</span><button class="fs-undo" data-act="undo">ביטול</button>`; }
    else action = `<button class="fs-btn restore" data-act="good">↩ להחזיר לבחירה</button>`;
  } else if (v === "bad") { stateCls = "removed"; action = `<span class="fs-state">✗ הוצאה מהבחירה</span><button class="fs-undo" data-act="undo">ביטול</button>`; }
  else action = `<button class="fs-btn remove" data-act="bad">✗ להוציא מהבחירה</button>`;
  const img = p.thumbnail_url ? `<img loading="lazy" src="${p.thumbnail_url}" alt="">` : "";
  return `<div class="tile fs-tile ${stateCls}" data-id="${p.id}" data-mode="${m}">${img}<div class="badges">${badges}</div><div class="fs-action">${action}</div></div>`;
}

function fsBindTiles(root) {
  root.querySelectorAll(".fs-tile:not([data-bound])").forEach((t) => {
    t.dataset.bound = "1";
    t.addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-act]");
      if (!btn) { openViewer(Number(t.dataset.id), t.closest("#fsGrid, #fsDups")); return; }
      e.stopPropagation();
      fsAct(Number(t.dataset.id), btn.dataset.act);
    });
  });
}

async function fsAct(id, act) {
  try {
    if (act === "undo") await api(`/api/photos/${id}/review`, { method: "DELETE" });
    else await api(`/api/photos/${id}/review`, { method: "PUT", body: JSON.stringify({ verdict: act, reasons: [] }) });
  } catch (e) { alert(`השמירה נכשלה: ${e.message}`); return; }
  fsOnLabel(id, act === "undo" ? null : act);
  markTile(id, act === "undo" ? null : act, true);
  refreshReview();
}

// Keep a filter-screen tile in sync after a label changes anywhere (viewer or tile button).
function fsOnLabel(id, verdict) {
  const p = fs.items.get(id);
  if (!p) return;
  p.review_verdict = verdict;
  document.querySelectorAll(`.fs-tile[data-id="${id}"]`).forEach((t) => {
    if (t.closest("#fsDups")) { fsRerenderGroupOf(t); return; }
    t.outerHTML = fsTileHtml(p, t.dataset.mode);
  });
  fsBindTiles($("fsGrid"));
}

// --- duplicates: groups side by side, the kept photo marked, one tap to change it
function fsGroupHtml(g) {
  const changed = g.auto_best_photo_id && g.best_photo_id !== g.auto_best_photo_id;
  // Byte-identical copies of the kept photo: there is nothing to choose between them.
  const bestHash = g.members.find((m) => m.is_group_best)?.content_hash;
  const members = g.members.map((m) => {
    const img = m.thumbnail_url ? `<img loading="lazy" src="${m.thumbnail_url}" alt="">` : "";
    let action;
    if (m.is_group_best) action = `<span class="fs-state">⭐ נשמרת</span>`;
    else if (m.content_hash === bestHash) action = `<span class="fs-state">עותק זהה של הנשמרת</span>`;
    else action = `<button class="fs-btn restore" data-act="keep">שמור את זו במקום</button>`;
    const auto = changed && m.id === g.auto_best_photo_id ? `<span class="badge">המערכת בחרה בזו</span>` : "";
    const cls = m.is_group_best ? "best" : "";
    return `<div class="tile fs-tile ${cls}" data-id="${m.id}" data-mode="dup">${img}<div class="badges">${auto}</div><div class="fs-action">${action}</div></div>`;
  }).join("");
  return `<div class="fs-group" data-first="${g.members[0]?.id}">
    <div class="fs-group-head">${g.kind === "exact" ? `${g.size} עותקים זהים של אותו קובץ — נשאר אחד, אין מה לבחור` : `${g.size} תמונות כמעט זהות — נשארת אחת`} ${changed ? `· <b>שינית את הבחירה</b> · <a href="#" data-reset="${g.best_photo_id}">חזרה לבחירה האוטומטית</a>` : ""}</div>
    <div class="fs-group-row">${members}</div></div>`;
}

function fsBindGroups() {
  $("fsDups").querySelectorAll(".fs-group:not([data-bound])").forEach((gEl) => {
    gEl.dataset.bound = "1";
    gEl.addEventListener("click", async (e) => {
      const reset = e.target.closest("[data-reset]");
      const tile = e.target.closest(".fs-tile");
      const btn = e.target.closest("button[data-act]");
      if (reset) { e.preventDefault(); await fsPick(gEl, Number(reset.dataset.reset), "DELETE"); return; }
      if (!tile) return;
      const id = Number(tile.dataset.id);
      if (!btn) { openViewer(id, $("fsDups")); return; }
      if (btn.dataset.act === "keep") { await fsPick(gEl, id, "PUT"); return; }
      await fsAct(id, btn.dataset.act);
    });
  });
}

async function fsPick(gEl, photoId, method) {
  try { await api(`/api/photos/${photoId}/keep`, { method }); } catch (e) { alert(e.message); return; }
  await fsRerenderGroup(gEl, photoId);
  refreshReview();
}

async function fsRerenderGroupOf(tileEl) {
  const gEl = tileEl.closest(".fs-group");
  if (gEl) await fsRerenderGroup(gEl, Number(tileEl.dataset.id));
}

async function fsRerenderGroup(gEl, anyMemberId) {
  // Group ids change when groups are recomputed, so fetch the group again via one of its photos.
  const p = await api(`/api/photos/${anyMemberId}`);
  if (!p.duplicate_group) { gEl.remove(); return; }
  p.duplicate_group.members.forEach((m) => fs.items.set(m.id, m));
  gEl.outerHTML = fsGroupHtml(p.duplicate_group);
  fsBindGroups();
}

async function refreshReview() {
  refreshFilterSummary();
  if (!state.libraryId) return;
  const lib = state.libraryId;
  let s;
  try { s = await api(`/api/libraries/${lib}/review/stats`); } catch (_) { return; }
  if (lib !== state.libraryId) return;
  $("exportJson").href = `/api/libraries/${state.libraryId}/review/export?format=json`;
  $("exportCsv").href = `/api/libraries/${state.libraryId}/review/export?format=csv`;
  const FLAG_HE = { blurry: "טשטוש", exposure: "תאורה", screenshot: "צילום מסך", extreme_low_res: "קטנה מדי", duplicate: "עותק כפול" };
  const rows = Object.entries(s.flags).map(([k, f]) => `<tr><td>${FLAG_HE[k] || k}</td><td>${f.flagged_reviewed}</td>
    <td>${f.flagged_bad}</td><td>${f.flagged_good}</td><td>${f.flag_precision == null ? "—" : `${Math.round(f.flag_precision * 100)}%`}</td><td>${f.missed}</td></tr>`).join("");
  $("reviewSummary").innerHTML = `<div class="muted">נבדקו ${num(s.reviewed)} · טרם נבדקו ${num(s.unreviewed)} · הסכמה ${num(s.agree)} · אי-הסכמה ${num(s.disagree)}</div>
    ${s.reviewed ? `<table class="agree"><tr><th>סיבת סינון</th><th>נבדקו</th><th>אדם אישר את הסינון</th>
      <th>אדם החזיר (טעות)</th><th>דיוק</th><th>פוספסו</th></tr>${rows}</table>` : ""}`;
}

async function startReview() {
  $("viewSelect").value = "grid"; $("filterSelect").value = "unreviewed";
  await reloadGallery();
  const first = $("grid").querySelector(".tile");
  if (first) openViewer(Number(first.dataset.id), $("grid"));
  else alert("כל התמונות בסינון הזה כבר נבדקו");
}

// ------------------------------------------------------------------- wiring
$("addBtn").addEventListener("click", addLibrary);
$("pathInput").addEventListener("keydown", (e) => { if (e.key === "Enter") addLibrary(); });
$("browseBtn").addEventListener("click", browse);
$("folderBrowserBtn").addEventListener("click", openFolderBrowser);
$("fbUp").addEventListener("click", () => { if ($("fbUp").dataset.path) fbNavigate($("fbUp").dataset.path); });
$("fbClose").addEventListener("click", () => $("fbDialog").close());
$("fbChoose").addEventListener("click", () => {
  if (!fb.path) return;
  $("pathInput").value = fb.path; $("formError").textContent = "";
  $("fbDialog").close(); $("addBtn").focus();
});
$("librarySelect").addEventListener("change", (e) => selectLibrary(Number(e.target.value)));
$("rescanBtn").addEventListener("click", async () => { const job = await api(`/api/libraries/${state.libraryId}/scan`, { method: "POST" }); showJob(job); });
$("cancelBtn").addEventListener("click", async () => { if (state.lastJob) await api(`/api/jobs/${state.lastJob.id}/cancel`, { method: "POST" }); });
$("deleteBtn").addEventListener("click", async () => {
  if (!confirm("למחוק את כל נתוני האינדקס והתמונות הממוזערות של הספרייה? התמונות המקוריות לא יימחקו.")) return;
  try { await api(`/api/libraries/${state.libraryId}`, { method: "DELETE" }); resetLibraryUI(); $("jobBox").hidden = true; await loadLibraries(); }
  catch (e) { alert(e.message); }
});
["viewSelect", "filterSelect", "yearSelect", "sortSelect"].forEach((id) => $(id).addEventListener("change", reloadGallery));
$("moreBtn").addEventListener("click", loadMore);
$("vClose").addEventListener("click", () => $("viewer").close());
$("vPrev").addEventListener("click", () => stepViewer(-1));
$("vNext").addEventListener("click", () => stepViewer(1));
$("vZoom").addEventListener("click", () => setZoom(!viewer.zoomed));
$("vImg").addEventListener("click", () => setZoom(!viewer.zoomed));
$("vGood").addEventListener("click", markGood);
$("vBad").addEventListener("click", markBad);
$("vContinue").addEventListener("click", () => stepViewer(1));
$("vClear").addEventListener("click", (e) => { e.preventDefault(); clearReview(); });
$("vNoteLink").addEventListener("click", (e) => { e.preventDefault(); $("vNote").hidden = false; $("vNoteLink").hidden = true; $("vNote").focus(); });
$("vNote").addEventListener("change", () => { const r = viewer.photo?.review; if (r) saveReview(r.verdict, r.reasons); });
$("vAdvance").addEventListener("change", () => { try { localStorage.setItem("reviewAdvance", $("vAdvance").checked ? "1" : "0"); } catch (_) {} });
window.addEventListener("resize", updateUpscaleNote);
document.addEventListener("keydown", (e) => {
  if (!$("viewer").open || e.target.tagName === "TEXTAREA" || e.ctrlKey || e.altKey || e.metaKey) return;
  const actions = { ArrowLeft: () => stepViewer(1), ArrowRight: () => stepViewer(-1),  // RTL: left = next
    1: markGood, 2: markBad, 0: clearReview, z: () => setZoom(!viewer.zoomed), Z: () => setZoom(!viewer.zoomed) };
  if (actions[e.key]) { e.preventDefault(); actions[e.key](); }
});
$("viewer").addEventListener("close", () => { $("vImg").removeAttribute("src"); viewer.photo = null; });
$("reviewStartBtn").addEventListener("click", startReview);
$("fsMore").addEventListener("click", fsLoadMore);

$("reloadBtn").addEventListener("click", () => location.reload());
setInterval(checkForUpdate, 30000);
// Dev mode (start_dev.bat, ADR-020): reload by itself as soon as the server runs a new build.
if (document.querySelector('meta[name="app-dev-reload"]')) {
  setInterval(async () => {
    try {
      const h = await api("/api/health");
      if (h.build && h.build !== PAGE_BUILD) location.reload();
    } catch (_) { /* server restarting */ }
  }, 2000);
}
window.addEventListener("focus", checkForUpdate);
document.addEventListener("visibilitychange", () => { if (!document.hidden) checkForUpdate(); });

loadHealth();
loadLibraries().catch((e) => ($("formError").textContent = e.message));
