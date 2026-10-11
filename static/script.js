/* script.js - frontend for the Time-Table Scheduler using CSP
   Talks to the Flask API with fetch(). No libraries needed. */

const $ = (id) => document.getElementById(id);

let CONFIG = { days: [], slots: [] };
let SUBJECT_TEACHER = {};   // subject name -> teacher name (shown inside timetable cells)
let SUBJECT_LAB = {};       // subject name -> true if it is a lab subject

// ------------------------------------------------------------------
// helpers
// ------------------------------------------------------------------
async function api(url, method = "GET", body = null) {
  const options = { method, headers: { "Content-Type": "application/json" } };
  if (body) options.body = JSON.stringify(body);
  const res = await fetch(url, options);
  let data = {};
  try { data = await res.json(); } catch (e) { /* empty body */ }
  if (!res.ok) {
    const err = new Error(data.error || "Request failed");
    err.data = data;
    throw err;
  }
  return data;
}

let messageTimer = null;
function showMessage(text, type = "ok") {
  const box = $("message");
  box.textContent = text;
  box.className = "message " + type;
  clearTimeout(messageTimer);
  messageTimer = setTimeout(() => box.classList.add("hidden"), 6000);
}

// create an element safely (textContent, so user input can never inject HTML)
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function run(action) {          // run an async action and show any error
  try { await action(); }
  catch (e) { showMessage(e.message, "error"); }
}

// ------------------------------------------------------------------
// tabs
// ------------------------------------------------------------------
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    btn.classList.add("active");
    $("tab-" + btn.dataset.tab).classList.add("active");
    if (btn.dataset.tab === "saved") loadSaved();
  });
});

// ------------------------------------------------------------------
// generic list renderer
// ------------------------------------------------------------------
function renderList(listId, items, labelFn, deleteUrlFn, afterDelete) {
  const ul = $(listId);
  ul.innerHTML = "";
  if (items.length === 0) {
    ul.appendChild(el("li", "empty", "Nothing added yet"));
    return;
  }
  items.forEach((item) => {
    const li = el("li");
    const label = el("span");
    labelFn(item, label);
    const del = el("button", "btn small danger", "Delete");
    del.addEventListener("click", () => run(async () => {
      await api(deleteUrlFn(item), "DELETE");
      await afterDelete();
    }));
    li.appendChild(label);
    li.appendChild(del);
    ul.appendChild(li);
  });
}

function badge(parent, text) {
  parent.appendChild(el("span", "badge", text));
}

function fillSelect(select, items, valueFn, textFn) {
  const previous = select.value;
  select.innerHTML = "";
  items.forEach((item) => {
    const opt = el("option", "", textFn(item));
    opt.value = valueFn(item);
    select.appendChild(opt);
  });
  if ([...select.options].some((o) => o.value === previous)) select.value = previous;
}

// ------------------------------------------------------------------
// SETUP TAB: load + render each list
// ------------------------------------------------------------------
async function loadTeachers() {
  const teachers = await api("/api/teachers");
  renderList("teacherList", teachers, (t, s) => (s.textContent = t.name),
             (t) => "/api/teachers/" + t.id, refreshAll);
  fillSelect($("subTeacher"), teachers, (t) => t.id, (t) => t.name);
  fillSelect($("avTeacher"), teachers, (t) => t.id, (t) => t.name);
}

async function loadRooms() {
  const rooms = await api("/api/rooms");
  renderList("roomList", rooms, (r, s) => {
    s.textContent = r.name;
    if (r.is_lab) badge(s, "LAB");
  }, (r) => "/api/rooms/" + r.id, loadRooms);
}

async function loadDivisions() {
  const divisions = await api("/api/divisions");
  renderList("divList", divisions, (d, s) => (s.textContent = d.name),
             (d) => "/api/divisions/" + d.id, loadDivisions);
}

async function loadSubjects() {
  const subjects = await api("/api/subjects");
  SUBJECT_TEACHER = {};
  SUBJECT_LAB = {};
  subjects.forEach((s) => {
    SUBJECT_TEACHER[s.name] = s.teacher;
    SUBJECT_LAB[s.name] = !!s.is_lab;
  });
  renderList("subList", subjects, (s, span) => {
    span.textContent = `${s.name}  -  ${s.teacher}  -  ${s.lectures_per_week}/week`;
    if (s.is_lab) badge(span, "LAB");
  }, (s) => "/api/subjects/" + s.id, loadSubjects);
}

