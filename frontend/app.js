/* MySharedBrain UI — Confluence-style space. Decoupled: HTTP JSON vs /api/* only. No build step. */
"use strict";

const $ = (id) => document.getElementById(id);
const api = {
  async get(path) {
    const r = await fetch(path);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  async send(path, method, body) {
    const r = await fetch(path, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!r.ok && r.status !== 204) throw new Error(await r.text());
    return r.status === 204 ? null : r.json();
  },
};

let currentId = null;
let editing = false;
let captureFilter = "pending";

/* ---------- tiny markdown renderer (view mode) ---------- */
function esc(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function inlineMd(s) {
  let out = esc(s);
  out = out.replace(/`([^`]+)`/g, "<code>$1</code>");
  out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/(^|[^*\w])\*([^*\n]+)\*/g, "$1<em>$2</em>");
  out = out.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  out = out.replace(/\[\[([^\]]+)\]\]/g, (m, p1) => `<span class="wiki-link" data-target="${esc(p1)}">${esc(p1)}</span>`);
  return out;
}
function renderMarkdown(src) {
  const lines = src.split("\n");
  let html = "";
  let inCode = false;
  let listTag = "";
  const closeList = () => {
    if (listTag) {
      html += `</${listTag}>`;
      listTag = "";
    }
  };
  const isTableSep = (l) => /^\|?[\s:|-]+\|?[\s:|.-]*$/.test(l.trim()) && l.includes("|");
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (/^```/.test(line)) {
      closeList();
      html += inCode ? "</code></pre>" : "<pre><code>";
      inCode = !inCode;
      continue;
    }
    if (inCode) {
      html += esc(line) + "\n";
      continue;
    }
    const t = line.trim();
    if (!t) {
      closeList();
      continue;
    }
    if (t.startsWith("|") && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      closeList();
      const cells = t.split("|").filter((c) => c.trim() !== "").map((c) => `<th>${inlineMd(c.trim())}</th>`).join("");
      html += `<table><thead><tr>${cells}</tr></thead><tbody>`;
      i += 2;
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        const row = lines[i].trim().split("|").filter((c) => c.trim() !== "").map((c) => `<td>${inlineMd(c.trim())}</td>`).join("");
        html += `<tr>${row}</tr>`;
        i++;
      }
      html += "</tbody></table>";
      i--;
      continue;
    }
    const h = t.match(/^(#{1,4})\s+(.*)/);
    if (h) {
      closeList();
      html += `<h${h[1].length}>${inlineMd(h[2])}</h${h[1].length}>`;
      continue;
    }
    if (/^---+$/.test(t) || /^___+$/.test(t)) {
      closeList();
      html += "<hr>";
      continue;
    }
    if (/^>\s?/.test(t)) {
      closeList();
      html += `<blockquote>${inlineMd(t.replace(/^>\s?/, ""))}</blockquote>`;
      continue;
    }
    const ul = t.match(/^[-*]\s+(.*)/);
    const ol = t.match(/^\d+[.)]\s+(.*)/);
    if (ul || ol) {
      const tag = ul ? "ul" : "ol";
      if (listTag !== tag) {
        closeList();
        html += `<${tag}>`;
        listTag = tag;
      }
      html += `<li>${inlineMd((ul || ol)[1])}</li>`;
      continue;
    }
    closeList();
    html += `<p>${inlineMd(t)}</p>`;
  }
  closeList();
  if (inCode) html += "</code></pre>";
  return html;
}
function timeAgo(ts) {
  const s = Math.floor((Date.now() - new Date(ts).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

/* ---------- view switching ---------- */
const VIEWS = ["pages", "ask", "capture", "activity"];
function showView(name) {
  for (const v of VIEWS) {
    $(`view-${v}`).classList.toggle("hidden", v !== name);
    document.querySelector(`.nav-item[data-view="${v}"]`).classList.toggle("active", v === name);
  }
  if (name === "capture") refreshCapture();
  if (name === "activity") refreshAudit();
}
for (const btn of document.querySelectorAll(".nav-item")) {
  btn.addEventListener("click", () => showView(btn.dataset.view));
}
$("feedback-link").addEventListener("click", () => showView("ask"));

/* ---------- page tree (full project view; folders remember collapse) ---------- */
const collapsed = new Set();
function treeIsOpen(full) {
  if (collapsed.has(full)) {
    return !!currentId && (currentId === full || currentId.startsWith(full + "/"));
  }
  return true;
}
function buildTree(ids) {
  const root = {};
  for (const id of ids) {
    let node = root;
    for (const part of id.split("/")) node = node[part] ??= {};
  }
  return root;
}
function renderTree() {
  const tree = $("page-tree");
  tree.innerHTML = "";
  api.get("/api/notes").then(({ notes }) => {
    const nested = buildTree(notes);
    const draw = (node, prefix, parent) => {
      for (const key of Object.keys(node).sort()) {
        const full = prefix ? `${prefix}/${key}` : key;
        const isPage = notes.includes(full);
        const hasKids = Object.keys(node[key]).length > 0;
        const li = document.createElement("li");
        const row = document.createElement("div");
        row.className = "tree-node" + (full === currentId ? " active" : "");
        const caret = document.createElement("button");
        caret.className = "caret" + (hasKids ? "" : " leaf");
        caret.textContent = "▶";
        const label = document.createElement("span");
        label.className = "tree-label-text";
        const icon = document.createElement("span");
        icon.className = "doc-icon";
        icon.innerHTML = '<svg width="14" height="14" viewBox="0 0 16 16"><path fill="currentColor" d="M3 2h7l3 3v9H3V2Zm6 1.5V6H11.5L9 3.5Z"/></svg>';
        label.appendChild(icon);
        label.appendChild(document.createTextNode(" " + (isPage ? key : `${key}/`)));
        label.title = full;
        const kids = document.createElement("ul");
        if (hasKids) {
          const open = treeIsOpen(full);
          if (!open) kids.classList.add("hidden");
          caret.textContent = open ? "▼" : "▶";
          caret.addEventListener("click", () => {
            if (collapsed.has(full)) collapsed.delete(full);
            else collapsed.add(full);
            renderTree();
          });
          draw(node[key], full, kids);
        }
        if (isPage) {
          row.classList.toggle("folder", hasKids);
          label.addEventListener("click", () => openNote(full));
        } else {
          label.style.color = "var(--ds-text-subtle)";
          label.addEventListener("click", () => {
            collapsed.delete(full);
            showFolder(full);
          });
        }
        row.appendChild(caret);
        row.appendChild(label);
        li.appendChild(row);
        li.appendChild(kids);
        parent.appendChild(li);
      }
    };
    if (notes.length === 0) {
      const li = document.createElement("li");
      li.className = "muted";
      li.style.padding = "6px 10px";
      li.textContent = "No pages yet";
      tree.appendChild(li);
    }
    draw(nested, "", tree);
  }).catch(() => {});
}

/* ---------- page view ---------- */
function renderCrumbs(box, id) {
  box.innerHTML = "";
  const parts = id.split("/");
  const crumbs = [["MySharedBrain", null]];
  parts.forEach((p, i) => crumbs.push([p, parts.slice(0, i + 1).join("/")]));
  crumbs.forEach(([label, target], i) => {
    if (i > 0) {
      const sep = document.createElement("span");
      sep.className = "sep";
      sep.textContent = "/";
      box.appendChild(sep);
    }
    const s = document.createElement("span");
    s.className = "crumb";
    s.textContent = label;
    if (target) s.addEventListener("click", () => openPath(target));
    box.appendChild(s);
  });
}
function breadcrumbs(id) {
  renderCrumbs($("breadcrumbs"), id);
}
function folderCrumbs(id) {
  const el = $("folder-crumbs");
  el.innerHTML = "";
  if (id) renderCrumbs(el, id);
}
async function openPath(path) {
  try {
    await openNote(path);
    return;
  } catch {
    // not a note — maybe a folder
  }
  const { notes } = await api.get("/api/notes");
  if (notes.some((n) => n === path || n.startsWith(path + "/"))) {
    await showFolder(path, notes);
    return;
  }
  showResults(path);
}
async function showFolder(folder, knownNotes) {
  const notes = knownNotes || (await api.get("/api/notes")).notes;
  const direct = new Map();
  for (const n of notes) {
    if (n !== folder && !n.startsWith(folder + "/")) continue;
    const rest = n === folder ? "" : n.slice(folder.length + 1);
    if (!rest) continue;
    const seg = rest.split("/")[0];
    if (!direct.has(seg)) direct.set(seg, rest.includes("/") ? "folder" : "page");
  }
  collapsed.delete(folder);
  showView("pages");
  $("empty-state").classList.add("hidden");
  $("page-view").classList.add("hidden");
  $("results-view").classList.remove("hidden");
  folderCrumbs(folder);
  $("results-title").textContent = folder.split("/").pop() || folder;
  const list = $("results-list");
  list.innerHTML = "";
  if (!direct.size) list.innerHTML = "<li class='muted'>Empty folder.</li>";
  for (const [seg, kind] of [...direct.entries()].sort()) {
    const li = document.createElement("li");
    const title = document.createElement("div");
    title.className = "res-title";
    title.textContent = (kind === "folder" ? "\uD83D\uDCC1 " : "\uD83D\uDCC4 ") + seg;
    li.appendChild(title);
    li.addEventListener("click", () => openPath(folder + "/" + seg));
    list.appendChild(li);
  }
  renderTree();
}
async function openNote(id) {
  const note = await api.get(`/api/notes/${encodeURIComponent(id)}`);
  currentId = note.id;
  editing = false;
  $("empty-state").classList.add("hidden");
  $("results-view").classList.add("hidden");
  $("page-view").classList.remove("hidden");
  $("page-title").textContent = note.id.split("/").pop();
  breadcrumbs(note.id);
  $("byline-text").textContent = "You are viewing a vault page · markdown source";
  $("page-render").innerHTML = renderMarkdown(note.content || "*Empty page — hit Edit to write.*");
  $("page-render").classList.remove("hidden");
  $("editor").classList.add("hidden");
  $("editor").value = note.content;
  $("edit-btn").classList.remove("hidden");
  $("save-btn").classList.add("hidden");
  $("cancel-btn").classList.add("hidden");
  showView("pages");
  renderTree();
}
$("page-render").addEventListener("click", (ev) => {
  const t = ev.target.closest(".wiki-link");
  if (t) openNote(t.dataset.target).catch(() => openPath(t.dataset.target));
});
function setEditing(on) {
  editing = on;
  $("page-render").classList.toggle("hidden", on);
  $("editor").classList.toggle("hidden", !on);
  $("edit-btn").classList.toggle("hidden", on);
  $("save-btn").classList.toggle("hidden", !on);
  $("cancel-btn").classList.toggle("hidden", !on);
  if (on) $("editor").focus();
}
$("edit-btn").addEventListener("click", () => setEditing(true));
$("cancel-btn").addEventListener("click", () => setEditing(false));
$("save-btn").addEventListener("click", async () => {
  await api.send(`/api/notes/${encodeURIComponent(currentId)}`, "PUT", { content: $("editor").value });
  await openNote(currentId); // stay on the page, re-rendered from server state
});
$("delete-btn").addEventListener("click", async () => {
  openModal("Delete page?", `“${currentId}” will be removed from the vault. This is audited.`, "", "Delete", async () => {
    await api.send(`/api/notes/${encodeURIComponent(currentId)}`, "DELETE");
    currentId = null;
    $("page-view").classList.add("hidden");
    $("empty-state").classList.remove("hidden");
    renderTree();
  });
});
$("move-btn").addEventListener("click", () => {
  openModal("Move page", "New id (folders are created from the path):", currentId, "Move", async (to) => {
    if (!to || to === currentId) return;
    const note = await api.send(`/api/notes/${encodeURIComponent(currentId)}/move`, "POST", { to });
    openNote(note.id);
  });
});

/* ---------- search ---------- */
let searchTimer = null;
$("global-search").addEventListener("input", (ev) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => quickSearch(ev.target.value), 200);
});
$("global-search").addEventListener("keydown", (ev) => {
  if (ev.key === "Enter") showResults(ev.target.value);
  if (ev.key === "Escape") $("search-results").classList.add("hidden");
});
document.addEventListener("click", (ev) => {
  if (!ev.target.closest("#search-wrap")) $("search-results").classList.add("hidden");
});
async function quickSearch(q) {
  const box = $("search-results");
  if (!q.trim()) {
    box.classList.add("hidden");
    return;
  }
  const res = await api.get(`/api/search?q=${encodeURIComponent(q)}&limit=8`);
  const ids = [...new Set([...res.names, ...res.content.map((h) => h.id)])].slice(0, 8);
  box.innerHTML = "";
  for (const id of ids) {
    const hit = res.content.find((h) => h.id === id);
    const div = document.createElement("div");
    div.className = "search-hit";
    const title = document.createElement("div");
    title.className = "hit-title";
    title.textContent = id;
    div.appendChild(title);
    if (hit && hit.excerpts[0]) {
      const ex = document.createElement("span");
      ex.className = "hit-ex";
      ex.textContent = hit.excerpts[0];
      div.appendChild(ex);
    }
    div.addEventListener("click", () => {
      box.classList.add("hidden");
      openNote(id);
    });
    box.appendChild(div);
  }
  const more = document.createElement("div");
  more.className = "search-more";
  more.textContent = `See all results for “${q}”`;
  more.addEventListener("click", () => {
    box.classList.add("hidden");
    showResults(q);
  });
  box.appendChild(more);
  box.classList.remove("hidden");
}
async function showResults(q) {
  if (!q.trim()) return;
  const res = await api.get(`/api/search?q=${encodeURIComponent(q)}&limit=20`);
  const ids = [...new Set([...res.names, ...res.content.map((h) => h.id)])];
  showView("pages");
  $("empty-state").classList.add("hidden");
  $("page-view").classList.add("hidden");
  $("results-view").classList.remove("hidden");
  folderCrumbs("");
  $("results-title").textContent = `Search results for “${q}”`;
  const list = $("results-list");
  list.innerHTML = "";
  if (!ids.length) {
    list.innerHTML = "<li class='muted'>No pages match. Try asking the librarian — a miss gets queued for retrieval.</li>";
    return;
  }
  for (const id of ids) {
    const hit = res.content.find((h) => h.id === id);
    const li = document.createElement("li");
    const title = document.createElement("div");
    title.className = "res-title";
    title.textContent = id;
    li.appendChild(title);
    if (hit) for (const ex of hit.excerpts.slice(0, 2)) {
      const s = document.createElement("span");
      s.className = "res-ex";
      s.textContent = ex;
      li.appendChild(s);
    }
    li.addEventListener("click", () => openNote(id));
    list.appendChild(li);
  }
}

/* ---------- ask + feedback ---------- */
$("ask-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const q = $("ask-input").value;
  const box = $("ask-result");
  box.textContent = "Asking…";
  try {
    const ans = await api.send("/api/request", "POST", { question: q });
    box.innerHTML = "";
    const card = document.createElement("div");
    card.className = "answer-card";
    const p = document.createElement("p");
    p.textContent = ans.message;
    card.appendChild(p);
    for (const id of ans.note_ids) {
      const b = document.createElement("button");
      b.className = "btn-default";
      b.textContent = id;
      b.style.marginRight = "6px";
      b.addEventListener("click", () => openNote(id));
      card.appendChild(b);
    }
    box.appendChild(card);
  } catch (err) {
    box.textContent = String(err);
  }
});
$("feedback-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  await api.send("/api/feedback", "POST", {
    kind: $("fb-kind").value,
    body: $("fb-body").value,
    note_id: $("fb-note").value,
  });
  $("fb-body").value = "";
  updateBadge();
});

