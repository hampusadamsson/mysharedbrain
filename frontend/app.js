/* MySharedBrain UI. Decoupled: only HTTP JSON against /api/*. No build step. */
"use strict";

const $ = (id) => document.getElementById(id);
const api = {
  async get(path) { const r = await fetch(path); if (!r.ok) throw new Error(await r.text()); return r.json(); },
  async send(path, method, body) {
    const r = await fetch(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!r.ok && r.status !== 204) throw new Error(await r.text());
    return r.status === 204 ? null : r.json();
  },
};

let currentId = null;

async function refreshNotes(query = "") {
  const params = query ? `?q=${encodeURIComponent(query)}` : "";
  const { notes } = await api.get(`/api/notes${params}`);
  const list = $("notes-list");
  list.innerHTML = "";
  for (const id of notes) {
    const li = document.createElement("li");
    li.textContent = id;
    if (id === currentId) li.classList.add("active");
    li.onclick = () => openNote(id);
    list.appendChild(li);
  }
}

async function openNote(id) {
  const note = await api.get(`/api/notes/${encodeURIComponent(id)}`);
  currentId = note.id;
  $("editor-title").textContent = note.id;
  $("editor").value = note.content;
  for (const b of ["save-btn", "move-btn", "delete-btn"]) $(b).disabled = false;
  $("editor").disabled = false;
  refreshNotes($("search-input").value);
}

async function search(q) {
  if (!q.trim()) return refreshNotes();
  const res = await api.get(`/api/search?q=${encodeURIComponent(q)}&limit=20`);
  const ids = [...new Set([...res.names, ...res.content.map((h) => h.id)])];
  const list = $("notes-list");
  list.innerHTML = "";
  for (const id of ids) {
    const hit = res.content.find((h) => h.id === id);
    const li = document.createElement("li");
    li.innerHTML = "";
    const title = document.createElement("span");
    title.textContent = id;
    li.appendChild(title);
    if (hit) for (const ex of hit.excerpts.slice(0, 2)) {
      const s = document.createElement("span");
      s.className = "excerpt";
      s.textContent = ex;
      li.appendChild(s);
    }
    li.onclick = () => openNote(id);
    list.appendChild(li);
  }
}

async function refreshCapture(status) {
  const params = status ? `?status=${status}` : "";
  const { entries } = await api.get(`/api/capture${params}`);
  const list = $("capture-list");
  list.innerHTML = "";
  for (const e of entries) {
    const li = document.createElement("li");
    const head = document.createElement("div");
    head.innerHTML = "";
    const kind = document.createElement("strong");
    kind.textContent = `${e.kind} · ${e.note_id || "—"}`;
    head.appendChild(kind);
    const badge = document.createElement("span");
    badge.className = "badge";
    badge.textContent = e.status;
    head.appendChild(badge);
    li.appendChild(head);
    const body = document.createElement("div");
    body.textContent = e.body;
    li.appendChild(body);
    if (e.status === "pending") {
      const row = document.createElement("div");
      row.className = "row";
      const ok = document.createElement("button");
      ok.textContent = "Apply";
      ok.onclick = async () => {
        let content = null;
        if (e.note_id) {
          try {
            const note = await api.get(`/api/notes/${encodeURIComponent(e.note_id)}`);
            content = `${note.content}\n\n${e.body}\n`;
          } catch { content = `${e.body}\n`; }
        }
        await api.send(`/api/capture/${e.id}/review`, "POST", { verdict: "applied", reviewer: "ui", content });
        refreshCapture(status);
        refreshNotes();
      };
      const no = document.createElement("button");
      no.textContent = "Reject";
      no.onclick = async () => {
        await api.send(`/api/capture/${e.id}/review`, "POST", { verdict: "rejected", reviewer: "ui" });
        refreshCapture(status);
      };
      row.appendChild(ok);
      row.appendChild(no);
      li.appendChild(row);
    }
    list.appendChild(li);
  }
}

async function refreshAudit() {
  const { entries } = await api.get("/api/audit?limit=50");
  const list = $("audit-list");
  list.innerHTML = "";
  for (const e of entries) {
    const li = document.createElement("li");
    li.textContent = `${e.ts} · ${e.actor} · ${e.action} · ${e.note_id} ${e.detail}`;
    list.appendChild(li);
  }
}

$("ask-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const q = $("ask-input").value;
  const box = $("ask-result");
  box.textContent = "Asking…";
  try {
    const ans = await api.send("/api/request", "POST", { question: q });
    box.innerHTML = "";
    const p = document.createElement("p");
    p.textContent = ans.message;
    box.appendChild(p);
    for (const id of ans.note_ids) {
      const b = document.createElement("button");
      b.textContent = id;
      b.onclick = () => openNote(id);
      box.appendChild(b);
    }
  } catch (err) { box.textContent = String(err); }
});

let searchTimer = null;
$("search-input").addEventListener("input", (ev) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => search(ev.target.value), 200);
});
$("search-form").addEventListener("submit", (ev) => { ev.preventDefault(); search($("search-input").value); });

$("new-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const id = $("new-id").value.trim();
  if (!id) return;
  await api.send("/api/notes", "POST", { id, content: "" });
  $("new-id").value = "";
  await refreshNotes();
  openNote(id);
});

$("save-btn").onclick = async () => {
  await api.send(`/api/notes/${encodeURIComponent(currentId)}`, "PUT", { content: $("editor").value });
};
$("delete-btn").onclick = async () => {
  if (!confirm(`Delete ${currentId}?`)) return;
  await api.send(`/api/notes/${encodeURIComponent(currentId)}`, "DELETE");
  currentId = null;
  $("editor").value = "";
  $("editor-title").textContent = "Select a note";
  refreshNotes();
};
$("move-btn").onclick = async () => {
  const to = prompt("Move to id:", currentId);
  if (!to || to === currentId) return;
  const note = await api.send(`/api/notes/${encodeURIComponent(currentId)}/move`, "POST", { to });
  currentId = note.id;
  $("editor-title").textContent = note.id;
  refreshNotes();
};

$("feedback-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  await api.send("/api/feedback", "POST", {
    kind: $("fb-kind").value, body: $("fb-body").value, note_id: $("fb-note").value,
  });
  $("fb-body").value = "";
  refreshCapture("pending");
});

$("capture-pending").onclick = () => refreshCapture("pending");
$("capture-all").onclick = () => refreshCapture(null);
$("audit-reload").onclick = refreshAudit;

refreshNotes();
refreshCapture("pending");
refreshAudit();