async function loadAvailability() {
  const rows = await api("/api/availability");
  renderList("avList", rows, (a, s) => (s.textContent = `${a.teacher}  -  ${a.day}  ${a.slot}`),
             (a) => "/api/availability/" + a.id, loadAvailability);
}

async function refreshAll() {
  await loadTeachers();
  await Promise.all([loadRooms(), loadDivisions(), loadSubjects(), loadAvailability()]);
}

// ------------------------------------------------------------------
// SETUP TAB: add buttons
// ------------------------------------------------------------------
$("btnAddTeacher").addEventListener("click", () => run(async () => {
  await api("/api/teachers", "POST", { name: $("teacherName").value });
  $("teacherName").value = "";
  await loadTeachers();
}));

$("btnAddRoom").addEventListener("click", () => run(async () => {
  await api("/api/rooms", "POST", { name: $("roomName").value, is_lab: $("roomLab").checked });
  $("roomName").value = "";
  $("roomLab").checked = false;
  await loadRooms();
}));

$("btnAddDiv").addEventListener("click", () => run(async () => {
  await api("/api/divisions", "POST", { name: $("divName").value });
  $("divName").value = "";
  await loadDivisions();
}));

$("btnAddSub").addEventListener("click", () => run(async () => {
  await api("/api/subjects", "POST", {
    name: $("subName").value,
    teacher_id: $("subTeacher").value,
    lectures_per_week: $("subLectures").value,
    is_lab: $("subLab").checked,
  });
  $("subName").value = "";
  $("subLab").checked = false;
  await loadSubjects();
}));

$("btnAddAv").addEventListener("click", () => run(async () => {
  await api("/api/availability", "POST", {
    teacher_id: $("avTeacher").value,
    day: $("avDay").value,
    slot: $("avSlot").value,
  });
  await loadAvailability();
}));

$("btnSeed").addEventListener("click", () => run(async () => {
  const r = await api("/api/seed", "POST");
  showMessage(r.message);
  await refreshAll();
}));

// Enter key adds in the simple one-field forms
[["teacherName", "btnAddTeacher"], ["roomName", "btnAddRoom"],
 ["divName", "btnAddDiv"], ["subName", "btnAddSub"]].forEach(([input, button]) => {
  $(input).addEventListener("keydown", (e) => { if (e.key === "Enter") $(button).click(); });
});

// ------------------------------------------------------------------
// TIMETABLE GRID
// ------------------------------------------------------------------
function colorClass(subject, subjectList) {
  return "c" + (subjectList.indexOf(subject) % 8);
}

