"use strict";

const $ = (id) => document.getElementById(id);
const PAGE = 120;
const state = { libraryId: null, offset: 0, total: 0, pollTimer: null, lastJobStatus: null };

const SIGNAL_HE = {
  "Best of duplicate group": ["הטובה מהקבוצה", "best"],
  "Duplicate — alternate": ["כפילות", "warn"],
  "Blurry": ["מטושטשת", "warn"],
  "Low resolution": ["רזולוציה נמוכה", "warn"],
  "Screenshot": ["צילום מסך", "warn"],
  "Underexposed": ["חשוכה", "warn"],
  "Overexposed": ["שרופה", "warn"],
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
  $("galleryCard").hidden = libs.length === 0;
  if (!libs.length) { state.libraryId = null; return; }
  const id = selectId ?? state.libraryId ?? libs[libs.length - 1].id;
  sel.value = String(id);
  await selectLibrary(Number(sel.value));
}

async function selectLibrary(id) {
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
    statTile(num(s.low_res), "רזולוציה נמוכה", "low_res"),
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
  return `<div class="tile ${extraClass}" data-id="${p.id}">${img}<div class="badges">${badges}</div><div class="date">${fmtDate(p.capture_time)}</div></div>`;
}

function bindTiles(root) {
  root.querySelectorAll(".tile").forEach((t) => t.addEventListener("click", () => openDetail(Number(t.dataset.id))));
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

// ------------------------------------------------------------------- detail
async function openDetail(id) {
  const p = await api(`/api/photos/${id}`);
  $("detailImg").src = p.preview_url || p.thumbnail_url || "";
  const rows = [
    ["קובץ", `<span class="ltr">${esc(p.rel_path)}</span>`],
    ["תאריך צילום", `${fmtDate(p.capture_time)}${p.tz_offset ? ` (${esc(p.tz_offset)})` : ""}`],
    ["מקור התאריך", DATE_SRC_HE[p.capture_time_source] || "—"],
    ["מידות", `${p.width}×${p.height} (${((p.width * p.height) / 1e6).toFixed(1)}MP)`],
    ["פורמט", esc(p.format)],
    ["מצלמה", esc([p.camera_make, p.camera_model].filter(Boolean).join(" ") || "—")],
    ["מיקום", p.gps_lat != null ? `<a target="_blank" rel="noopener" href="https://www.openstreetmap.org/?mlat=${p.gps_lat}&mlon=${p.gps_lon}#map=15/${p.gps_lat}/${p.gps_lon}">${p.gps_lat.toFixed(5)}, ${p.gps_lon.toFixed(5)}</a>` : "—"],
    ["ציון איכות טכנית", p.quality_score != null ? `${Math.round(p.quality_score * 100)}/100` : "—"],
    ["חדות", p.sharpness ?? "—"],
    ["בהירות / ניגודיות", `${p.brightness ?? "—"} / ${p.contrast ?? "—"}`],
    ["סימונים", (p.signals || []).map((s) => (SIGNAL_HE[s] || [s])[0]).join(", ") || "—"],
    ["גודל קובץ", `${((p.file_size || 0) / 1024 / 1024).toFixed(2)}MB`],
  ];
  let html = `<table>${rows.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join("")}</table>`;
  if (p.duplicates?.length) {
    html += `<h3 style="font-size:14px">תמונות דומות בקבוצה (${p.duplicates.length})</h3><div class="grid">${p.duplicates.map((m) => tileHtml(m, m.is_group_best ? "best" : "")).join("")}</div>`;
  }
  $("detailInfo").innerHTML = html;
  bindTiles($("detailInfo"));
  if (!$("detail").open) $("detail").showModal();
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
  try { await api(`/api/libraries/${state.libraryId}`, { method: "DELETE" }); state.libraryId = null; $("jobBox").hidden = true; await loadLibraries(); }
  catch (e) { alert(e.message); }
});
["viewSelect", "filterSelect", "yearSelect", "sortSelect"].forEach((id) => $(id).addEventListener("change", reloadGallery));
$("moreBtn").addEventListener("click", loadMore);
$("closeDetail").addEventListener("click", () => $("detail").close());
$("detail").addEventListener("click", (e) => { if (e.target === $("detail")) $("detail").close(); });

$("reloadBtn").addEventListener("click", () => location.reload());
setInterval(checkForUpdate, 30000);
window.addEventListener("focus", checkForUpdate);
document.addEventListener("visibilitychange", () => { if (!document.hidden) checkForUpdate(); });

loadHealth();
loadLibraries().catch((e) => ($("formError").textContent = e.message));
