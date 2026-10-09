// NexCYR app shell — router, global search, AI status chip, boot wiring.
import { endpoints } from "./api.js?v=20261008-fast1";
import { views } from "./views.js?v=20261009-speed1";
import { el, toast, closeModal } from "./ui.js";
import * as voice from "./voice.js";

const viewHost = document.getElementById("view");
const topTitle = document.getElementById("topTitle");
const topSub = document.getElementById("topSub");
const navItems = Array.from(document.querySelectorAll(".nav-item"));
const sidebarToggle = document.getElementById("sidebarToggle");

// Compact navigation is the default command-center state; the three-dot
// control opens/closes the full navigation without changing view routing.
document.body.classList.add("sidebar-collapsed");
function syncSidebarToggle() {
  const collapsed = document.body.classList.contains("sidebar-collapsed");
  if (sidebarToggle) {
    sidebarToggle.textContent = collapsed ? "•••" : "×";
    sidebarToggle.setAttribute("aria-label", collapsed ? "Open navigation" : "Close navigation");
    sidebarToggle.title = collapsed ? "Open navigation" : "Close navigation";
  }
}
sidebarToggle?.addEventListener("click", () => {
  document.body.classList.toggle("sidebar-collapsed");
  document.body.classList.toggle("sidebar-open", !document.body.classList.contains("sidebar-collapsed"));
  syncSidebarToggle();
});
syncSidebarToggle();

const TITLES = {
  dashboard: ["Command Center", "Live platform posture"],
  assessments: ["Assessments", "Engagement containers"],
  targets: ["Authorized Targets", "Scan authorization gate"],
  scans: ["Scans", "Authorized scanning"],
  recon: ["Reconnaissance", "Host / port / service discovery"],
  findings: ["Findings", "Risk-scored security findings"],
  soc: ["SOC Monitoring", "Events & correlation"],
  attackmap: ["Cyber Attack Map", "Relationship graph"],
  purple: ["Purple Team", "Detection validation"],
  wifi: ["Wi-Fi Security", "Wireless assessment"],
  agents: ["NexCYR Agents", "Hybrid Cloud + distributed agents"],
  ai: ["NexCYR Intelligence", "Contextual assistant"],
  reports: ["Reports", "PDF assessment reports"],
  settings: ["Settings", "Platform configuration"],
};

let currentAttackMap = null;

const ctx = {
  navigate,
  refreshAiChip,
};

function setActive(view) {
  navItems.forEach((n) => n.classList.toggle("active", n.dataset.view === view));
  const [t, s] = TITLES[view] || ["NexCYR", ""];
  topTitle.firstChild.textContent = t + " ";
  topSub.textContent = s ? "· " + s : "";
  document.title = `NexCYR — ${t}`;
}

async function navigate(view) {
  if (!views[view]) view = "dashboard";
  if (currentAttackMap) { currentAttackMap.destroy(); currentAttackMap = null; }
  voice.stopSpeaking();
  setActive(view);
  try {
    window.location.hash = view;
  } catch (_) {}
  await views[view](viewHost, ctx);
  viewHost.scrollTop = 0;
}

navItems.forEach((n) => n.addEventListener("click", (e) => {
  e.preventDefault();
  navigate(n.dataset.view);
  if (window.matchMedia("(max-width: 780px)").matches) {
    document.body.classList.add("sidebar-collapsed");
    document.body.classList.remove("sidebar-open");
    syncSidebarToggle();
  }
}));

// ---- modal close wiring ----
document.getElementById("modalClose").addEventListener("click", closeModal);
document.getElementById("modalBack").addEventListener("click", (e) => { if (e.target.id === "modalBack") closeModal(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

// ---- operator chip ----
try {
  const op = sessionStorage.getItem("nexcyr.operator");
  if (op) document.getElementById("opName").textContent = op;
} catch (_) {}

// ---- AI status chip ----
async function refreshAiChip() {
  try {
    const st = await endpoints.aiStatus();
    const dot = document.getElementById("aiDot");
    const txt = document.getElementById("aiChipText");
    const external = st.external_provider_configured;
    dot.className = "dot" + (external ? "" : " warn");
    txt.textContent = external ? `AI · ${st.provider || "provider"}` : "AI · fallback";
    document.getElementById("aiChip").title =
      `NexCYR Intelligence: ${st.engine} (${external ? "external provider" : "fallback engine — no API key"})`;
  } catch (_) {
    document.getElementById("aiChipText").textContent = "AI · offline";
    document.getElementById("aiDot").className = "dot crit";
  }
}

// ---- load voice settings ----
async function loadVoiceSettings() {
  try {
    const s = await endpoints.settings();
    voice.configureVoice(s.voice || {});
  } catch (_) {}
}

// ---- global search ----
const searchInput = document.getElementById("globalSearch");
const searchResults = document.getElementById("searchResults");
let searchTimer = null;

function renderSearch(data) {
  searchResults.innerHTML = "";
  const groups = [
    ["assessments", "Assessments", "assessments"],
    ["targets", "Targets", "targets"],
    ["scans", "Scans", "scans"],
    ["findings", "Findings", "findings"],
    ["soc_events", "SOC Events", "soc"],
    ["purple_team_tests", "Purple Team", "purple"],
  ];
  let any = false;
  groups.forEach(([key, label, view]) => {
    const items = data[key] || [];
    if (!items.length) return;
    any = true;
    searchResults.appendChild(el("div", { class: "group", text: label }));
    items.forEach((it) => {
      searchResults.appendChild(el("div", { class: "item", onClick: () => { searchResults.classList.remove("open"); navigate(view); } },
        el("div", { class: "l", text: it.label }),
        el("div", { class: "d", text: it.detail || "" })));
    });
  });
  if (!any) {
    searchResults.appendChild(el("div", { class: "item" }, el("div", { class: "d", text: "No matches for this query." })));
  }
  searchResults.classList.add("open");
}

searchInput.addEventListener("input", () => {
  const q = searchInput.value.trim();
  clearTimeout(searchTimer);
  if (q.length < 2) { searchResults.classList.remove("open"); return; }
  searchTimer = setTimeout(async () => {
    try {
      const data = await endpoints.search(q);
      renderSearch(data);
    } catch (e) {
      searchResults.innerHTML = "";
      searchResults.appendChild(el("div", { class: "item" }, el("div", { class: "d", text: "Search failed: " + e.message })));
      searchResults.classList.add("open");
    }
  }, 260);
});
searchInput.addEventListener("focus", () => { if (searchResults.children.length) searchResults.classList.add("open"); });
document.addEventListener("click", (e) => {
  if (!e.target.closest(".searchbox")) searchResults.classList.remove("open");
});

// ---- boot ----
async function boot() {
  // Render the requested view first. Non-essential status/settings calls
  // continue in the background so the command center feels immediate.
  const initial = (window.location.hash || "#dashboard").slice(1);
  await navigate(views[initial] ? initial : "dashboard");

  Promise.allSettled([loadVoiceSettings(), refreshAiChip()]);

  endpoints.health()
    .then((h) => {
      if (h && h.status && h.status !== "healthy") {
        toast("Service degraded", h.status, "warn");
      }
    })
    .catch(() => {
      toast("Backend unreachable", "Could not reach /health", "err");
    });
}

window.addEventListener("hashchange", () => {
  const v = (window.location.hash || "").slice(1);
  if (v && views[v] && !navItems.find((n) => n.classList.contains("active") && n.dataset.view === v)) {
    navigate(v);
  }
});

boot();