function buildGrid(entries, division, days, slots, subjectList) {
  const wrap = el("div", "grid-wrap");
  const table = el("table", "grid");

  const head = el("tr");
  head.appendChild(el("th", "", ""));
  slots.forEach((s) => head.appendChild(el("th", "", s)));
  const thead = el("thead");
  thead.appendChild(head);
  table.appendChild(thead);

  const tbody = el("tbody");
  days.forEach((day) => {
    const tr = el("tr");
    tr.appendChild(el("th", "", day));
    slots.forEach((slot) => {
      const td = el("td");
      const hit = entries.find((e) => e.division === division && e.day === day && e.slot === slot);
      if (hit) {
        const cell = el("div", "cell " + colorClass(hit.subject, subjectList), hit.subject);
        const lab = SUBJECT_LAB[hit.subject] ? " (Lab)" : "";
        cell.appendChild(el("small", "", (SUBJECT_TEACHER[hit.subject] || "") + " | " + hit.room + lab));
        td.appendChild(cell);
      }
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  wrap.appendChild(table);
  return wrap;
}

// Shows one card with division tabs + grid inside `container`
function renderTimetable(container, title, entries, days, slots) {
  container.innerHTML = "";
  const divisions = [...new Set(entries.map((e) => e.division))].sort();
  const subjectList = [...new Set(entries.map((e) => e.subject))].sort();

  const card = el("div", "card print-me");
  const top = el("div", "grid-title");
  top.appendChild(el("h2", "", title));
  const printBtn = el("button", "btn secondary no-print", "Print / Save as PDF");
  printBtn.addEventListener("click", () => window.print());
  top.appendChild(printBtn);
  card.appendChild(top);

  const tabs = el("div", "division-tabs");
  const gridHolder = el("div");
  card.appendChild(tabs);
  card.appendChild(gridHolder);

  function show(division) {
    tabs.querySelectorAll("button").forEach((b) =>
      b.classList.toggle("active", b.textContent === division));
    gridHolder.innerHTML = "";
    gridHolder.appendChild(buildGrid(entries, division, days, slots, subjectList));
  }

  divisions.forEach((d) => {
    const b = el("button", "", d);
    b.addEventListener("click", () => show(d));
    tabs.appendChild(b);
  });
  container.appendChild(card);
  if (divisions.length) show(divisions[0]);
}

// ------------------------------------------------------------------
// GENERATE TAB
// ------------------------------------------------------------------
function showStats(stats) {
  const box = $("stats");
  box.innerHTML = "";
  const items = [
    ["Status", stats.status],
    ["Lectures placed", stats.variables],
    ["Nodes explored", stats.nodes],
    ["Backtracks", stats.backtracks],
    ["Time (sec)", stats.time_sec],
    ["Violations", stats.violations === undefined ? "-" : stats.violations],
  ];
  if (stats.penalty !== undefined) {
    items.push(["Idle gaps", stats.gaps], ["Soft penalty", stats.penalty], ["Tries", stats.attempts]);
  }
  items.forEach(([label, value]) => {
    const div = el("div", "stat" + (label === "Violations" && value === 0 ? " good" : ""));
    div.appendChild(el("b", "", String(value)));
    div.appendChild(document.createTextNode(label));
    box.appendChild(div);
  });
  box.classList.remove("hidden");
}

$("btnGenerate").addEventListener("click", async () => {
  const btn = $("btnGenerate");
  btn.disabled = true;
  btn.textContent = "Solving...";
  $("resultArea").innerHTML = "";
  try {
    const r = await api("/api/generate", "POST", {
      name: $("ttName").value || "Timetable",
      algorithm: $("algoSelect").value,
      shuffle: $("shuffle").checked,
      attempts: $("attempts").value,
    });
    showStats(r.stats);
    await loadSubjects();     // makes sure teacher names are available for the grid
    renderTimetable($("resultArea"), $("ttName").value || "Timetable",
                    r.entries, CONFIG.days, CONFIG.slots);
    showMessage("Timetable generated and saved (ID " + r.timetable_id + ")");
  } catch (e) {
    if (e.data && e.data.stats) showStats(e.data.stats);
    showMessage(e.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Generate";
  }
});

// ------------------------------------------------------------------
// SAVED TAB
// ------------------------------------------------------------------
async function loadSaved() {
  const list = await api("/api/timetables");
  const ul = $("savedList");
  ul.innerHTML = "";
  if (list.length === 0) {
    ul.appendChild(el("li", "empty", "No saved timetables yet"));
    return;
  }
  list.forEach((t) => {
    const li = el("li");
    li.appendChild(el("span", "", `#${t.id}  -  ${t.name}  (${t.created_at})`));
    const actions = el("span");
    const view = el("button", "btn small", "View");
    view.addEventListener("click", () => run(async () => {
      await loadSubjects();
      const d = await api("/api/timetables/" + t.id);
      renderTimetable($("savedArea"), t.name, d.entries, d.days, d.slots);
    }));
    const del = el("button", "btn small danger", "Delete");
    del.style.marginLeft = "6px";
    del.addEventListener("click", () => run(async () => {
      await api("/api/timetables/" + t.id, "DELETE");
      $("savedArea").innerHTML = "";
      await loadSaved();
    }));
    actions.appendChild(view);
    actions.appendChild(del);
    li.appendChild(actions);
    ul.appendChild(li);
  });
}

// ------------------------------------------------------------------
// START
// ------------------------------------------------------------------
async function init() {
  CONFIG = await api("/api/config");
  fillSelect($("avDay"), CONFIG.days, (d) => d, (d) => d);
  const slotOptions = ["all", ...CONFIG.slots];
  fillSelect($("avSlot"), slotOptions, (s) => s, (s) => (s === "all" ? "Whole day" : s));
  await refreshAll();
}

run(init);
