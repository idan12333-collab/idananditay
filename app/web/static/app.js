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
async function loadHealth() {
  try {
    const h = await api("/api/health");
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

async function browse() {
  $("browseBtn").disabled = true;
  try {
    const res = await api("/api/system/pick-folder", { method: "POST" });
    if (res.path) $("pathInput").value = res.path;
  } catch (e) { $("formError").textContent = e.message; }
  finally { $("browseBtn").disabled = false; }
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

loadHealth();
loadLibraries().catch((e) => ($("formError").textContent = e.message));