/* ---------- capture ---------- */
for (const btn of document.querySelectorAll(".cap-filter")) {
  btn.addEventListener("click", () => {
    captureFilter = btn.dataset.status;
    for (const other of document.querySelectorAll(".cap-filter")) {
      const on = other === btn;
      other.classList.toggle("active", on);
      other.classList.toggle("btn-default", on);
      other.classList.toggle("btn-subtle", !on);
    }
    refreshCapture();
  });
}
async function updateBadge() {
  const { entries } = await api.get("/api/capture?status=pending");
  const badge = $("capture-badge");
  badge.textContent = entries.length;
  badge.classList.toggle("hidden", entries.length === 0);
}
async function refreshCapture() {
  const params = captureFilter === "all" ? "" : `?status=${captureFilter}`;
  const { entries } = await api.get(`/api/capture${params}`);
  const list = $("capture-list");
  list.innerHTML = "";
  if (!entries.length) {
    list.innerHTML = "<li class='muted'>Queue is clear. Nothing awaiting review.</li>";
  }
  for (const e of entries) {
    const li = document.createElement("li");
    const head = document.createElement("div");
    head.className = "card-head";
    const kind = document.createElement("span");
    kind.className = `lozenge ${e.kind}`;
    kind.textContent = e.kind;
    const status = document.createElement("span");
    status.className = `lozenge ${e.status}`;
    status.textContent = e.status;
    const title = document.createElement("strong");
    title.textContent = e.note_id || "general";
    head.appendChild(kind);
    head.appendChild(status);
    head.appendChild(title);
    li.appendChild(head);
    const body = document.createElement("div");
    body.className = "card-body";
    body.textContent = e.body;
    li.appendChild(body);
    const meta = document.createElement("div");
    meta.className = "card-meta";
    meta.textContent = `${timeAgo(e.ts)}${e.reviewer ? ` · reviewed by ${e.reviewer}` : ""}${e.review_note ? ` · ${e.review_note}` : ""}`;
    li.appendChild(meta);
    if (e.status === "pending") {
      const row = document.createElement("div");
      row.className = "card-actions";
      const ok = document.createElement("button");
      ok.className = "btn-primary";
      ok.textContent = "Apply";
      ok.addEventListener("click", async () => {
        let content = null;
        if (e.note_id) {
          try {
            const note = await api.get(`/api/notes/${encodeURIComponent(e.note_id)}`);
            content = `${note.content}\n\n${e.body}\n`;
          } catch {
            content = `${e.body}\n`;
          }
        }
        await api.send(`/api/capture/${e.id}/review`, "POST", { verdict: "applied", reviewer: "ui", content });
        refreshCapture();
        updateBadge();
        renderTree();
      });
      const approve = document.createElement("button");
      approve.className = "btn-default";
      approve.textContent = "Approve";
      approve.addEventListener("click", async () => {
        await api.send(`/api/capture/${e.id}/review`, "POST", { verdict: "approved", reviewer: "ui" });
        refreshCapture();
        updateBadge();
      });
      const no = document.createElement("button");
      no.className = "btn-default";
      no.textContent = "Reject";
      no.addEventListener("click", async () => {
        await api.send(`/api/capture/${e.id}/review`, "POST", { verdict: "rejected", reviewer: "ui" });
        refreshCapture();
        updateBadge();
      });
      row.appendChild(ok);
      row.appendChild(approve);
      row.appendChild(no);
      li.appendChild(row);
    }
    list.appendChild(li);
  }
  updateBadge();
}

