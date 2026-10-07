// NexCYR UI helpers — DOM building, toasts, modal, tables, badges, states.

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "html") node.innerHTML = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === "style" && typeof v === "object") Object.assign(node.style, v);
    else node.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    node.appendChild(typeof c === "string" || typeof c === "number" ? document.createTextNode(String(c)) : c);
  }
  return node;
}

export const SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"];

export function normSev(s) {
  const v = (s || "info").toLowerCase();
  if (v === "informational") return "info";
  return SEVERITY_ORDER.includes(v) ? v : "info";
}

export function badge(text, cls) {
  return el("span", { class: `badge ${cls || "neutral"}`, text: String(text ?? "") });
}

export function sevBadge(sev) {
  const s = normSev(sev);
  return badge(s, s);
}

export function statusBadge(status) {
  const s = (status || "").toLowerCase();
  const map = {
    open: "warn", in_progress: "info", resolved: "ok", accepted: "ok", closed: "neutral",
    completed: "ok", running: "info", pending: "warn", planned: "neutral", executed: "info",
    cancelled: "neutral", detected: "ok", missed: "critical", partial: "warn",
    created: "neutral", active: "ok", failed: "critical", nmap_unavailable: "warn",
    contained: "ok", investigating: "info", created_: "neutral",
  };
  return badge(s, map[s] || "neutral");
}

export function riskLevelClass(level) {
  const l = (level || "").toLowerCase();
  if (["critical", "high"].includes(l)) return "crit";
  if (["medium", "elevated", "moderate"].includes(l)) return "warn";
  if (["low", "minimal"].includes(l)) return "good";
  return "info";
}

// ---- toasts ----
let toastHost = null;
export function toast(title, body = "", kind = "info", ms = 4200) {
  toastHost = toastHost || document.getElementById("toasts");
  if (!toastHost) return;
  const t = el("div", { class: `toast ${kind}` },
    el("div", { class: "tt", text: title }),
    body ? el("div", { class: "tb", text: body }) : null
  );
  toastHost.appendChild(t);
  setTimeout(() => {
    t.style.transition = "opacity .3s, transform .3s";
    t.style.opacity = "0"; t.style.transform = "translateX(20px)";
    setTimeout(() => t.remove(), 320);
  }, ms);
}

// ---- modal ----
const modalBack = () => document.getElementById("modalBack");
export function openModal(title, bodyNode, footNodes = []) {
  const back = modalBack();
  document.getElementById("modalTitle").textContent = title;
  const body = document.getElementById("modalBody");
  body.innerHTML = "";
  body.appendChild(bodyNode);
  const foot = document.getElementById("modalFoot");
  foot.innerHTML = "";
  footNodes.forEach((n) => foot.appendChild(n));
  back.classList.add("open");
  return back;
}
export function closeModal() {
  const back = modalBack();
  if (back) back.classList.remove("open");
}
export function confirmModal(title, message, onConfirm, confirmLabel = "Confirm", danger = true) {
  const body = el("div", { class: "muted", style: { lineHeight: "1.6", fontSize: "13px" }, text: message });
  const cancel = el("button", { class: "btn ghost", text: "Cancel", onClick: closeModal });
  const ok = el("button", { class: `btn ${danger ? "danger" : "primary"}`, text: confirmLabel, onClick: async () => { closeModal(); await onConfirm(); } });
  openModal(title, body, [cancel, ok]);
}

// ---- loading / empty states ----
export function loadingState(msg = "Loading…") {
  return el("div", { class: "state" }, el("div", { class: "spinner" }), el("div", { class: "sm", text: msg }));
}
export function emptyState(big, small = "") {
  return el("div", { class: "state" }, el("div", { class: "big", text: big }), small ? el("div", { class: "sm", text: small }) : null);
}

// ---- table ----
export function table(columns, rows) {
  // columns: [{ key, label, render?(row) }]
  const thead = el("thead", {}, el("tr", {}, columns.map((c) => el("th", { text: c.label }))));
  const tbody = el("tbody", {});
  if (!rows.length) {
    tbody.appendChild(el("tr", {}, el("td", { colspan: String(columns.length) }, emptyState("No records", "Nothing stored yet for this module."))));
  } else {
    rows.forEach((row) => {
      tbody.appendChild(el("tr", {}, columns.map((c) => el("td", {}, c.render ? c.render(row) : (row[c.key] ?? "—")))));
    });
  }
  return el("div", { class: "table-wrap" }, el("table", {}, thead, tbody));
}

// ---- form field helpers ----
export function field(labelText, inputNode, hint) {
  return el("div", { class: "field" },
    el("label", { text: labelText }),
    inputNode,
    hint ? el("div", { class: "hint", text: hint }) : null
  );
}
export function input(name, attrs = {}) {
  return el("input", { name, ...attrs });
}
export function textarea(name, attrs = {}) {
  return el("textarea", { name, ...attrs });
}
export function select(name, options, attrs = {}) {
  const sel = el("select", { name, ...attrs });
  options.forEach((o) => {
    const [val, label] = Array.isArray(o) ? o : [o, o];
    sel.appendChild(el("option", { value: val, text: label }));
  });
  return sel;
}
export function checkbox(name, checked = false, labelText = "") {
  return el("label", { class: "check" }, el("input", { type: "checkbox", name, checked: checked || null }), labelText);
}

// read a form node into an object; skip empty optional strings -> undefined
export function readForm(formNode, { numbers = [], bools = [], optionalEmpty = [] } = {}) {
  const out = {};
  const data = new FormData(formNode);
  for (const [k, v] of data.entries()) {
    let val = typeof v === "string" ? v.trim() : v;
    if (numbers.includes(k)) {
      out[k] = val === "" ? null : Number(val);
      continue;
    }
    out[k] = val;
  }
  bools.forEach((b) => { out[b] = formNode.querySelector(`[name="${b}"]`)?.checked ?? false; });
  optionalEmpty.forEach((k) => { if (out[k] === "") out[k] = null; });
  return out;
}

export function fmtDate(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (isNaN(d)) return iso;
    return d.toLocaleString(undefined, { year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  } catch (_) { return iso; }
}

export function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

export function viewHead(title, sub, actions = []) {
  return el("div", { class: "view-head" },
    el("div", {}, el("h1", { text: title }), sub ? el("div", { class: "sub", text: sub }) : null),
    el("div", { class: "actions" }, actions)
  );
}
