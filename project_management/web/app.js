/* Project-management dashboard. Plain JS, no dependencies.
 * All data is inserted with textContent / DOM nodes — never innerHTML — so nothing
 * from state.json, docs or transcripts can inject markup.
 *
 * Honesty rule: no button approves or executes anything. Buttons either open a
 * Claude conversation (and say what to type there) or prepare a message to paste
 * to the PM — and their labels say exactly that.
 */
"use strict";

const POLL_MS = 10000;
const RECENT_CHANGES = 5;
const DAILY_PREVIEW_LINES = 6;
let DATA = null;
let openWorkerId = null;

// ------------------------------------------------------------------ helpers
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "style") el.style.cssText = v;   // CSSOM: allowed under the strict CSP (attributes are not)
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
const $ = (id) => document.getElementById(id);
/* Replace a container's content, keeping every <details> the viewer opened/closed
 * as it was (the page re-renders every 10 s). Keyed by the summary's text. */
function fill(id, ...kids) {
  const el = $(id);
  const key = (d) => d.querySelector(":scope > summary")?.textContent.trim();
  const seen = new Map([...el.querySelectorAll("details")].map((d) => [key(d), d.open]));
  el.replaceChildren(...kids.flat().filter(Boolean));
  for (const d of el.querySelectorAll("details")) {
    const k = key(d);
    if (seen.has(k)) d.open = seen.get(k);
  }
  return el;
}
const empty = (text) => h("p", { class: "empty" }, text);

const STATUS_HE = {
  ACTIVE: "עובד עכשיו", WAITING: "ממתין", BLOCKED: "חסום", DONE: "סיים", PLANNED: "מתוכנן",
  UNKNOWN: "לא ידוע", PENDING_PM: "ממתין להחלטת המנהל", CANCELLED: "בוטל",
};
const MANUAL_HE = { not_needed: "לא נדרשת", required: "נדרשת בדיקה שלך", passed: "עברה", failed: "נכשלה" };
const TESTS_HE = { passed: "עברו", failed: "נכשלו", not_run: "לא הורצו" };
const LEVEL_HE = { healthy: "תקין", high: "מתחיל להיות גבוה", near: "קרוב לגבול", handoff: "מומלץ handoff" };
const ATT_HE = {
  manual_test: "בדיקה ידנית", approval: "אישור", permission: "הרשאה", commit: "אישור commit",
  product_decision: "החלטה שלך", conflict: "התנגשות", licensing_privacy: "רישוי / פרטיות",
};
const EVENT_HE = {
  started: "התחיל", paused: "נעצר", finished: "סיים", tests_passed: "בדיקות עברו", tests_failed: "בדיקות נכשלו",
  manual_test_requested: "התבקשה בדיקה ידנית", manual_test_passed: "בדיקה ידנית עברה",
  manual_test_failed: "בדיקה ידנית נכשלה", commit: "commit", resumed: "המשיך", handoff: "handoff",
  conflict: "התנגשות", other: "עדכון",
};
const MS_HE = { done: "הושלם", in_progress: "בעבודה", ready_to_close: "מוכן לסגירה?", next: "הבא בתור", not_started: "טרם התחיל" };
const MS_CLASS = { done: "st-DONE", in_progress: "st-ACTIVE", ready_to_close: "st-WAITING", next: "st-PLANNED", not_started: "" };

function badge(text, cls) { return h("span", { class: `badge ${cls || ""}` }, text); }
function statusBadge(s) { return badge(STATUS_HE[s] || s, `st-${s}`); }

function parseTs(v) { if (!v) return null; const d = new Date(v); return isNaN(d) ? null : d; }
function ago(v) {
  const d = parseTs(v);
  if (!d) return "לא ידוע";
  const s = Math.round((Date.now() - d.getTime()) / 1000);
  if (s < 45) return "עכשיו";
  const m = Math.round(s / 60);
  if (m < 60) return m === 1 ? "לפני דקה" : `לפני ${m} דקות`;
  const hr = Math.round(m / 60);
  if (hr < 24) return hr === 1 ? "לפני שעה" : `לפני ${hr} שעות`;
  const dd = Math.round(hr / 24);
  return dd === 1 ? "אתמול" : `לפני ${dd} ימים`;
}
function clock(v) {
  const d = parseTs(v);
  if (!d) return "";
  const today = new Date().toDateString() === d.toDateString();
  const t = d.toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit" });
  return today ? t : `${d.toLocaleDateString("he-IL", { day: "numeric", month: "numeric" })} ${t}`;
}
const when = (v) => h("span", { class: "when ts", title: v || "" }, clock(v) || "—");
const byTimeDesc = (a, b) => (parseTs(b.at) || 0) - (parseTs(a.at) || 0);
const workerName = (id) => (DATA?.workers.find((w) => w.id === id)?.name) || id || "";
// Dependencies may point at a worker or at another task.
const depName = (id) => DATA?.workers.find((w) => w.id === id)?.name
  || DATA?.state.tasks.find((t) => t.id === id)?.title_hebrew || id || "";