/* ---------- activity ---------- */
$("audit-reload").addEventListener("click", refreshAudit);
async function refreshAudit() {
  const { entries } = await api.get("/api/audit?limit=50");
  const list = $("audit-list");
  list.innerHTML = "";
  for (const e of entries) {
    const li = document.createElement("li");
    const av = document.createElement("span");
    av.className = "avatar avatar-sm";
    av.textContent = (e.actor || "?")[0].toUpperCase();
    const wrap = document.createElement("div");
    const text = document.createElement("div");
    text.className = "activity-text";
    text.innerHTML = "";
    const who = document.createElement("strong");
    who.textContent = e.actor;
    text.appendChild(who);
    text.appendChild(document.createTextNode(` ${e.action} `));
    if (e.note_id) {
      const code = document.createElement("code");
      code.textContent = e.note_id;
      text.appendChild(code);
    }
    if (e.detail) text.appendChild(document.createTextNode(` — ${e.detail}`));
    const time = document.createElement("div");
    time.className = "activity-time";
    time.textContent = timeAgo(e.ts);
    wrap.appendChild(text);
    wrap.appendChild(time);
    li.appendChild(av);
    li.appendChild(wrap);
    list.appendChild(li);
  }
}

/* ---------- modal ---------- */
let modalOk = null;
function openModal(title, desc, initial, okLabel, onOk) {
  $("modal-title").textContent = title;
  $("modal-desc").textContent = desc;
  $("modal-input").value = initial;
  $("modal-ok").textContent = okLabel;
  modalOk = onOk;
  $("modal").classList.remove("hidden");
  $("modal-input").focus();
  $("modal-input").select();
}
function closeModal() {
  $("modal").classList.add("hidden");
  modalOk = null;
}
$("modal-cancel").addEventListener("click", closeModal);
$("modal").addEventListener("click", (ev) => {
  if (ev.target.id === "modal") closeModal();
});
$("modal-ok").addEventListener("click", async () => {
  const fn = modalOk;
  const val = $("modal-input").value;
  closeModal();
  if (fn) await fn(val);
});
function createPage() {
  openModal("Create page", "Page id (use slashes for folders, e.g. projects/homelab):", "", "Create", async (id) => {
    if (!id.trim()) return;
    await api.send("/api/notes", "POST", { id: id.trim(), content: "" });
    openNote(id.trim());
  });
}
$("create-btn").addEventListener("click", createPage);
$("empty-create").addEventListener("click", createPage);

showView("pages");
renderTree();
updateBadge();