/* The ONLY way to reach a worker: open its conversation. The label says what to do there. */
function openSessionButton(w, whatToType, primary) {
  if (!w.deep_link) return h("span", { class: "hint" }, `אין קישור לשיחה של ${w.name} — בקש מהמנהל להוסיף.`);
  const label = whatToType ? `פתח את השיחה של ${w.name} (שם כותבים ${whatToType})` : `פתח את השיחה של ${w.name}`;
  return h("a", { class: `btn ${primary ? "primary" : "small"}`, href: w.deep_link }, label);
}
/* Prepares a message for the PM. Never executes anything. */
function prepareButton(type, workerId, label) {
  return h("button", { class: "btn small", type: "button", onclick: () => openRequest(type, workerId) }, `הכן הודעה למנהל: ${label}`);
}

// ------------------------------------------------------------------ data
async function load() {
  try {
    const r = await fetch("/api/dashboard", { cache: "no-store" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const first = DATA === null;
    DATA = await r.json();
    render();
    // Content arrives after the browser's own jump to #section, so re-apply it once.
    if (first && location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView();
  } catch (e) {
    fill("freshness", h("span", { class: "badge s-bad" }, "אין חיבור לשרת הדשבורד"), " — ייתכן שהחלון שלו נסגר. הפעל שוב את start_project_manager.bat");
  }
}

// ------------------------------------------------------------------ render
function render() {
  const d = DATA;
  fill("freshness", "המנהל עדכן ", h("strong", {}, d.state.updated_at ? ago(d.state.updated_at) : "— עוד לא"),
    h("span", { class: "hint-inline" }, " · מתרענן לבד"));
  const pmLink = $("open-pm");
  if (d.pm.deep_link) { pmLink.href = d.pm.deep_link; pmLink.hidden = false; } else pmLink.hidden = true;

  renderBanners(d);
  renderOverview(d);
  renderAttention(d);
  renderWorkers(d);
  renderRoadmap(d);
  renderRecent(d);
  renderDaily(d);
  renderTasks(d);
  renderInbox(d);
  renderTechnical(d);
  if (openWorkerId && $("worker-dialog").open) renderWorkerDetail(openWorkerId);
}

function renderBanners(d) {
  const out = [];
  if (d.state_status === "missing") {
    out.push(h("div", { class: "banner warn" }, "המנהל עוד לא עדכן מצב. מוצג רק מה שידוע מהמסמכים."));
  } else if (d.state_status === "corrupt") {
    out.push(h("div", { class: "banner warn" }, "קובץ המצב של המנהל לא נקרא כרגע (אולי בדיוק נכתב) — ינסה שוב בעוד רגע."));
  } else if (d.state.updated_at && Date.now() - parseTs(d.state.updated_at) > 3 * 3600 * 1000) {
    out.push(h("div", { class: "banner info" }, `המנהל לא עדכן את המצב ${ago(d.state.updated_at)} — ייתכן שחלק מהמידע ישן.`));
  }
  // Efficiency: one quiet banner, only when something is actionable.
  const actionable = (d.efficiency?.recommendations || []).filter((r) => r.level === "bad" || r.level === "warn");
  if (actionable.length) {
    out.push(h("div", { class: "banner quiet" }, h("strong", {}, "שים לב: "),
      actionable.length === 1 ? actionable[0].text : h("ul", {}, actionable.map((r) => h("li", {}, r.text)))));
  }
  fill("banners", out);
}

// ------------------------------------------------------------------ 1. overview
function renderOverview(d) {
  const st = d.state;
  let lines = (st.overview_hebrew || "").split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
  if (!lines.length) {
    const s = st.project_summary;
    lines = [s.completed, s.active, s.next].filter(Boolean);
  }
  if (!lines.length) lines = [fallbackOverview(d)];
  fill("overview", lines.slice(0, 4).map((l) => h("p", {}, l)));

  const f = d.roadmap_focus || {};
  const cur = f.here || f.next;
  const att = attentionItems(d).length;
  const active = d.workers.filter((w) => w.status === "ACTIVE").length;
  const waiting = d.workers.filter((w) => w.status === "WAITING" || w.status === "BLOCKED").length;
  fill("overview-meta",
    cur && h("a", { class: "chip", href: "#roadmap" }, `${f.here ? "אנחנו כאן" : "השלב הבא"}: שלב ${cur.number} — `, h("bdi", {}, cur.title)),
    h("span", { class: "chip" }, `${active} עובדים פעילים`),
    waiting ? h("span", { class: "chip" }, `${waiting} ממתינים`) : null,
    h("a", { class: `chip ${att ? "chip-you" : "chip-ok"}`, href: "#attention" }, att ? `${att} דברים מחכים לך` : "שום דבר לא מחכה לך"));
}
function fallbackOverview(d) {
  const done = d.roadmap.milestones?.filter((m) => m.status === "done").map((m) => m.number);
  return done?.length ? `הושלמו אבני דרך ${done.join(", ")}.` : "אין עדיין תמונת מצב מהמנהל.";
}

// ------------------------------------------------------------------ 2. waiting for you
function attentionItems(d) {
  const items = d.state.attention.map((a) => ({ ...a }));
  const has = (w, types) => items.some((a) => a.worker === w && types.includes(a.type));
  for (const w of d.workers) {
    if (w.manual_test.status === "required" && !has(w.id, ["manual_test"])) {
      items.push({ type: "manual_test", worker: w.id, text_hebrew: `לבדוק את העבודה של ${w.name}` });
    }
    if (w.awaiting_owner_approval && !has(w.id, ["approval", "commit"])) {
      items.push({ type: "commit", worker: w.id, text_hebrew: `${w.name} מחכה לאישור שלך לשמירה ב-Git` });
    }
  }
  return items;
}

function attentionActions(a, w) {
  if (!w) return [];
  switch (a.type) {
    case "manual_test":
      return [
        h("button", { class: "btn small", type: "button", onclick: () => openWorker(w.id) }, "הצג את צעדי הבדיקה"),
        openSessionButton(w, "'מאושר, אפשר commit' אם הכול תקין"),
        prepareButton("manual_test_failed", w.id, "הבדיקה נכשלה"),
      ];
    case "approval":
    case "commit":
      return [openSessionButton(w, "'מאושר, אפשר commit'")];
    default:
      return [openSessionButton(w, "")];
  }
}

function renderAttention(d) {
  const items = attentionItems(d);
  if (!items.length) return fill("attention-list", h("div", { class: "all-clear" }, "אין שום דבר שדורש אותך כרגע."));
  fill("attention-list",
    items.map((a) => {
      const w = d.workers.find((x) => x.id === a.worker);
      return h("div", { class: "att" },
        h("div", { class: "att-title" }, badge(ATT_HE[a.type] || a.type, "s-warn"), h("span", {}, a.text_hebrew)),
        a.how_to_act && h("div", { class: "how" }, a.how_to_act),
        h("div", { class: "row-actions" }, attentionActions(a, w)));
    }),
    h("p", { class: "hint" }, "הכפתורים כאן לא מאשרים ולא מבצעים כלום בעצמם — הם רק פותחים שיחה או מכינים הודעה."));
}

// ------------------------------------------------------------------ 3. workers
function contextView(ctx) {
  if (ctx.percent === null || ctx.percent === undefined) return h("span", { class: "when" }, "אין נתון");
  const label = `${Math.round(ctx.percent)}%${ctx.source === "estimate" ? " (הערכה)" : ""}`;
  return h("div", {},
    h("span", {}, label, " "), badge(LEVEL_HE[ctx.level] || "", `st-${ctx.level}`),
    h("div", { class: `meter ${ctx.level}` }, h("span", { style: `width:${Math.min(100, ctx.percent)}%` })));
}
function testsText(t) {
  if (!t.result) return "לא ידוע";
  return `${TESTS_HE[t.result] || t.result}${t.count !== null ? ` (${t.count})` : ""}`;
}
function waitingLine(w) {
  if (!w.depends_on.length || w.status === "DONE") return null;
  const parts = w.depends_on.map((id) => {
    const o = DATA.workers.find((x) => x.id === id);
    const what = o ? (o.remaining.slice(0, 2).join(" · ") || o.next_action) : "";
    return `${depName(id)}${what ? ` — ${what}` : ""}`;
  });
  return h("div", { class: "waiting-line" }, h("strong", {}, "ממתין ל: "), parts.join(" | "));
}

function renderWorkers(d) {
  if (!d.workers.length) return fill("worker-cards", empty("אין עובדים רשומים."));
  fill("worker-cards", d.workers.map((w) => {
    const card = h("article", {
      class: `card st-border-${w.status}`, tabindex: "0", role: "button", "aria-label": `פרטי ${w.name}`,
      onclick: (ev) => { if (!ev.target.closest("a,button")) openWorker(w.id); },
      onkeydown: (ev) => { if (ev.key === "Enter" && ev.target === card) openWorker(w.id); },
    },
      h("div", { class: "card-head" },
        h("div", {}, h("h3", {}, w.name), h("div", { class: "task" }, w.task)),
        statusBadge(w.status)),
      w.now_hebrew && h("div", { class: "now" }, w.now_hebrew),
      waitingLine(w),
      h("dl", { class: "facts" },
        h("dt", {}, "פעילות אחרונה"), h("dd", {}, ago(w.last_activity_at)),
        h("dt", {}, "נשמר ב-Git"), h("dd", {}, w.committed ? "כן" : "עדיין לא"),
        h("dt", {}, "בדיקות"), h("dd", {}, testsText(w.tests)),
        h("dt", {}, "בדיקה ידנית"), h("dd", {}, badge(MANUAL_HE[w.manual_test.status], `st-${w.manual_test.status}`)),
        h("dt", {}, "context"), h("dd", {}, contextView(w.context_resolved)),
      ),
      contextAdvice(w, true),
      h("div", { class: "row-actions" },
        h("button", { class: "btn small", type: "button", onclick: () => openWorker(w.id) }, "כל הפרטים"),
        openSessionButton(w, "")));
    return card;
  }));
}

function contextAdvice(w, compact) {
  const lvl = w.context_resolved.level;
  if (lvl !== "near" && lvl !== "handoff") return null;
  const files = (DATA.handoff_files || []).map((f) => `${f.name}: עודכן ${ago(f.modified_at)}`).join(" · ");
  return h("div", { class: `banner ${lvl === "handoff" ? "bad" : "warn"}` },
    h("strong", {}, lvl === "handoff" ? "מומלץ handoff עכשיו. " : "קרוב לגבול. "),
    "כדאי לסיים את הצעד הנוכחי בנקודה בטוחה ולעבור לעובד חדש (עדיף על compact — עובד חדש מתחיל נקי).",
    !compact && h("div", { class: "when" }, "קבצי ה-handoff: ", files || "לא ידוע"));
}

// ------------------------------------------------------------------ worker detail
function openWorker(id) {
  openWorkerId = id;
  renderWorkerDetail(id);
  const dlg = $("worker-dialog");
  if (!dlg.open) dlg.showModal();
}
function box(title, ...kids) { return h("div", { class: "box" }, h("h3", {}, title), ...kids); }
function ul(items, emptyText) { return items?.length ? h("ul", {}, items.map((x) => h("li", {}, x))) : empty(emptyText || "—"); }

function renderWorkerDetail(id) {
  const w = DATA.workers.find((x) => x.id === id);
  if (!w) return;
  fill("wd-title", `${w.name} `, statusBadge(w.status));
  const tr = w.transcript;
  const feed = [
    ...DATA.state.timeline.filter((t) => t.worker === w.id).map((t) => ({ at: t.at, text: `${EVENT_HE[t.event] || t.event}: ${t.text_hebrew}` })),
    ...(tr?.activity || []).map((a) => ({ at: a.at, text: a.text, est: true })),
  ].sort(byTimeDesc).slice(0, 15);

  fill("wd-body",
    h("div", { class: "box now-box" }, h("h3", {}, "מה העובד עושה עכשיו?"),
      h("p", {}, w.now_hebrew || "המנהל לא כתב."),
      waitingLine(w),
      w.next_action && h("p", {}, h("strong", {}, "הצעד הבא: "), w.next_action)),
    contextAdvice(w, false),
    w.manual_test.status === "required" && h("div", { class: "box test-box" }, h("h3", {}, "הבדיקה הידנית שלך"),
      w.manual_test.steps.length ? h("ol", {}, w.manual_test.steps.map((s) => h("li", {}, s))) : empty("העובד עוד לא כתב צעדים."),
      w.manual_test.note && h("p", {}, w.manual_test.note),
      h("p", { class: "hint" }, "אם הכול תקין — פתח את השיחה של העובד וכתוב שם 'מאושר, אפשר commit'. הכפתור רק פותח את השיחה."),
      h("div", { class: "row-actions" }, openSessionButton(w, "'מאושר, אפשר commit'", true), prepareButton("manual_test_failed", w.id, "הבדיקה נכשלה"))),
    h("div", { class: "detail-grid" },
      box("מה בוצע", ul(w.done)),
      box("מה נשאר", ul(w.remaining)),
      box("מצב",
        h("dl", { class: "facts" },
          h("dt", {}, "בדיקות"), h("dd", {}, testsText(w.tests)),
          h("dt", {}, "בדיקה ידנית"), h("dd", {}, MANUAL_HE[w.manual_test.status]),
          h("dt", {}, "נשמר ב-Git"), h("dd", {}, w.committed ? `כן ${w.commit || ""}` : "עדיין לא"),
          h("dt", {}, "מחכה לאישור שלך"), h("dd", {}, w.awaiting_owner_approval ? "כן (בשיחה שלו)" : "לא"),
          h("dt", {}, "context"), h("dd", {}, contextView(w.context_resolved)))),
      box("עדכון אחרון", h("p", {}, w.last_update.text || "—"), h("div", { class: "when" }, ago(w.last_update.at))),
    ),
    h("h3", {}, "פעולות"),
    h("div", { class: "row-actions" },
      openSessionButton(w, "", true),
      prepareButton("status_request", w.id, "עדכון מצב"),
      prepareButton("pause_worker", w.id, "לעצור אותו"),
      prepareButton("continue_worker", w.id, "להמשיך אותו"),
      prepareButton("message_worker", w.id, "הודעה אליו")),
    h("p", { class: "hint" }, "\"הכן הודעה למנהל\" לא שולח כלום — הוא מכין טקסט שאתה מדביק בשיחה של המנהל."),
    h("details", { class: "quiet-details" }, h("summary", {}, "פרטים טכניים של העובד"),
      h("div", { class: "detail-grid" },
        box("קבצים שבאחריותו", ul(w.owns.map((o) => h("code", {}, o)), "לא הוגדר")),
        box("שינויים שלו שעוד לא נשמרו",
          w.git_files.length ? h("ul", { class: "files" }, w.git_files.map((f) => h("li", {}, h("code", {}, f.path), " ", fileNote(f)))) : empty("אין")),
        box("פרטים", h("dl", { class: "facts" },
          h("dt", {}, "שלב"), h("dd", {}, w.current_step || "—"),
          h("dt", {}, "התחיל מ-commit"), h("dd", {}, w.start_commit ? h("code", {}, w.start_commit) : "—"),
          h("dt", {}, "חוסם את"), h("dd", {}, w.blocks.map(depName).join(", ") || "אף אחד"))),
        tr?.last_text && box("הודעה אחרונה שלו", h("p", { class: "when" }, clock(tr.last_text.at)), h("p", {}, h("bdi", {}, tr.last_text.text)))),
      h("h3", {}, "פעילות אחרונה"),
      feed.length ? h("ul", { class: "list" }, feed.map((f) => h("li", {}, when(f.at), h("span", {}, f.text), f.est ? h("span", { class: "when" }, "(מקובץ השיחה)") : null)))
        : empty("אין פעילות ידועה.")),
  );
}

function fileNote(f) {
  const bits = [{ new: "חדש", modified: "שונה", deleted: "נמחק", added: "נוסף", renamed: "שונה שם" }[f.kind] || f.kind];
  if (f.added !== null && f.added !== undefined) bits.push(`+${f.added} −${f.removed}`);
  if (f.owners?.length > 1) bits.push(`משותף: ${f.owners.map((o) => (o === "PM" ? "מנהל" : o)).join(", ")}`);
  return h("span", { class: "when" }, `(${bits.join(" · ")})`);
}

// ------------------------------------------------------------------ 7. roadmap
/* "Here" / "next" are chosen server-side (dashboard.roadmap_focus) and carry only the
 * PM's Hebrew notes — raw English ROADMAP items are never shown in these cards. */
function renderRoadmap(d) {
  const r = d.roadmap;
  if (!r.ok) return fill("roadmap-body", empty("ROADMAP.md לא נמצא."));
  const ms = r.milestones.filter((m) => m.number !== null);
  const here = d.roadmap_focus?.here;
  const next = d.roadmap_focus?.next;
  const special = new Set([here?.number, next?.number]);
  const done = ms.filter((m) => m.status === "done" && !special.has(m.number));
  const later = ms.filter((m) => m.status !== "done" && !special.has(m.number));

  const row = (m) => {
    const pct = m.total ? Math.round((100 * m.done_count) / m.total) : 0;
    return h("div", { class: "ms" },
      h("div", {}, h("span", { class: "title" }, `${m.number}. `, h("bdi", {}, m.title)), " ", MS_HE[m.status] ? badge(MS_HE[m.status], MS_CLASS[m.status]) : null),
      h("div", { class: "progress", title: `${m.done_count}/${m.total}` }, h("span", { style: `width:${pct}%` })),
      h("span", { class: "when ts" }, `${m.done_count}/${m.total}`));
  };
  const hereCard = here && h("div", { class: "ms-focus" },
    h("div", { class: "ms-focus-head" },
      h("div", { class: "ms-focus-title" }, `${here.number}. `, h("bdi", {}, here.title)),
      badge("אנחנו כאן", "st-here")),
    here.status === "done" && h("p", { class: "when" }, "השלב סומן כגמור, אבל יש בו עוד עבודה פתוחה."),
    here.notes.length ? [h("h4", {}, "מה עוד חסר כדי לסיים את השלב"), h("ul", {}, here.notes.map((n) => h("li", {}, n)))] : null);
  const nextRow = next && h("div", { class: "ms-next" },
    h("div", {}, badge("השלב הבא", "st-next"), " ", h("span", { class: "title" }, `${next.number}. `, h("bdi", {}, next.title))),
    next.notes.length ? h("ul", { class: "ms-notes" }, next.notes.map((n) => h("li", {}, n))) : null);

  fill("roadmap-body",
    hereCard,
    nextRow,
    done.length ? h("details", { class: "quiet-details" }, h("summary", {}, `שלבים שהושלמו (${done.length})`), h("div", { class: "ms-list" }, done.map(row))) : null,
    later.length ? h("details", { class: "quiet-details" }, h("summary", {}, `שלבים עתידיים (${later.length})`), h("div", { class: "ms-list" }, later.map(row))) : null);
}

// ------------------------------------------------------------------ 8. recent / completed
function renderRecent(d) {
  const st = d.state;
  const changes = [...st.changes].sort(byTimeDesc).slice(0, RECENT_CHANGES);
  fill("changes-body", changes.length
    ? h("ul", { class: "list big-list" }, changes.map((c) => h("li", {}, h("span", {}, c.text_hebrew), h("span", { class: "when ts" }, ago(c.at)))))
    : empty("המנהל עוד לא רשם שינויים."));

  const groups = new Map();
  for (const c of [...st.completed].sort(byTimeDesc)) {
    const key = c.milestone || "אחר";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(c);
  }
  const entries = [...groups.entries()];
  const group = ([ms, items], open) => h("details", { class: "done-group", open: open || null },
    h("summary", {}, ms, " ", h("span", { class: "when" }, `(${items.length})`)),
    h("ul", { class: "list" }, items.map((c) => h("li", {}, h("span", {}, c.text_hebrew)))));
  if (entries.length) {
    fill("completed-body", entries.map((e, i) => group(e, i === 0)));
  } else {
    const commits = d.git.commits || [];
    fill("completed-body", commits.length
      ? h("ul", { class: "list" }, commits.slice(0, 5).map((c) => h("li", {}, h("span", { dir: "auto" }, c.subject))))
      : empty("אין עדיין."));
  }
}

// ------------------------------------------------------------------ 9. daily
function renderMarkdown(text) {
  const root = h("div", { class: "md" });
  let list = null;
  const inline = (s) => s.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean).map((part) =>
    part.startsWith("**") ? h("strong", {}, part.slice(2, -2)) : part.startsWith("`") ? h("code", {}, part.slice(1, -1)) : part);
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trimEnd();
    const head = line.match(/^(#{1,4})\s+(.*)$/);
    const item = line.match(/^\s*(?:[-*]|\d+[.)])\s+(.*)$/);
    if (item) { if (!list) root.append(list = h("ul")); list.append(h("li", {}, inline(item[1]))); continue; }
    list = null;
    if (head) root.append(h(`h${Math.min(4, head[1].length + 2)}`, {}, inline(head[2])));
    else if (line.trim()) root.append(h("p", {}, inline(line)));
  }
  return root;
}
/* The "בקצרה" section if present, else the first few content lines. */
function dailyBrief(text) {
  const lines = text.split(/\r?\n/);
  const start = lines.findIndex((l) => /^#{1,6}\s+.*בקצרה/.test(l));
  if (start >= 0) {
    const rest = lines.slice(start + 1);
    const end = rest.findIndex((l) => /^#{1,6}\s/.test(l));
    return (end >= 0 ? rest.slice(0, end) : rest).join("\n").trim();
  }
  return lines.filter((l) => l.trim() && !/^#\s/.test(l)).slice(0, DAILY_PREVIEW_LINES).join("\n");
}
function renderDaily(d) {
  const dd = d.daily;
  const e = dd.today_entry;
  fill("daily-body",
    e ? [h("div", { class: "brief" }, renderMarkdown(dailyBrief(e.text))),
      h("details", { class: "quiet-details" }, h("summary", {}, "קרא עוד"), renderMarkdown(e.text))]
      : [empty("עוד אין סיכום להיום."), h("p", { class: "hint" }, "אין סיכום יום אוטומטי."),
        h("button", { class: "btn small", type: "button", onclick: () => openRequest("daily_summary", "") }, "הכן הודעה למנהל: \"צור סיכום יום\"")],
    dd.history?.length ? h("details", { class: "quiet-details" }, h("summary", {}, `ימים קודמים (${dd.history.length})`),
      dd.history.map((x) => h("details", { class: "day" }, h("summary", {}, x.date), renderMarkdown(x.text)))) : null);
}

// ------------------------------------------------------------------ 10. tasks + requests
function renderTasks(d) {
  const tasks = d.state.tasks;
  const pendingIdeas = d.inbox.filter((r) => r.type === "new_task" && r.status === "pending");
  const ideaRows = pendingIdeas.map((r) => h("tr", {},
    h("td", {}, r.text), h("td", {}, statusBadge("PENDING_PM")), h("td", {}, "—"), h("td", {}, "—")));
  if (!tasks.length && !ideaRows.length) return fill("tasks-body", empty("אין משימות פתוחות ברשימה של המנהל."));
  fill("tasks-body", h("div", { class: "table-wrap" }, h("table", {},
    h("thead", {}, h("tr", {}, ["משימה", "מצב", "מי מטפל", "תלויה ב"].map((t) => h("th", {}, t)))),
    h("tbody", {}, ideaRows, tasks.map((t) => h("tr", {},
      h("td", {}, t.title_hebrew),
      h("td", {}, statusBadge(t.status)),
      h("td", {}, t.owner ? workerName(t.owner) : "—"),
      h("td", {}, t.depends_on.map(depName).join(" · ") || "—")))))));
}

function renderInbox(d) {
  const pending = d.inbox.filter((r) => r.status === "pending").length;
  fill("inbox-count", d.inbox.length ? badge(pending ? `${pending} ממתינות למנהל` : "הכול טופל", pending ? "s-warn" : "s-ok") : null);
  fill("inbox-body", d.inbox.length ? h("ul", { class: "list" }, d.inbox.slice(0, 20).map((r) => h("li", {},
    when(r.at), badge(r.status === "handled" ? "טופל" : "ממתינה", r.status === "handled" ? "s-ok" : "s-warn"),
    h("span", { class: "grow" }, r.copy_text),
    h("button", { class: "btn small", type: "button", onclick: (ev) => copy(r.copy_text, ev.currentTarget) }, "העתק"))))
    : empty("עוד לא הכנת בקשות."));
}

const REQUEST_HINT = {
  new_task: "כתוב רעיון, בקשה או באג במילים שלך — המנהל יחליט מתי ומי יטפל בזה.",
  message_worker: "ההודעה עוברת דרך המנהל, שיעביר אותה לעובד.",
  manual_test_failed: "כתוב בקצרה מה לא עבד — המנהל יעביר לעובד.",
  new_worker: "תאר במילים שלך מה העובד החדש צריך לעשות.",
};
function openRequest(type, workerId) {
  const meta = DATA.request_types[type];
  if (!meta) return;
  $("request-form").dataset.type = type;
  fill("rd-title", meta.label);
  const hint = $("rd-hint");
  hint.textContent = REQUEST_HINT[type] || "";
  hint.hidden = !REQUEST_HINT[type];
  const sel = $("rd-worker");
  sel.replaceChildren(h("option", { value: "" }, meta.needs_worker ? "בחר עובד…" : "(לא קשור לעובד מסוים)"),
    ...DATA.workers.map((w) => h("option", { value: w.id }, w.name)));
  sel.value = workerId || "";
  $("rd-worker-field").hidden = !meta.needs_worker;
  $("rd-text-label").textContent = ["message_worker", "new_task", "new_worker"].includes(type) ? "מה לכתוב" : "הערה (לא חובה)";
  $("rd-text").value = "";
  $("rd-error").hidden = true;
  $("rd-result").hidden = true;
  $("rd-submit").hidden = false;
  const pm = $("rd-open-pm");
  if (DATA.pm.deep_link) { pm.href = DATA.pm.deep_link; pm.hidden = false; } else pm.hidden = true;
  if ($("worker-dialog").open) $("worker-dialog").close();
  $("request-dialog").showModal();
}

async function submitRequest(ev) {
  ev.preventDefault();
  const form = $("request-form");
  const body = { type: form.dataset.type, worker: $("rd-worker-field").hidden ? "" : $("rd-worker").value, text: $("rd-text").value };
  try {
    const r = await fetch("/api/request", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
    $("rd-copy").value = data.copy_text;
    $("rd-result").hidden = false;
    $("rd-submit").hidden = true;
    $("rd-error").hidden = true;
    load();
  } catch (e) {
    fill("rd-error", "לא נשמר: ", e.message).hidden = false;
  }
}

async function copy(text, btn) {
  let ok = false;
  try { await navigator.clipboard.writeText(text); ok = true; } catch {
    const ta = h("textarea", { style: "position:fixed;opacity:0" }, text);
    document.body.append(ta); ta.select();
    try { ok = document.execCommand("copy"); } catch { ok = false; }
    ta.remove();
  }
  if (btn) { const old = btn.textContent; btn.textContent = ok ? "הועתק ✓" : "העתק ידנית"; setTimeout(() => { btn.textContent = old; }, 1800); }
}

// ------------------------------------------------------------------ technical details (collapsed)
function renderTechnical(d) {
  const g = d.git;
  const own = d.ownership;
  const label = (id) => (id === "PM" ? "מנהל (מסמכים)" : workerName(id));
  const gitNodes = !g.ok ? [h("div", { class: "banner warn" }, "לא ניתן לקרוא את Git: ", g.error || "")] : [
    h("dl", { class: "facts" },
      h("dt", {}, "ענף"), h("dd", {}, h("code", {}, g.branch || "?")),
      h("dt", {}, "commit אחרון"), h("dd", {}, g.commits[0] ? [h("code", {}, g.commits[0].hash), " ", h("bdi", {}, g.commits[0].subject), " · ", ago(g.commits[0].at)] : "—"),
      h("dt", {}, "מצב"), h("dd", {}, g.clean ? badge("נקי — הכול נשמר", "s-ok") : badge(`${g.dirty.length} קבצים שלא נשמרו`, "s-warn"))),
    own.warnings.map((w) => h("div", { class: `banner ${w.level === "warn" ? "warn" : "info"}` }, w.text_hebrew,
      w.workers ? ` (${w.workers.map(workerName).join(", ")})` : "",
      w.files?.length ? h("div", { class: "when" }, w.files.slice(0, 8).join(", "), w.files.length > 8 ? " …" : "") : null)),
    Object.entries(own.groups).map(([id, files]) => h("details", { class: "group" },
      h("summary", {}, label(id), " ", h("span", { class: "when" }, `(${files.length} קבצים)`)),
      h("ul", { class: "files" }, files.map((f) => h("li", {}, h("code", {}, f.path), " ", fileNote(f)))))),
    own.unowned.length ? h("details", { class: "group" }, h("summary", {}, "ללא בעלים ", badge("שים לב", "s-warn")),
      h("ul", { class: "files" }, own.unowned.map((f) => h("li", {}, h("code", {}, f.path), " ", fileNote(f))))) : null,
  ];
  const e = d.efficiency;
  const u = e.plan_usage;
  const tl = [...d.state.timeline].sort(byTimeDesc).slice(0, 30);
  const follow = d.roadmap.milestones?.flatMap((m) => m.open_follow_ups.map((i) => ({ m, i }))) || [];
  const a = d.active_work;
  fill("technical-body",
    h("h3", {}, "Git"), gitNodes,
    h("h3", {}, "עומס ושימוש"),
    h("p", {}, `פעילים ${e.active} · ממתינים ${e.waiting} · חסומים ${e.blocked}`,
      u && u.five_hour_percent !== null ? ` · מכסה 5 שעות ${Math.round(u.five_hour_percent)}%` : "",
      u && u.weekly_percent !== null ? ` · שבועי ${Math.round(u.weekly_percent)}%` : ""),
    e.activity.length ? h("p", { class: "when" }, "תגובות בשעה האחרונה (הערכה מקובצי השיחה): ", e.activity.map((x) => `${x.name} ${x.turns_last_hour}`).join(" · ")) : null,
    e.recommendations.length ? h("ul", {}, e.recommendations.map((r) => h("li", {}, r.text))) : null,
    h("h3", {}, "ציר זמן"),
    tl.length ? h("ul", { class: "list" }, tl.map((t) => h("li", {}, when(t.at), badge(workerName(t.worker) || "—"), badge(EVENT_HE[t.event] || t.event), t.text_hebrew))) : empty("אין אירועים."),
    follow.length ? [h("h3", {}, "המשכים פתוחים במפת הדרכים"), h("ul", { class: "list" }, follow.map(({ m, i }) => h("li", {}, badge(`M${m.number}`), h("bdi", {}, i.text))))] : null,
    h("h3", {}, "לוח התיאום (ACTIVE_WORK.md)"),
    a.ok ? h("pre", { class: "raw", dir: "auto" }, a.raw) : empty("לא נמצא."),
    h("h3", {}, "החלטות ארכיטקטורה"),
    d.adrs.length ? h("ul", { class: "list" }, d.adrs.map((x) => h("li", {}, h("code", {}, x.id), h("bdi", {}, x.title)))) : empty("—"));
}

// ------------------------------------------------------------------ wiring
document.addEventListener("click", (ev) => {
  const close = ev.target.closest("[data-close]");
  if (close) close.closest("dialog").close();
  const req = ev.target.closest("[data-request]");
  if (req) openRequest(req.dataset.request, "");
});
for (const dlg of document.querySelectorAll("dialog")) {
  dlg.addEventListener("click", (ev) => { if (ev.target === dlg) dlg.close(); });   // click on backdrop
}
$("worker-dialog").addEventListener("close", () => { openWorkerId = null; });
$("request-form").addEventListener("submit", submitRequest);
$("rd-copy-btn").addEventListener("click", (ev) => copy($("rd-copy").value, ev.currentTarget));

load();
setInterval(() => { if (!document.hidden) load(); }, POLL_MS);
document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });
