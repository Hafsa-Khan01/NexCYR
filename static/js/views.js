// NexCYR views — every screen, backed by real API data. No fabricated metrics.
import { endpoints } from "./api.js";
import {
  el, table, badge, sevBadge, statusBadge, field, input, textarea, select, checkbox,
  readForm, openModal, closeModal, confirmModal, toast, loadingState, emptyState,
  viewHead, fmtDate, riskLevelClass, normSev, SEVERITY_ORDER,
} from "./ui.js";
import * as voice from "./voice.js";
import { AttackMap, MAP_TYPE_LABEL, MAP_TYPE_COLOR } from "./attackmap.js";

// ------------------------------------------------------------------
// Shared: Ask NexCYR panel (used on Dashboard + Intelligence view)
// ------------------------------------------------------------------
export function askPanel(ctx, { contextType = null, contextId = null, title = "Ask NexCYR", tall = false } = {}) {
  const thread = el("div", { class: "ai-thread" });
  const ta = textarea("question", { placeholder: "Ask about a finding, scan, assessment, alert, or your highest risk…", rows: tall ? "3" : "2" });
  const voiceBtn = el("button", { class: "btn ghost sm", title: "Toggle voice output" }, el("span", { text: voice.isVoiceEnabled() ? "🔊" : "🔇" }));

  function renderVoiceBtn() {
    voiceBtn.textContent = voice.isVoiceEnabled() ? "🔊 Voice on" : "🔇 Voice off";
    voiceBtn.classList.toggle("primary", voice.isVoiceEnabled());
  }
  renderVoiceBtn();
  voiceBtn.addEventListener("click", () => {
    voice.setVoiceEnabled(!voice.isVoiceEnabled());
    renderVoiceBtn();
    toast("Voice " + (voice.isVoiceEnabled() ? "enabled" : "disabled"), "", "info", 2000);
  });

  const askBtn = el("button", { class: "btn primary", text: "Ask" });
  const stopBtn = el("button", { class: "btn ghost", text: "Stop voice" });
  stopBtn.addEventListener("click", () => voice.stopSpeaking());

  const quicks = [
    "What is my highest risk?",
    "Summarize this assessment.",
    "What should I do next?",
    "Show me the important SOC activity.",
    "Explain this finding.",
  ];

  function pushMsg(role, text, meta = {}) {
    const msg = el("div", { class: `ai-msg ${role}` },
      el("div", { class: "who" },
        role === "user" ? "You" : "NexCYR Intelligence",
        meta.engine ? el("span", { class: "eng", text: "· " + meta.engine }) : null
      ),
      el("div", { class: "txt", text })
    );
    if (role === "bot" && text) {
      const speakBtn = el("button", { class: "btn ghost sm", text: "🔊 Speak" });
      speakBtn.addEventListener("click", () => {
        voice.speak(text);
        msg.classList.add("speaking");
        voice.onVoiceState(() => { if (!voice.isSpeaking()) msg.classList.remove("speaking"); });
      });
      const stop = el("button", { class: "btn ghost sm", text: "Stop", onClick: () => { voice.stopSpeaking(); msg.classList.remove("speaking"); } });
      msg.appendChild(el("div", { class: "voice-row" }, speakBtn, stop));
    }
    thread.appendChild(msg);
    thread.scrollTop = thread.scrollHeight;
    return msg;
  }

  async function ask() {
    const q = ta.value.trim();
    if (!q) return;
    pushMsg("user", q);
    ta.value = "";
    askBtn.disabled = true;
    const pending = pushMsg("bot", "Thinking…");
    try {
      const res = await endpoints.ai({ question: q, context_type: contextType || undefined, context_id: contextId ?? undefined });
      pending.querySelector(".txt").textContent = res.answer || "(no answer)";
      pending.querySelector(".who").appendChild(el("span", { class: "eng", text: "· " + (res.engine || "engine") }));

      // NexCYR can speak the complete answer automatically when voice is enabled.
      // The operator still has the explicit Speak/Stop controls for replay.
      if (res.answer && voice.isVoiceEnabled()) {
        voice.speak(res.answer);
      }

      const sr = el("button", { class: "btn ghost sm", text: "🔊 Speak" });
      sr.addEventListener("click", () => { voice.speak(res.answer || ""); pending.classList.add("speaking"); voice.onVoiceState(() => { if (!voice.isSpeaking()) pending.classList.remove("speaking"); }); });
      const st = el("button", { class: "btn ghost sm", text: "Stop", onClick: () => { voice.stopSpeaking(); pending.classList.remove("speaking"); } });
      pending.appendChild(el("div", { class: "voice-row" }, sr, st));
      if (res.risk_level) pending.querySelector(".who").appendChild(badge(res.risk_level, normSev(res.risk_level)));
      thread.scrollTop = thread.scrollHeight;
    } catch (e) {
      pending.querySelector(".txt").textContent = "Intelligence request failed: " + e.message;
    } finally {
      askBtn.disabled = false;
      ta.focus();
    }
  }

  askBtn.addEventListener("click", ask);
  ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) ask(); });

  const quickRow = el("div", { class: "quick" }, quicks.map((q) =>
    el("button", { text: q, onClick: () => { ta.value = q; ask(); } })));

  return el("div", { class: "panel ask" },
    el("h3", {}, "✧ " + title, contextType ? el("span", { class: "tag", text: `context: ${contextType}${contextId ? " #" + contextId : ""}` }) : null),
    thread,
    quickRow,
    el("div", { class: "ask-input" }, ta, askBtn),
    el("div", { style: { display: "flex", gap: "8px" } }, voiceBtn, stopBtn)
  );
}

// ------------------------------------------------------------------
// Shared helpers
// ------------------------------------------------------------------
async function withLoading(container, fn, msg = "Loading…") {
  container.innerHTML = "";
  const loader = loadingState(msg);
  container.appendChild(loader);
  try {
    await fn(container);
    loader.remove();
  } catch (e) {
    container.innerHTML = "";
    container.appendChild(emptyState("Error", e.message));
    toast("Request failed", e.message, "err");
  }
}

function gauge(score, level) {
  const pct = Math.max(0, Math.min(100, Number(score) || 0));
  const r = 54, c = 2 * Math.PI * r;
  const col = ["critical", "high"].includes((level || "").toLowerCase()) ? "#ff2d55"
    : ["medium", "elevated", "moderate"].includes((level || "").toLowerCase()) ? "#f59e0b"
    : ["low", "minimal"].includes((level || "").toLowerCase()) ? "#22c55e" : "#22e0ff";
  const svgns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgns, "svg");
  svg.setAttribute("width", "130"); svg.setAttribute("height", "130"); svg.setAttribute("viewBox", "0 0 130 130");
  const bg = document.createElementNS(svgns, "circle");
  bg.setAttribute("cx", "65"); bg.setAttribute("cy", "65"); bg.setAttribute("r", String(r));
  bg.setAttribute("fill", "none"); bg.setAttribute("stroke", "rgba(255,255,255,0.07)"); bg.setAttribute("stroke-width", "10");
  const fg = document.createElementNS(svgns, "circle");
  fg.setAttribute("cx", "65"); fg.setAttribute("cy", "65"); fg.setAttribute("r", String(r));
  fg.setAttribute("fill", "none"); fg.setAttribute("stroke", col); fg.setAttribute("stroke-width", "10");
  fg.setAttribute("stroke-linecap", "round");
  fg.setAttribute("stroke-dasharray", String(c));
  fg.setAttribute("stroke-dashoffset", String(c - (pct / 100) * c));
  fg.style.filter = `drop-shadow(0 0 6px ${col})`;
  svg.appendChild(bg); svg.appendChild(fg);
  return el("div", { class: "gauge" }, svg,
    el("div", { class: "val" }, String(pct), el("small", { text: (level || "unknown").toUpperCase() })));
}

function sevBars(dist) {
  const max = Math.max(1, ...Object.values(dist || {}).map((v) => Number(v) || 0));
  const colors = { critical: "#ff2d55", high: "#ff7a18", medium: "#f5c518", low: "#38bdf8", info: "#8b98a5" };
  return el("div", {}, SEVERITY_ORDER.map((s) => {
    const n = Number((dist || {})[s]) || 0;
    return el("div", { class: "sev-bar" },
      el("span", { class: "lab", style: { color: colors[s] }, text: s }),
      el("div", { class: "track" }, el("div", { class: "fill", style: { width: (n / max) * 100 + "%", background: colors[s], boxShadow: `0 0 8px ${colors[s]}` } })),
      el("span", { class: "cnt", text: String(n) })
    );
  }));
}

async function targetOptions() {
  const targets = await endpoints.targets();
  return targets.map((t) => [String(t.id), `${t.name || t.value} (${t.target_type}${t.authorized ? " · authorized" : " · NOT authorized"})`]);
}

async function authorizedTargetOptions() {
  const targets = await endpoints.targets();
  return targets
    .filter((t) => Boolean(t.authorized))
    .map((t) => [String(t.id), `${t.name || t.value} (${t.target_type} · authorized)`]);
}
async function assessmentOptions() {
  const a = await endpoints.assessments();
  return [["", "— none —"]].concat(a.map((x) => [String(x.id), x.name]));
}

const DASHBOARD_SOUND_KEY = "nexcyr.dashboard.soundAlerts";
const DASHBOARD_ANNOUNCE_KEY = "nexcyr.dashboard.announcements";
let dashboardRefreshTimer = null;
let dashboardAudioContext = null;

function dashboardPreference(key) {
  try { return window.localStorage.getItem(key) === "true"; } catch (_) { return false; }
}
function setDashboardPreference(key, enabled) {
  try { window.localStorage.setItem(key, enabled ? "true" : "false"); } catch (_) {}
}
function primeDashboardAudio() {
  try {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return false;
    if (!dashboardAudioContext) dashboardAudioContext = new AudioContextClass();
    if (dashboardAudioContext.state === "suspended") dashboardAudioContext.resume().catch(() => {});
    return true;
  } catch (_) { return false; }
}
function playDashboardAlertTone() {
  if (!dashboardAudioContext && !primeDashboardAudio()) return;
  try {
    const context = dashboardAudioContext;
    if (context.state === "suspended") context.resume().catch(() => {});
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    const start = context.currentTime;
    oscillator.type = "sine";
    oscillator.frequency.setValueAtTime(880, start);
    gain.gain.setValueAtTime(0.001, start);
    gain.gain.exponentialRampToValueAtTime(0.12, start + 0.025);
    gain.gain.exponentialRampToValueAtTime(0.001, start + 0.24);
    oscillator.connect(gain);
    gain.connect(context.destination);
    oscillator.start(start);
    oscillator.stop(start + 0.25);
  } catch (_) {}
}
function dashboardSpeechText(d) {
  const c = d?.counts || {};
  const risk = d?.risk || {};
  const sev = risk.severity_distribution || {};
  const parts = [
    "NexCYR dashboard summary.",
    `${c.assessments || 0} assessments. ${c.authorized_targets || 0} authorized targets. ${c.scans || 0} recorded scans.`,
    `${c.open_findings || 0} open findings, including ${c.critical_findings || 0} critical and ${c.high_findings || 0} high severity findings.`,
    `${c.open_soc_alerts || 0} open SOC alerts, from ${c.soc_alerts || 0} total recorded SOC events.`,
    `Overall risk posture: ${risk.level || "unknown"}, score ${risk.score ?? 0} out of 100.`,
    `Severity distribution: ${sev.critical || 0} critical, ${sev.high || 0} high, ${sev.medium || 0} medium, ${sev.low || 0} low, ${sev.info || 0} informational.`,
    `Purple Team: ${d?.purple_team?.total || 0} tests, ${d?.purple_team?.detected || 0} detected, ${d?.purple_team?.missed || 0} missed detections.`
  ];
  (d?.recent_findings || []).slice(0, 5).forEach((f) => parts.push(
    `Finding ${f.severity || "unknown"}: ${f.title || "untitled"}; status ${f.status || "unknown"}.`
  ));
  (d?.recent_soc_events || []).slice(0, 5).forEach((e) => parts.push(
    `SOC ${e.severity || "info"} event: ${e.message || e.event_type || "recorded event"}.`
  ));
  (d?.correlation?.clusters || []).slice(0, 3).forEach((cl) => parts.push(
    `Correlation: ${cl.category?.replace(/_/g, " ") || "activity"}; ${cl.event_count || 0} event(s), highest severity ${cl.max_severity || "unknown"}.`
  ));
  (d?.agents || []).slice(0, 4).forEach((a) => parts.push(
    `Agent ${a.name || a.agent_key || a.id}: ${a.status || "unknown"}.`
  ));
  return parts.join(" ").slice(0, 3800);
}

// ------------------------------------------------------------------
// VIEW: Dashboard
// ------------------------------------------------------------------
async function dashboardView(container, ctx) {
  if (dashboardRefreshTimer) {
    window.clearInterval(dashboardRefreshTimer);
    dashboardRefreshTimer = null;
  }
  let latestDashboardData = null;
  const seenFindingIds = new Set();
  const seenSocIds = new Set();
  let refreshInFlight = false;

  await withLoading(container, async (c) => {
    const d = await endpoints.dashboard();
    latestDashboardData = d;
    (d.recent_findings || []).forEach((f) => seenFindingIds.add(f.id));
    (d.recent_soc_events || []).forEach((e) => seenSocIds.add(e.id));
    const k = d.counts;
    const riskHas = d.risk.has_data;

    const hero = el("section", { class: "dashboard-hero" },
      el("div", { class: "hero-grid" },
        el("div", { class: "hero-copy" },
          el("div", { class: "hero-kicker" }, "NexCYR // SECURITY OPERATIONS"),
          el("h1", {}, "Unified Cybersecurity Command Center"),
          el("p", {}, "Assess authorized assets, discover exposure, correlate SOC activity, validate detections and move findings into a measurable Purple Team workflow."),
          el("div", { class: "hero-status" },
            el("span", { class: "hero-pulse" }),
            el("span", {}, "Platform online"),
            el("span", { class: "hero-divider" }, "•"),
            el("span", { class: "hero-mono", text: "LIVE" })
          )
        ),
        el("div", { class: "hero-actions" },
          el("div", { class: "hero-label" }, "OPERATE"),
          el("button", { class: "btn primary hero-btn", text: "＋ Authorized Target", onClick: () => ctx.navigate("targets") }),
          el("button", { class: "btn hero-btn", text: "◈ New Assessment", onClick: () => ctx.navigate("assessments") }),
          el("button", { class: "btn ghost hero-btn", text: "⌖ Run Recon", onClick: () => ctx.navigate("recon") }),
          el("button", { class: "btn ghost hero-btn", text: "✧ Ask NexCYR", onClick: () => ctx.navigate("ai") })
        )
      ),
      el("div", { class: "hero-scanline" })
    );

    const metrics = el("div", { class: "grid cols-4", id: "dashMetrics" },
      metric("Assessments", k.assessments, "total", "info"),
      metric("Authorized Targets", k.authorized_targets, `${k.targets} total · ${k.active_targets} active`, "info"),
      metric("Scans", k.scans, "recorded", "info"),
      metric("Open Findings", k.open_findings, `${k.findings} total`, k.open_findings ? "warn" : "good"),
      metric("Critical", k.critical_findings, "findings", k.critical_findings ? "crit" : "good"),
      metric("High", k.high_findings, "findings", k.high_findings ? "crit" : "good"),
      metric("SOC Alerts", k.open_soc_alerts, `${k.soc_alerts} total`, k.open_soc_alerts ? "warn" : "good"),
      metric("Purple Team", k.purple_team_tests, `${d.purple_team.detected} detected · ${d.purple_team.missed} missed`, "info")
    );
    metrics.querySelectorAll(".metric").forEach((card) => {
      const label = card.querySelector(".k")?.textContent;
      if (label) card.dataset.dashboardMetric = label;
    });

    const riskBody = el("div", { id: "dashRiskBody" },
      riskHas
        ? el("div", { class: "risk-hero" }, gauge(d.risk.score, d.risk.level),
            el("div", { style: { flex: "1" } },
              el("div", { class: "section-title", text: "Severity Distribution" }),
              sevBars(d.risk.severity_distribution)))
        : el("div", { class: "state" }, el("div", { class: "big", text: "NO RECORDED SECURITY FINDINGS" }),
            el("div", { class: "sm", text: d.risk.empty_message || "Create findings to populate risk posture." }))
    );
    const riskPanel = el("div", { class: "panel", id: "dashRiskPanel" },
      el("h3", {}, "Overall Risk Posture"), riskBody
    );

    const recentFindingsBody = el("div", { id: "dashRecentFindingsBody" },
      d.recent_findings.length
        ? el("div", { class: "feed" }, d.recent_findings.map((f) => feedRow("⚠", f.title, `${sevText(f.severity)} · ${f.status} · ${fmtDate(f.created_at)}`, normSev(f.severity), () => ctx.navigate("findings"))))
        : emptyState("No findings yet", "Findings appear here once recorded.")
    );
    const recentFindings = el("div", { class: "panel", id: "dashRecentFindings" },
      el("h3", {}, "⚠ Recent Findings", el("span", { class: "tag", onClick: () => ctx.navigate("findings"), text: "view all", style: { cursor: "pointer", color: "var(--cyan)" } })),
      recentFindingsBody
    );

    const recentSocBody = el("div", { id: "dashRecentSocBody" },
      d.recent_soc_events.length
        ? el("div", { class: "feed" }, d.recent_soc_events.map((e) => feedRow("◉", e.message, `${e.event_type} · ${sevText(e.severity)} · ${fmtDate(e.created_at)}`, normSev(e.severity), () => ctx.navigate("soc"))))
        : emptyState("No SOC events", "Recorded security events appear here.")
    );
    const recentSoc = el("div", { class: "panel", id: "dashRecentSoc" },
      el("h3", {}, "◉ Recent SOC Activity", el("span", { class: "tag", onClick: () => ctx.navigate("soc"), text: "view all", style: { cursor: "pointer", color: "var(--cyan)" } })),
      recentSocBody
    );

    const correlationBody = el("div", { id: "dashCorrelationBody" },
      d.correlation.clusters.length
        ? el("div", { class: "feed" }, d.correlation.clusters.map((cl) =>
            feedRow("⧉", `${cl.category.replace(/_/g, " ")} cluster`, `${cl.event_count} event(s) · max severity ${sevText(cl.max_severity)} · ${cl.assessment || "platform"}`, normSev(cl.max_severity), () => ctx.navigate("soc"))))
        : emptyState("NO CORRELATED ACTIVITY", "Correlation runs on stored SOC events.")
    );
    const correlation = el("div", { class: "panel", id: "dashCorrelation" },
      el("h3", {}, "Event Correlation"), correlationBody
    );

    const activityBody = el("div", { id: "dashRecentActivityBody" },
      d.recent_activity.length
        ? el("div", { class: "feed" }, d.recent_activity.map((a) => feedRow(a.kind === "finding" ? "⚠" : "◉", a.label, `${a.kind.replace("_", " ")} · ${sevText(a.severity)} · ${fmtDate(a.at)}`, normSev(a.severity))))
        : emptyState("No activity yet")
    );
    const activity = el("div", { class: "panel", id: "dashRecentActivity" },
      el("h3", {}, "Recent Activity"), activityBody
    );

    const agents = d.agents || [];
    const agentsBody = el("div", { id: "dashAgentsBody" },
      agents.length
        ? el("div", { class: "feed" }, agents.slice(0, 6).map((a) => feedRow(
            "⬢",
            `${a.name}${a.version ? " v" + a.version : ""}`,
            `${a.agent_key} · ${a.status} · seen ${a.last_seen_seconds_ago != null ? agoLabel(a.last_seen_seconds_ago) : "never"}${a.nmap_available ? " · nmap" : ""}`,
            a.status === "online" ? "low" : a.status === "degraded" ? "medium" : "info",
            () => ctx.navigate("agents"))))
        : emptyState("NO NEXCYR AGENTS", "Cloud Scanner is active. Register an agent to scan from inside a target network.")
    );
    const agentsPanel = el("div", { class: "panel", id: "dashAgentsPanel" },
      el("h3", {}, "⬢ NexCYR Agents",
        el("span", { class: "tag", onClick: () => ctx.navigate("agents"), text: "manage", style: { cursor: "pointer", color: "var(--cyan)" } })),
      agentsBody
    );

    const miniMap = el("div", { class: "panel map-wrap" },
      el("h3", {}, "✦ Cyber Attack Map", el("span", { class: "tag", onClick: () => ctx.navigate("attackmap"), text: "open full map", style: { cursor: "pointer", color: "var(--cyan)" } })),
      el("div", { class: "earth-map-bg", "aria-hidden": "true" }),
      el("canvas", { id: "dashMap", style: { width: "100%", height: "320px", display: "block", borderRadius: "9px", background: "transparent" } })
    );

    const ask = askPanel(ctx, { title: "Ask NexCYR" });

    function renderDashboardAlertButtons() {
      soundToggle.textContent = dashboardPreference(DASHBOARD_SOUND_KEY) ? "🔔 Sound alerts ON" : "🔕 Sound alerts OFF";
      announceToggle.textContent = dashboardPreference(DASHBOARD_ANNOUNCE_KEY) ? "🗣 Speak alerts ON" : "🗣 Speak alerts OFF";
      soundToggle.classList.toggle("primary", dashboardPreference(DASHBOARD_SOUND_KEY));
      announceToggle.classList.toggle("primary", dashboardPreference(DASHBOARD_ANNOUNCE_KEY));
    }
    const soundToggle = el("button", { class: "btn ghost sm", onClick: () => {
      const enabled = !dashboardPreference(DASHBOARD_SOUND_KEY);
      setDashboardPreference(DASHBOARD_SOUND_KEY, enabled);
      if (enabled) primeDashboardAudio();
      renderDashboardAlertButtons();
      toast(enabled ? "Sound alerts enabled" : "Sound alerts disabled",
        enabled ? "New medium, high and critical findings can play a tone." : "No sound will play for new findings.", "info", 2500);
    } });
    const announceToggle = el("button", { class: "btn ghost sm", onClick: () => {
      const enabled = !dashboardPreference(DASHBOARD_ANNOUNCE_KEY);
      setDashboardPreference(DASHBOARD_ANNOUNCE_KEY, enabled);
      renderDashboardAlertButtons();
      if (enabled && !voice.isVoiceEnabled()) {
        toast("Voice output is disabled", "Enable Voice output in Settings to hear dashboard alerts.", "warn");
      } else {
        toast(enabled ? "Spoken alerts enabled" : "Spoken alerts disabled",
          enabled ? "New high/critical findings and SOC alerts can be spoken." : "Dashboard alerts will stay silent.", "info", 2500);
      }
    } });
    const readDashboardButton = el("button", { class: "btn ghost sm", text: "🔊 Read dashboard", onClick: () => {
      if (!voice.isVoiceEnabled()) {
        toast("Voice output is disabled", "Enable Voice output in Settings first.", "warn");
        return;
      }
      voice.speak(dashboardSpeechText(latestDashboardData));
    } });
    renderDashboardAlertButtons();
    const alertControls = el("div", { class: "dash-alert-controls", style: { display: "flex", gap: "6px", flexWrap: "wrap", justifyContent: "flex-end" } },
      soundToggle, announceToggle, readDashboardButton
    );
    c.appendChild(viewHead("Command Center", "Live platform posture · updates every 15 seconds", [alertControls]));

    /* Defer the heavy real-Earth texture until the dashboard has painted. */
    const realEarth = document.querySelector(".liquid-backdrop .earth-backdrop");
    const loadRealEarth = () => {
      if (realEarth) realEarth.classList.add("real-earth");
    };
    // Give the first dashboard paint priority; the decorative remote texture loads afterward.
    window.setTimeout(loadRealEarth, 1600);
    c.appendChild(hero);
    c.appendChild(metrics);
    c.appendChild(el("div", { class: "grid cols-2", style: { marginTop: "16px" } }, riskPanel, miniMap));
    c.appendChild(el("div", { class: "grid cols-2", style: { marginTop: "16px" } }, recentFindings, recentSoc));
    c.appendChild(el("div", { class: "grid cols-2", style: { marginTop: "16px" } }, correlation, activity));
    c.appendChild(el("div", { style: { marginTop: "16px" } }, agentsPanel));
    c.appendChild(el("div", { style: { marginTop: "16px" } }, ask));

    // Mini attack map is intentionally non-blocking: it must not hold up dashboard readiness.
    void (async () => {
      try {
        const mapData = await endpoints.attackMap();
        const canvas = document.getElementById("dashMap");
        if (canvas && mapData.has_data) {
          const am = new AttackMap(canvas, document.getElementById("mapTip"), { onSelect: () => ctx.navigate("attackmap") });
          am.setData(mapData);
        } else if (canvas) {
          canvas.replaceWith(emptyState("NO LINKED SECURITY ACTIVITY", "Link targets → scans → findings → events to populate the map."));
        }
      } catch (_) { /* mini map is optional and never blocks initial display */ }
    })();
  }, "Loading command center…");

  dashboardRefreshTimer = window.setInterval(async () => {
    if (!container.isConnected || window.location.hash !== "#dashboard") {
      window.clearInterval(dashboardRefreshTimer);
      dashboardRefreshTimer = null;
      return;
    }
    if (refreshInFlight || !latestDashboardData) return;
    refreshInFlight = true;
    try {
      const next = await endpoints.dashboard();
      const freshFindings = (next.recent_findings || []).filter((f) => !seenFindingIds.has(f.id));
      const freshEvents = (next.recent_soc_events || []).filter((e) => !seenSocIds.has(e.id));
      (next.recent_findings || []).forEach((f) => seenFindingIds.add(f.id));
      (next.recent_soc_events || []).forEach((e) => seenSocIds.add(e.id));
      latestDashboardData = next;
      updateDashboardSnapshot(next, ctx);

      const findingAlerts = freshFindings.filter((f) => ["critical", "high", "medium"].includes(normSev(f.severity)));
      const eventAlerts = freshEvents.filter((e) =>
        ["critical", "high"].includes(normSev(e.severity)) &&
        !["vulnerability_detected", "finding_recorded", "scan_completed", "scan_failed"].includes((e.event_type || "").toLowerCase())
      );
      if ((findingAlerts.length || eventAlerts.length) && dashboardPreference(DASHBOARD_SOUND_KEY)) {
        playDashboardAlertTone();
      }
      const spokenAlerts = [
        ...findingAlerts.filter((f) => ["critical", "high"].includes(normSev(f.severity)))
          .map((f) => `${normSev(f.severity)} finding: ${f.title}`),
        ...eventAlerts.map((e) => `${normSev(e.severity)} SOC alert: ${e.message}`)
      ].slice(0, 4);
      if (spokenAlerts.length && dashboardPreference(DASHBOARD_ANNOUNCE_KEY) && voice.isVoiceEnabled()) {
        voice.speak("New NexCYR security alert. " + spokenAlerts.join(". "));
      }
    } catch (_) {
      // Keep the last real snapshot visible during a temporary API failure.
    } finally {
      refreshInFlight = false;
    }
  }, 15000);
}

function updateDashboardSnapshot(d, ctx) {
  const c = d.counts || {};
  const values = {
    "Assessments": [c.assessments, "total", "info"],
    "Authorized Targets": [c.authorized_targets, `${c.targets || 0} total · ${c.active_targets || 0} active`, "info"],
    "Scans": [c.scans, "recorded", "info"],
    "Open Findings": [c.open_findings, `${c.findings || 0} total`, c.open_findings ? "warn" : "good"],
    "Critical": [c.critical_findings, "findings", c.critical_findings ? "crit" : "good"],
    "High": [c.high_findings, "findings", c.high_findings ? "crit" : "good"],
    "SOC Alerts": [c.open_soc_alerts, `${c.soc_alerts || 0} total`, c.open_soc_alerts ? "warn" : "good"],
    "Purple Team": [c.purple_team_tests, `${d.purple_team?.detected || 0} detected · ${d.purple_team?.missed || 0} missed`, "info"]
  };
  document.querySelectorAll("#dashMetrics .metric").forEach((card) => {
    const value = values[card.dataset.dashboardMetric || card.querySelector(".k")?.textContent];
    if (!value) return;
    const number = card.querySelector(".v");
    const note = card.querySelector(".n");
    if (number) number.textContent = String(value[0] ?? 0);
    if (note) note.textContent = value[1] || "";
    card.className = `metric ${value[2] || ""}`;
  });

  const riskBody = document.getElementById("dashRiskBody");
  if (riskBody) {
    riskBody.innerHTML = "";
    if (d.risk?.has_data) {
      riskBody.appendChild(el("div", { class: "risk-hero" }, gauge(d.risk.score, d.risk.level),
        el("div", { style: { flex: "1" } },
          el("div", { class: "section-title", text: "Severity Distribution" }),
          sevBars(d.risk.severity_distribution))));
    } else {
      riskBody.appendChild(el("div", { class: "state" },
        el("div", { class: "big", text: "NO RECORDED SECURITY FINDINGS" }),
        el("div", { class: "sm", text: d.risk?.empty_message || "Create findings to populate risk posture." })));
    }
  }
  const findingsBody = document.getElementById("dashRecentFindingsBody");
  if (findingsBody) {
    findingsBody.innerHTML = "";
    findingsBody.appendChild((d.recent_findings || []).length
      ? el("div", { class: "feed" }, d.recent_findings.map((f) =>
          feedRow("⚠", f.title, `${sevText(f.severity)} · ${f.status} · ${fmtDate(f.created_at)}`, normSev(f.severity), () => ctx.navigate("findings"))))
      : emptyState("No findings yet", "Findings appear here once recorded."));
  }
  const socBody = document.getElementById("dashRecentSocBody");
  if (socBody) {
    socBody.innerHTML = "";
    socBody.appendChild((d.recent_soc_events || []).length
      ? el("div", { class: "feed" }, d.recent_soc_events.map((e) =>
          feedRow("◉", e.message, `${e.event_type} · ${sevText(e.severity)} · ${fmtDate(e.created_at)}`, normSev(e.severity), () => ctx.navigate("soc"))))
      : emptyState("No SOC events", "Recorded security events appear here."));
  }
  const correlationBody = document.getElementById("dashCorrelationBody");
  if (correlationBody) {
    correlationBody.innerHTML = "";
    correlationBody.appendChild((d.correlation?.clusters || []).length
      ? el("div", { class: "feed" }, d.correlation.clusters.map((cl) =>
          feedRow("⧉", `${cl.category.replace(/_/g, " ")} cluster`, `${cl.event_count} event(s) · max severity ${sevText(cl.max_severity)} · ${cl.assessment || "platform"}`, normSev(cl.max_severity), () => ctx.navigate("soc"))))
      : emptyState("NO CORRELATED ACTIVITY", "Correlation runs on stored SOC events."));
  }
  const activityBody = document.getElementById("dashRecentActivityBody");
  if (activityBody) {
    activityBody.innerHTML = "";
    activityBody.appendChild((d.recent_activity || []).length
      ? el("div", { class: "feed" }, d.recent_activity.map((a) =>
          feedRow(a.kind === "finding" ? "⚠" : "◉", a.label, `${a.kind.replace("_", " ")} · ${sevText(a.severity)} · ${fmtDate(a.at)}`, normSev(a.severity))))
      : emptyState("No activity yet"));
  }
  const agentsBody = document.getElementById("dashAgentsBody");
  if (agentsBody) {
    agentsBody.innerHTML = "";
    agentsBody.appendChild((d.agents || []).length
      ? el("div", { class: "feed" }, d.agents.slice(0, 6).map((a) => feedRow(
          "⬢", `${a.name}${a.version ? " v" + a.version : ""}`,
          `${a.agent_key} · ${a.status} · seen ${a.last_seen_seconds_ago != null ? agoLabel(a.last_seen_seconds_ago) : "never"}${a.nmap_available ? " · nmap" : ""}`,
          a.status === "online" ? "low" : a.status === "degraded" ? "medium" : "info",
          () => ctx.navigate("agents"))))
      : emptyState("NO NEXCYR AGENTS", "Cloud Scanner is active. Register an agent to scan from inside a target network."));
  }
}

function sevText(s) { return (s || "info").toLowerCase(); }
function metric(label, value, note, cls) {
  return el("div", { class: `metric ${cls || ""}` },
    el("div", { class: "k", text: label }),
    el("div", { class: "v", text: String(value ?? 0) }),
    el("div", { class: "n", text: note || "" }));
}
function feedRow(icon, title, meta, sev, onClick) {
  const colors = { critical: "#ff2d55", high: "#ff7a18", medium: "#f5c518", low: "#38bdf8", info: "#8b98a5" };
  return el("div", { class: "row", style: onClick ? { cursor: "pointer" } : null, onClick: onClick || null },
    el("div", { class: "ico", style: { color: colors[sev] || "#8ea0bb", borderColor: colors[sev] || "var(--line)" }, text: icon }),
    el("div", { class: "body" }, el("div", { class: "t", text: title }), el("div", { class: "m", text: meta })));
}

// ------------------------------------------------------------------
// VIEW: Assessments
// ------------------------------------------------------------------
async function assessmentsView(container, ctx) {
  await withLoading(container, async (c) => {
    async function reload() {
      const rows = await endpoints.assessments();
      const tbl = table(
        [
          { key: "id", label: "ID", render: (r) => el("span", { class: "mono", text: "#" + r.id }) },
          { key: "name", label: "Name" },
          { key: "assessment_type", label: "Type" },
          { key: "status", label: "Status", render: (r) => statusBadge(r.status) },
          { key: "risk_level", label: "Risk", render: (r) => badge(r.risk_level || "unknown", riskLevelClass(r.risk_level)) },
          { key: "risk_score", label: "Score", render: (r) => el("span", { class: "mono", text: String(r.risk_score ?? 0) }) },
          { key: "stats", label: "Targets/Scans/Findings", render: (r) => el("span", { class: "mono muted", text: `${r.stats?.targets ?? 0} / ${r.stats?.scans ?? 0} / ${r.stats?.findings ?? 0}` }) },
          { key: "created_at", label: "Created", render: (r) => el("span", { class: "muted", text: fmtDate(r.created_at) }) },
                    { label: "Actions", render: (r) => el("div", { class: "row-actions" },
              el("button", { class: "btn ghost sm", text: "Edit", onClick: () => form(r) }),
              el("button", { class: "btn danger sm", text: "Delete", onClick: () => del(r) })) },
        ],
        rows
      );
      listHost.innerHTML = "";
      listHost.appendChild(rows.length ? tbl : emptyState("No assessments", "Create your first assessment to begin."));
    }

    function form(existing) {
      const f = el("form", {},
        field("Name", input("name", { value: existing?.name || "", required: "true", placeholder: "e.g. Q3 External Perimeter" })),
        el("div", { class: "field-row" },
          field("Type", select("assessment_type", [["general", "General"], ["internal", "Internal"], ["external", "External"], ["web", "Web Application"], ["wireless", "Wireless"], ["purple_team", "Purple Team"]], { }),
          ),
          field("Status", select("status", [["created", "Created"], ["planning", "Planning"], ["running", "Running"], ["review", "Review"], ["completed", "Completed"], ["archived", "Archived"]]))
        ),
        field("Description", textarea("description", { placeholder: "Scope, objectives, authorization notes…" }), "Free text."),
      );
      if (existing) { f.querySelector('[name="assessment_type"]').value = existing.assessment_type || "general"; f.querySelector('[name="status"]').value = existing.status || "created"; f.querySelector('[name="description"]').value = existing.description || ""; }
      const save = el("button", { class: "btn primary", text: existing ? "Save changes" : "Create assessment" });
      save.addEventListener("click", async () => {
        const body = readForm(f, { optionalEmpty: ["description"] });
        if (!body.name) { toast("Name required", "", "warn"); return; }
        try {
          if (existing) await endpoints.updateAssessment(existing.id, body);
          else await endpoints.createAssessment(body);
          closeModal(); toast(existing ? "Assessment updated" : "Assessment created", "", "ok"); reload(); ctx.refreshAiChip?.();
        } catch (e) { toast("Save failed", e.message, "err"); }
      });
      openModal(existing ? `Edit assessment #${existing.id}` : "New assessment", f, [el("button", { class: "btn ghost", text: "Cancel", onClick: closeModal }), save]);
    }

    function del(r) {
      confirmModal("Delete assessment", `Delete "${r.name}" and all linked targets, scans and findings? This cannot be undone.`, async () => {
        try { await endpoints.deleteAssessment(r.id); toast("Assessment deleted", "", "ok"); reload(); }
        catch (e) { toast("Delete failed", e.message, "err"); }
      }, "Delete");
    }

    const listHost = el("div", {});
    c.appendChild(viewHead("Assessments", "Engagement containers for targets, scans and findings",
      [el("button", { class: "btn primary", text: "+ New assessment", onClick: () => form(null) })]));
    c.appendChild(el("div", { class: "panel" }, listHost));
    await reload();
  });
}

// ------------------------------------------------------------------
// VIEW: Targets
// ------------------------------------------------------------------
async function targetsView(container, ctx) {
  await withLoading(container, async (c) => {
    async function reload() {
      const rows = await endpoints.targets();
      const tbl = table(
        [
          { key: "id", label: "ID", render: (r) => el("span", { class: "mono", text: "#" + r.id }) },
          { key: "name", label: "Name", render: (r) => r.name || el("span", { class: "muted", text: "—" }) },
          { key: "target_type", label: "Type", render: (r) => badge(r.target_type, "neutral") },
          { key: "value", label: "Value", render: (r) => el("span", { class: "mono", text: r.value }) },
          { key: "authorized", label: "Authorized", render: (r) => r.authorized ? badge("authorized", "ok") : badge("not authorized", "critical") },
          { key: "status", label: "Status", render: (r) => statusBadge(r.status) },
          { key: "assessment_id", label: "Assessment", render: (r) => r.assessment_id ? el("span", { class: "mono muted", text: "#" + r.assessment_id }) : el("span", { class: "muted", text: "—" }) },
          { label: "Actions", render: (r) => el("div", { class: "row-actions" },
              !r.authorized
                ? el("button", { class: "btn primary sm", text: "Authorize", title: "Authorize this target for scanning and reconnaissance", onClick: () => authorize(r) })
                : el("button", { class: "btn ghost sm", text: "Authorized", title: "Scanning authorization is enabled", onClick: () => revokeAuthorization(r) }),
              el("button", { class: "btn ghost sm", text: "Edit", onClick: () => form(r) }),
              el("button", { class: "btn danger sm", text: "Delete", onClick: () => del(r) })) },
        ],
        rows
      );
      listHost.innerHTML = "";
      listHost.appendChild(rows.length ? tbl : emptyState("No targets yet", "Choose + Add target / IP, enter an IP address in the target-value field, and keep authorization set to Not authorized until permission is confirmed."));
    }

    async function form(existing) {
      const aOpts = await assessmentOptions();
      let agents = [];
      try { agents = await endpoints.agents(); } catch (_) {}
      const agentOpts = [["", "Cloud Scanner (default)"]]
        .concat(agents.map((a) => [String(a.id), `${a.name} (${a.status})`]));
      const targetTypes = [["ip", "IP address"], ["domain", "Domain"], ["url", "URL"], ["host", "Hostname"], ["network", "CIDR network"]];
      const targetType = select("target_type", targetTypes);
      const targetValue = input("value", { value: existing?.value || "", required: "true", placeholder: "192.0.2.10", autocomplete: "off" });
      const authorization = select("authorized", [
        ["false", "Not authorized — scanning blocked"],
        ["true", "Authorized — I have permission"],
      ]);
      const updateValueHint = () => {
        const hints = {
          ip: "192.0.2.10 or 2001:db8::10",
          domain: "example.com",
          url: "https://example.com",
          host: "server-01",
          network: "192.0.2.0/24 (up to 256 addresses)",
        };
        targetValue.placeholder = hints[targetType.value] || "Enter one target value";
      };
      targetType.addEventListener("change", updateValueHint);

      const f = el("form", {},
        field("Name", input("name", { value: existing?.name || "", placeholder: "e.g. Web server" })),
        field("Target type", targetType),
        field("IP address / domain / hostname / URL / CIDR", targetValue,
          "Enter the exact IP or target in this field. Only one target is stored; no scan runs automatically."),
        el("div", { class: "field-row" },
          field("Assessment", select("assessment_id", aOpts)),
          field("Status", select("status", [["active", "Active"], ["inactive", "Inactive"], ["retired", "Retired"]]))
        ),
        field("Authorization status", authorization,
          "Not authorized is the safe default. Nmap and reconnaissance remain blocked until authorization is explicitly confirmed."),
        field("Preferred scanner", select("preferred_agent_id", agentOpts),
          "Where scans of this target run from. Agents must be online and capable when a scan is routed."),
        field("Notes", textarea("notes", { placeholder: "Owner, authorization reference, approved testing window…" }))
      );
      if (existing) {
        targetType.value = existing.target_type;
        f.querySelector('[name="status"]').value = existing.status || "active";
        f.querySelector('[name="assessment_id"]').value = existing.assessment_id != null ? String(existing.assessment_id) : "";
        f.querySelector('[name="preferred_agent_id"]').value = existing.preferred_agent_id != null ? String(existing.preferred_agent_id) : "";
        f.querySelector('[name="notes"]').value = existing.notes || "";
      }
      authorization.value = String(Boolean(existing?.authorized));
      updateValueHint();

      const save = el("button", { class: "btn primary", type: "button", text: existing ? "Save changes" : "Add target" });
      save.addEventListener("click", async () => {
        if (!f.reportValidity()) return;
        const body = readForm(f, { numbers: ["assessment_id", "preferred_agent_id"], optionalEmpty: ["name", "notes"] });
        body.authorized = body.authorized === "true";
        try {
          if (existing) await endpoints.updateTarget(existing.id, body);
          else await endpoints.createTarget(body);
          closeModal();
          toast(existing ? "Target updated" : "Target added", body.authorized ? "Authorized target saved; no scan was started." : "Saved as not authorized. Scanning remains blocked.", body.authorized ? "ok" : "warn");
          reload();
        } catch (e) { toast("Save failed", e.message, "err"); }
      });
      openModal(existing ? `Edit target #${existing.id}` : "New target", f, [el("button", { class: "btn ghost", type: "button", text: "Cancel", onClick: closeModal }), save]);
    }

    function authorize(r) {
      confirmModal(
        "Authorize target",
        `I confirm "${r.value}" is explicitly authorized for scanning and reconnaissance.`,
        async () => {
          try {
            await endpoints.updateTarget(r.id, { authorized: true });
            toast("Target authorized", `${r.value} can now be used for scans and recon.`, "ok");
            reload();
          } catch (e) { toast("Authorization failed", e.message, "err"); }
        },
        "Authorize"
      );
    }

    function revokeAuthorization(r) {
      confirmModal(
        "Revoke authorization",
        `Remove scanning authorization from "${r.value}"?`,
        async () => {
          try {
            await endpoints.updateTarget(r.id, { authorized: false });
            toast("Authorization revoked", "", "ok");
            reload();
          } catch (e) { toast("Could not revoke authorization", e.message, "err"); }
        },
        "Revoke"
      );
    }

    function del(r) {
      confirmModal("Delete target", `Delete target "${r.value}"? Linked scans/findings referencing it may be affected.`, async () => {
        try { await endpoints.deleteTarget(r.id); toast("Target deleted", "", "ok"); reload(); }
        catch (e) { toast("Delete failed", e.message, "err"); }
      }, "Delete");
    }

    const listHost = el("div", {});
    c.appendChild(viewHead("Targets", "Enter an IP or target value; scans run only for explicitly authorized targets",
      [el("button", { class: "btn primary", text: "+ Add target / IP", type: "button", onClick: () => form(null) })]));
    c.appendChild(el("div", { class: "panel" }, listHost));
    await reload();
  });
}

// ------------------------------------------------------------------
// VIEW: Scans
// ------------------------------------------------------------------
async function scansView(container, ctx) {
  await withLoading(container, async (c) => {
    async function reload() {
      const [rows, summary] = await Promise.all([endpoints.scans(), endpoints.scanSummary()]);
      sumHost.innerHTML = "";
      sumHost.appendChild(el("div", { class: "grid cols-4" },
        metric("Total Scans", summary.total_scans, "", "info"),
        metric("Completed", summary.by_status?.completed || 0, "", "good"),
        metric("Nmap", summary.nmap_available ? "available" : "unavailable", summary.nmap_available ? "engine ready" : "NMAP_UNAVAILABLE", summary.nmap_available ? "good" : "warn"),
        metric("Findings from scans", summary.findings_from_scans, `risk ${summary.overall_risk_level} (${summary.overall_risk_score})`, riskLevelClass(summary.overall_risk_level)),
      ));
      const tbl = table(
        [
          { key: "id", label: "ID", render: (r) => el("span", { class: "mono", text: "#" + r.id }) },
          { key: "target_value", label: "Target", render: (r) => el("span", { class: "mono", text: r.target_value || "—" }) },
          { key: "scan_type", label: "Type", render: (r) => badge(r.scan_type, "neutral") },
          { key: "status", label: "Status", render: (r) => statusBadge(r.status) },
          { key: "execution_source", label: "Source", render: (r) => r.execution_source === "AGENT"
              ? badge((r.agent_name || "agent") + (r.agent_version ? " v" + r.agent_version : ""), "ok")
              : badge("cloud scanner", "neutral") },
          { key: "result_summary", label: "Summary", render: (r) => el("span", { class: "muted", text: r.result_summary || "—" }) },
          { key: "created_at", label: "Created", render: (r) => el("span", { class: "muted", text: fmtDate(r.created_at) }) },
          { label: "Actions", render: (r) => el("div", { class: "row-actions" },
              el("button", { class: "btn ghost sm", text: "Results", onClick: () => showResults(r) }),
              el("button", { class: "btn danger sm", text: "Delete", onClick: () => del(r) })) },
        ],
        rows
      );
      listHost.innerHTML = "";
      listHost.appendChild(rows.length ? tbl : emptyState("No scans", "Create a scan against an authorized target."));
    }

    async function form() {
      const authorized = await authorizedTargetOptions();
      let agents = [];
      try { agents = await endpoints.agents(); } catch (_) {}
      const online = agents.filter((a) => a.status === "online");
      const locOpts = [["", "Cloud Scanner (built-in)"]]
        .concat(online.map((a) => [String(a.id), `NexCYR Agent · ${a.name}${a.version ? " v" + a.version : ""}`]));
      const locHint = online.length
        ? "Network targets use Nmap host discovery through the selected Agent. Service/stealth profiles also use the Agent."
        : "Cloud TCP port profile is available for host targets. Network discovery and Nmap service/stealth profiles require an online NexCYR Agent.";

      const targetSelect = select("target_id", [
        ["", authorized.length ? "— Select a saved target or enter one below —" : "— Enter a target below —"],
        ...authorized,
      ]);
      const quickType = select("quick_target_type", [["ip", "IP address"], ["domain", "Domain"], ["host", "Hostname"], ["network", "CIDR network"]]);
      const quickValue = input("quick_target_value", { placeholder: "192.0.2.10", autocomplete: "off" });
      const quickAuthorization = select("quick_target_authorized", [
        ["false", "Not authorized — save only, no scan"],
        ["true", "Authorized — I have permission"],
      ]);
      quickType.addEventListener("change", () => {
        const hints = {
          ip: "192.0.2.10 or 2001:db8::10",
          domain: "example.com",
          host: "server-01",
          network: "192.0.2.0/24 (up to 256 addresses)",
        };
        quickValue.placeholder = hints[quickType.value] || "Enter one target value";
      });

      const quickAdd = el("button", { class: "btn ghost", type: "button", text: "Save target only" });
      quickAdd.addEventListener("click", async () => {
        const value = quickValue.value.trim();
        if (!value) {
          toast("Target value required", "Enter the IP address, hostname, domain or CIDR first.", "warn");
          quickValue.focus();
          return;
        }
        quickAdd.disabled = true;
        quickAdd.textContent = "Saving…";
        const authorizedChoice = quickAuthorization.value === "true";
        try {
          const created = await endpoints.createTarget({
            name: value,
            target_type: quickType.value,
            value,
            authorized: authorizedChoice,
            status: "active",
          });
          quickValue.value = "";
          if (created.authorized) {
            const refreshed = await authorizedTargetOptions();
            targetSelect.replaceChildren(
              el("option", { value: "", text: "— Select one authorized target —" }),
              ...refreshed.map(([optionValue, label]) => el("option", { value: optionValue, text: label }))
            );
            targetSelect.value = String(created.id);
            toast("Authorized target saved", "It is selected now. Press Run scan only when you are ready.", "ok");
          } else {
            toast("Target saved as not authorized", "No scan was started. Confirm permission before authorizing it in Targets.", "warn");
          }
        } catch (e) {
          toast("Target save failed", e.message, "err");
        } finally {
          quickAdd.disabled = false;
          quickAdd.textContent = "Save target only";
        }
      });

      const quickTargetBox = el("div", { class: "quick-target-box" },
        el("div", { class: "section-title", text: "New target / IP" }),
        el("div", { class: "muted", style: { fontSize: "11px", lineHeight: "1.5", marginBottom: "10px" },
          text: "Enter one target here. To scan it now, choose “Authorized — I have permission” and click Run scan. NexCYR will save it and start the scan. Save target only stores it without scanning." }),
        el("div", { class: "field-row" },
          field("Target type", quickType),
          field("IP address / hostname / domain / CIDR", quickValue)
        ),
        field("Authorization status", quickAuthorization),
        el("div", { class: "quick-target-actions" }, quickAdd)
      );

      const f = el("form", {},
        field("Saved target (optional)", targetSelect,
          authorized.length ? "Select a saved authorized target, or enter a new target below and confirm permission to scan it." : "You do not need to create a target first. Enter one below and explicitly confirm permission; Run scan will save it and start scanning."),
        quickTargetBox,
        el("div", { class: "field-row", style: { marginTop: "14px" } },
          field("Scan type", select("scan_type", [["service", "Nmap service / version"], ["basic", "Cloud TCP port profile"], ["stealth", "Stealth Nmap (Agent only)"]])),
          field("Assessment", select("assessment_id", await assessmentOptions()))
        ),
        field("Scan location", select("agent_id", locOpts), locHint)
      );
      const run = el("button", { class: "btn primary", type: "button", text: "Run scan" });
      run.addEventListener("click", async () => {
        const body = readForm(f, { numbers: ["target_id", "assessment_id", "agent_id"] });
        delete body.quick_target_type;
        delete body.quick_target_value;
        delete body.quick_target_authorized;
        const inlineValue = quickValue.value.trim();
        const needsInlineTarget = !body.target_id;
        if (needsInlineTarget && !inlineValue) {
          toast("Target required", "Select a saved authorized target or enter an IP address / host below.", "warn");
          quickValue.focus();
          return;
        }
        if (needsInlineTarget && quickAuthorization.value !== "true") {
          toast("Authorization required", "Choose “Authorized — I have permission” only for a target you own or are approved to test. No scan has started.", "warn");
          quickAuthorization.focus();
          return;
        }
        if (!body.agent_id) delete body.agent_id;
        run.disabled = true; run.textContent = "Scanning…";
        let inlineTarget = null;
        try {
          if (needsInlineTarget) {
            inlineTarget = await endpoints.createTarget({
              name: inlineValue,
              target_type: quickType.value,
              value: inlineValue,
              authorized: true,
              status: "active",
              assessment_id: body.assessment_id || null,
            });
            body.target_id = inlineTarget.id;
            targetSelect.replaceChildren(
              el("option", { value: "", text: "— Select one authorized target —" }),
              ...(await authorizedTargetOptions()).map(([optionValue, label]) => el("option", { value: optionValue, text: label }))
            );
            targetSelect.value = String(inlineTarget.id);
            quickValue.value = "";
          }
          const res = await endpoints.createScan(body);
          closeModal();
          const via = res.execution_source === "AGENT" ? `via ${res.agent_name || "agent"}` : (res.status === "queued" ? "queued for agent" : "via Cloud Scanner");
          toast("Scan " + res.status, `${res.result_summary || via}`, res.status === "completed" ? "ok" : "warn");
          reload();
        } catch (e) {
          toast(inlineTarget ? "Target saved; scan failed" : "Scan failed",
            inlineTarget ? `${inlineTarget.value} was saved as authorized. ${e.message}` : e.message, "err");
        }
        finally { run.disabled = false; run.textContent = "Run scan"; }
      });
      openModal("New scan", f, [
        el("button", { class: "btn ghost", type: "button", text: "Cancel", onClick: closeModal }),
        run
      ]);
    }

    async function showResults(r) {
      const body = el("div", {}, loadingState("Fetching results…"));
      openModal(`Scan #${r.id} results`, body, [el("button", { class: "btn ghost", text: "Close", onClick: closeModal })]);
      try {
        const res = await endpoints.scanResults(r.id);
        const scan = res.scan;
        body.innerHTML = "";
        body.appendChild(el("div", { class: "kv-list" },
          kv("Target", scan.target_value || "—"),
          kv("Type", scan.scan_type),
          kv("Status", scan.status),
          kv("Source", scan.execution_source === "AGENT"
            ? `NexCYR Agent · ${scan.agent_name || "—"}${scan.agent_version ? " v" + scan.agent_version : ""}`
            : "Cloud Scanner"),
          kv("Started", fmtDate(scan.started_at)),
          kv("Completed", fmtDate(scan.completed_at)),
          scan.error ? kv("Error", scan.error) : null,
        ));
        if (scan.result_summary) body.appendChild(el("p", { class: "muted", style: { margin: "12px 0" }, text: scan.result_summary }));
        const services = (scan.result_data && scan.result_data.services) || [];
        const openPorts = (scan.result_data && scan.result_data.open_ports) || [];
        const hosts = (scan.result_data && scan.result_data.hosts) || [];

        if (hosts.length) {
          body.appendChild(el("div", { class: "section-title", style: { marginTop: "14px" }, text: "Live devices / hosts (" + hosts.length + ")" }));
          body.appendChild(table(
            [
              { key: "address", label: "IP / Address", render: (x) => el("span", { class: "mono", text: x.address || "—" }) },
              { key: "hostname", label: "Hostname", render: (x) => el("span", { class: "muted", text: x.hostname || "—" }) },
              { key: "state", label: "State", render: () => badge("up", "ok") },
            ],
            hosts
          ));
        }

        if (scan.scan_type === "basic" && !hosts.length) {
          body.appendChild(el("div", { class: "section-title", style: { marginTop: "14px" }, text: "Open ports (" + openPorts.length + ")" }));
          body.appendChild(openPorts.length
            ? table(
                [{ key: "port", label: "Port", render: (x) => el("span", { class: "mono", text: String(x.port) }) },
                 { key: "state", label: "State", render: () => badge("open", "ok") }],
                openPorts.map((port) => ({ port }))
              )
            : emptyState("No open ports", "No TCP connections were observed in the fixed NexCYR common-port profile."));
        } else if (!hosts.length) {
          body.appendChild(el("div", { class: "section-title", style: { marginTop: "14px" }, text: "Detected services (" + services.length + ")" }));
          body.appendChild(services.length
            ? table([{ key: "port", label: "Port" }, { key: "state", label: "State" }, { key: "service", label: "Service" }, { key: "version", label: "Version", render: (x) => el("span", { class: "muted", text: x.version || "—" }) }], services)
            : emptyState("No services", scan.status === "nmap_unavailable" ? "Nmap unavailable — route this profile to a NexCYR Agent." : scan.status === "agent_required" ? "This profile requires an online NexCYR Agent." : "Nothing detected."));
        }
        const fnds = res.findings || [];
        body.appendChild(el("div", { class: "section-title", style: { marginTop: "16px" }, text: `Findings generated (${fnds.length})` }));
        body.appendChild(fnds.length
          ? el("div", { class: "feed" }, fnds.map((x) => feedRow("⚠", x.title, `${sevText(x.severity)} · risk ${x.risk_score ?? 0}`, normSev(x.severity))))
          : emptyState("No findings", "No risk-worthy services were derived."));
      } catch (e) {
        body.innerHTML = ""; body.appendChild(emptyState("Error", e.message));
      }
    }

    function del(r) {
      confirmModal("Delete scan", `Delete scan #${r.id}?`, async () => {
        try { await endpoints.deleteScan(r.id); toast("Scan deleted", "", "ok"); reload(); }
        catch (e) { toast("Delete failed", e.message, "err"); }
      }, "Delete");
    }

    const sumHost = el("div", { style: { marginBottom: "16px" } });
    const listHost = el("div", {});
    c.appendChild(viewHead("Scans", "Safe authorized scanning — Nmap where available, never fabricated",
      [el("button", { class: "btn primary", text: "+ New scan", onClick: form })]));
    c.appendChild(sumHost);
    c.appendChild(el("div", { class: "panel" }, listHost));
    await reload();
  }, "Loading scans…");
}

// ------------------------------------------------------------------
// VIEW: Recon
// ------------------------------------------------------------------
async function reconView(container, ctx) {
  await withLoading(container, async (c) => {
    async function reload() {
      const rows = await endpoints.recon();
      const tbl = table(
        [
          { key: "id", label: "ID", render: (r) => el("span", { class: "mono", text: "#" + r.id }) },
          { key: "value", label: "Target", render: (r) => el("span", { class: "mono", text: r.value }) },
          { key: "recon_type", label: "Type", render: (r) => badge((r.recon_type || "").replace(/_/g, " "), "neutral") },
          { key: "status", label: "Status", render: (r) => statusBadge(r.status) },
          { key: "created_at", label: "Created", render: (r) => el("span", { class: "muted", text: fmtDate(r.created_at) }) },
          { label: "Actions", render: (r) => el("button", { class: "btn ghost sm", text: "View", onClick: () => show(r) }) },
        ],
        rows
      );
      listHost.innerHTML = "";
      listHost.appendChild(rows.length ? tbl : emptyState("No recon results", "Run host/port/service discovery against an authorized target."));
    }

    async function form() {
      const tOpts = await authorizedTargetOptions();
      const f = el("form", {},
        field("Authorized target", select("target_id", [["", tOpts.length ? "— Select one authorized target —" : "No authorized targets"], ...tOpts])),
        el("div", { class: "field-row" },
          field("Recon type", select("recon_type", [["host_discovery", "Host discovery"], ["port_discovery", "Port discovery"], ["service_enumeration", "Service enumeration"]])),
          field("Assessment", select("assessment_id", await assessmentOptions()))
        )
      );
      const run = el("button", { class: "btn primary", text: "Run recon" });
      run.addEventListener("click", async () => {
        const body = readForm(f, { numbers: ["target_id", "assessment_id"] });
        if (!body.target_id) { toast("No authorized target", "", "warn"); return; }
        run.disabled = true; run.textContent = "Running…";
        try {
          const res = await endpoints.createRecon(body);
          closeModal(); toast("Recon " + res.status, `${res.recon_type} on ${res.value}`, res.status === "completed" ? "ok" : "warn"); reload();
        } catch (e) { toast("Recon failed", e.message, "err"); }
        finally { run.disabled = false; run.textContent = "Run recon"; }
      });
      openModal("New authorized reconnaissance", f, [el("button", { class: "btn ghost", text: "Cancel", onClick: closeModal }), run]);
    }

    function show(r) {
      const body = el("div", {});
      body.appendChild(el("div", { class: "kv-list" },
        kv("Target", r.value), kv("Type", r.recon_type), kv("Status", r.status), kv("Created", fmtDate(r.created_at))));
      body.appendChild(el("div", { class: "section-title", style: { marginTop: "14px" }, text: "Result data" }));
      body.appendChild(el("div", { class: "pre", text: r.result ? JSON.stringify(r.result, null, 2) : "(no structured data)" }));
      openModal(`Recon #${r.id}`, body, [el("button", { class: "btn ghost", text: "Close", onClick: closeModal })]);
    }

    const listHost = el("div", {});
    c.appendChild(viewHead("Reconnaissance", "Safe authorized host / port / service discovery",
      [el("button", { class: "btn primary", text: "+ New recon", onClick: form })]));
    c.appendChild(el("div", { class: "panel" }, listHost));
    await reload();
  }, "Loading recon…");
}

// ------------------------------------------------------------------
// VIEW: Findings
// ------------------------------------------------------------------
async function findingsView(container, ctx) {
  await withLoading(container, async (c) => {
    let filter = "all";

    async function reload() {
      const rows = await endpoints.findings();
      const shown = filter === "all" ? rows : rows.filter((r) => normSev(r.severity) === filter);
      const tabs = el("div", { class: "pill-tabs" },
        ["all", ...SEVERITY_ORDER].map((s) => el("button", { class: filter === s ? "active" : "", text: s === "all" ? `All (${rows.length})` : `${s} (${rows.filter((r) => normSev(r.severity) === s).length})`, onClick: () => { filter = s; reload(); } })));
      const tbl = table(
        [
          { key: "id", label: "ID", render: (r) => el("span", { class: "mono", text: "#" + r.id }) },
          { key: "title", label: "Title" },
          { key: "severity", label: "Severity", render: (r) => sevBadge(r.severity) },
          { key: "status", label: "Status", render: (r) => statusBadge(r.status) },
          { key: "risk_score", label: "Risk", render: (r) => el("span", { class: "mono", text: String(r.risk_score ?? 0) }) },
          { key: "created_at", label: "Created", render: (r) => el("span", { class: "muted", text: fmtDate(r.created_at) }) },
          { label: "Actions", render: (r) => el("div", { class: "row-actions" },
              el("button", { class: "btn ghost sm", text: "View", onClick: () => show(r) }),
              el("button", { class: "btn ghost sm", text: "Ask AI", onClick: () => askAbout(r) }),
              el("button", { class: "btn ghost sm", text: "Edit", onClick: () => form(r) }),
              el("button", { class: "btn danger sm", text: "Delete", onClick: () => del(r) })) },
        ],
        shown
      );
      listHost.innerHTML = "";
      listHost.appendChild(tabs);
      listHost.appendChild(shown.length ? tbl : emptyState("No findings", filter === "all" ? "Record a finding or run a scan." : `No ${filter} findings.`));
    }

    async function form(existing) {
      const aOpts = await assessmentOptions();
      const tOpts = [["", "— none —"]].concat((await endpoints.targets()).map((t) => [String(t.id), t.name || t.value]));
      const f = el("form", {},
        field("Title", input("title", { value: existing?.title || "", required: "true", placeholder: "e.g. Exposed SMB service" })),
        el("div", { class: "field-row" },
          field("Severity", select("severity", [["critical", "Critical"], ["high", "High"], ["medium", "Medium"], ["low", "Low"], ["info", "Info"]])),
          field("Status", select("status", [["open", "Open"], ["in_progress", "In progress"], ["resolved", "Resolved"], ["accepted", "Accepted"], ["closed", "Closed"]]))
        ),
        el("div", { class: "field-row" },
          field("Assessment", select("assessment_id", aOpts)),
          field("Target", select("target_id", tOpts))
        ),
        field("Description", textarea("description")),
        field("Evidence", textarea("evidence", { placeholder: "Command output, screenshots reference, banner…" })),
        field("Remediation", textarea("remediation", { placeholder: "Recommended fix…" })),
      );
      if (existing) {
        f.querySelector('[name="severity"]').value = normSev(existing.severity);
        f.querySelector('[name="status"]').value = existing.status || "open";
        f.querySelector('[name="assessment_id"]').value = existing.assessment_id != null ? String(existing.assessment_id) : "";
        f.querySelector('[name="target_id"]').value = existing.target_id != null ? String(existing.target_id) : "";
        ["description", "evidence", "remediation"].forEach((k) => { f.querySelector(`[name="${k}"]`).value = existing[k] || ""; });
      }
      const save = el("button", { class: "btn primary", text: existing ? "Save changes" : "Create finding" });
      save.addEventListener("click", async () => {
        const body = readForm(f, { numbers: ["assessment_id", "target_id"], optionalEmpty: ["description", "evidence", "remediation"] });
        if (!body.title) { toast("Title required", "", "warn"); return; }
        try {
          if (existing) await endpoints.updateFinding(existing.id, body);
          else await endpoints.createFinding(body);
          closeModal(); toast(existing ? "Finding updated" : "Finding created", "Risk engine recalculated", "ok"); reload();
        } catch (e) { toast("Save failed", e.message, "err"); }
      });
      openModal(existing ? `Edit finding #${existing.id}` : "New finding", f, [el("button", { class: "btn ghost", text: "Cancel", onClick: closeModal }), save]);
    }

    async function show(r) {
      const full = await endpoints.finding(r.id).catch(() => r);
      const body = el("div", {},
        el("div", { style: { display: "flex", gap: "8px", marginBottom: "12px" } }, sevBadge(full.severity), statusBadge(full.status), badge("risk " + (full.risk_score ?? 0), riskLevelClass(full.risk_level))),
        el("div", { class: "kv-list" },
          kv("Assessment", full.assessment_id ? "#" + full.assessment_id : "—"),
          kv("Target", full.target_id ? "#" + full.target_id : "—"),
          kv("Scan", full.scan_id ? "#" + full.scan_id : "—"),
          kv("Risk level", full.risk_level || "—"),
          kv("Confidence", full.confidence || "—"),
          kv("Created", fmtDate(full.created_at)),
        ),
        section("Description", full.description),
        section("Evidence", full.evidence),
        section("Remediation", full.remediation),
        full.risk_factors ? section("Risk factors", Array.isArray(full.risk_factors) ? full.risk_factors.join("\n") : full.risk_factors) : null,
        full.recommendations ? section("Recommendations", Array.isArray(full.recommendations) ? full.recommendations.join("\n") : full.recommendations) : null,
      );
      openModal(`Finding #${full.id} — ${full.title}`, body,
        [el("button", { class: "btn ghost", text: "Ask NexCYR", onClick: () => { closeModal(); askAbout(full); } }),
         el("button", { class: "btn primary", text: "Close", onClick: closeModal })]);
    }

    function askAbout(r) {
      const body = el("div", {}, askPanel(ctx, { contextType: "finding", contextId: r.id, title: `Ask about finding #${r.id}` }));
      openModal(`NexCYR Intelligence — ${r.title}`, body, [el("button", { class: "btn primary", text: "Done", onClick: closeModal })]);
    }

    function del(r) {
      confirmModal("Delete finding", `Delete finding "${r.title}"?`, async () => {
        try { await endpoints.deleteFinding(r.id); toast("Finding deleted", "", "ok"); reload(); }
        catch (e) { toast("Delete failed", e.message, "err"); }
      }, "Delete");
    }

    const listHost = el("div", {});
    c.appendChild(viewHead("Findings", "Risk-engine scored security findings",
      [el("button", { class: "btn primary", text: "+ New finding", onClick: () => form(null) })]));
    c.appendChild(el("div", { class: "panel" }, listHost));
    await reload();
  }, "Loading findings…");
}

function section(title, text) {
  if (!text) return null;
  return el("div", { style: { marginTop: "14px" } },
    el("div", { class: "section-title", text: title }),
    el("div", { class: "pre", text: String(text) }));
}
function kv(k, v) { return el("div", { class: "kv" }, el("div", { class: "k", text: k }), el("div", { class: "v", text: String(v ?? "—") })); }

// ------------------------------------------------------------------
// VIEW: SOC Monitoring
// ------------------------------------------------------------------
async function socView(container, ctx) {
  await withLoading(container, async (c) => {
    async function reload() {
      const [rows, summary, corr] = await Promise.all([endpoints.socEvents(), endpoints.socSummary(), endpoints.socCorrelation()]);
      sumHost.innerHTML = "";
      sumHost.appendChild(el("div", { class: "grid cols-4" },
        metric("Total Events", summary.total, "", "info"),
        metric("Open", summary.open, "", summary.open ? "warn" : "good"),
        metric("Critical", summary.critical, "", summary.critical ? "crit" : "good"),
        metric("High", summary.high, "", summary.high ? "crit" : "good"),
      ));

      corrHost.innerHTML = "";
      corrHost.appendChild(el("div", { class: "panel" },
        el("h3", {}, "⧉ Event Correlation", el("span", { class: "tag", text: `${corr.total_events} event(s) · ${corr.window_hours}h window` })),
        corr.clusters.length
          ? el("div", { class: "feed" }, corr.clusters.map((cl) => feedRow("⧉", cl.category.replace(/_/g, " ") + " cluster",
              `${cl.event_count} event(s) · max ${sevText(cl.max_severity)} · ${cl.open_count ?? 0} open · ${cl.assessment || "platform"}`, normSev(cl.max_severity))))
          : emptyState("NO CORRELATED ACTIVITY", "Correlation derives from stored SOC events only.")));

      const tbl = table(
        [
          { key: "id", label: "ID", render: (r) => el("span", { class: "mono", text: "#" + r.id }) },
          { key: "event_type", label: "Type", render: (r) => badge(r.event_type, "neutral") },
          { key: "source", label: "Source", render: (r) => el("span", { class: "muted", text: r.source }) },
          { key: "message", label: "Message", render: (r) => el("span", { text: (r.message || "").slice(0, 70) + ((r.message || "").length > 70 ? "…" : "") }) },
          { key: "severity", label: "Severity", render: (r) => sevBadge(r.severity) },
          { key: "status", label: "Status", render: (r) => statusBadge(r.status) },
          { key: "created_at", label: "Created", render: (r) => el("span", { class: "muted", text: fmtDate(r.created_at) }) },
          { label: "Actions", render: (r) => el("div", { class: "row-actions" },
              el("button", { class: "btn ghost sm", text: "Edit", onClick: () => form(r) }),
              el("button", { class: "btn danger sm", text: "Delete", onClick: () => del(r) })) },
        ],
        rows
      );
      listHost.innerHTML = "";
      listHost.appendChild(rows.length ? tbl : emptyState("No SOC events", "Record a security event to begin monitoring."));
    }

    async function form(existing) {
      const aOpts = await assessmentOptions();
      const tOpts = [["", "— none —"]].concat((await endpoints.targets()).map((t) => [String(t.id), t.name || t.value]));
      const f = el("form", {},
        el("div", { class: "field-row" },
          field("Event type", input("event_type", { value: existing?.event_type || "", required: "true", placeholder: "authentication / network_scanning / malware" })),
          field("Source", input("source", { value: existing?.source || "", required: "true", placeholder: "e.g. firewall-01" }))
        ),
        field("Message", textarea("message", { required: "true", placeholder: "What was observed…" })),
        el("div", { class: "field-row" },
          field("Severity", select("severity", [["critical", "Critical"], ["high", "High"], ["medium", "Medium"], ["low", "Low"], ["info", "Info"]])),
          field("Status", select("status", [["open", "Open"], ["investigating", "Investigating"], ["contained", "Contained"], ["resolved", "Resolved"], ["closed", "Closed"]]))
        ),
        el("div", { class: "field-row" },
          field("Assessment", select("assessment_id", aOpts)),
          field("Target", select("target_id", tOpts))
        ),
        el("div", { class: "field-row" },
          field("Source IP", input("source_ip", { value: existing?.source_ip || "" })),
          field("Destination IP", input("destination_ip", { value: existing?.destination_ip || "" }))
        ),
        field("Detected by", input("detected_by", { value: existing?.detected_by || "", placeholder: "e.g. correlation-engine" })),
      );
      if (existing) {
        f.querySelector('[name="severity"]').value = normSev(existing.severity);
        f.querySelector('[name="status"]').value = existing.status || "open";
        f.querySelector('[name="assessment_id"]').value = existing.assessment_id != null ? String(existing.assessment_id) : "";
        f.querySelector('[name="target_id"]').value = existing.target_id != null ? String(existing.target_id) : "";
        f.querySelector('[name="message"]').value = existing.message || "";
      }
      const save = el("button", { class: "btn primary", text: existing ? "Save changes" : "Create event" });
      save.addEventListener("click", async () => {
        const body = readForm(f, { numbers: ["assessment_id", "target_id"], optionalEmpty: ["source_ip", "destination_ip", "detected_by"] });
        if (!body.event_type || !body.source || !body.message) { toast("Type, source and message are required", "", "warn"); return; }
        try {
          if (existing) await endpoints.updateSocEvent(existing.id, body);
          else await endpoints.createSocEvent(body);
          closeModal(); toast(existing ? "Event updated" : "SOC event created", "", "ok"); reload();
        } catch (e) { toast("Save failed", e.message, "err"); }
      });
      openModal(existing ? `Edit SOC event #${existing.id}` : "New SOC event", f, [el("button", { class: "btn ghost", text: "Cancel", onClick: closeModal }), save]);
    }

    function del(r) {
      confirmModal("Delete event", `Delete SOC event #${r.id}?`, async () => {
        try { await endpoints.deleteSocEvent(r.id); toast("Event deleted", "", "ok"); reload(); }
        catch (e) { toast("Delete failed", e.message, "err"); }
      }, "Delete");
    }

    const sumHost = el("div", { style: { marginBottom: "16px" } });
    const corrHost = el("div", { style: { marginBottom: "16px" } });
    const listHost = el("div", {});
    c.appendChild(viewHead("SOC Monitoring", "Stored security events + rule-based correlation",
      [el("button", { class: "btn primary", text: "+ New event", onClick: () => form(null) })]));
    c.appendChild(sumHost);
    c.appendChild(corrHost);
    c.appendChild(el("div", { class: "panel" }, listHost));
    await reload();
  }, "Loading SOC…");
}

// ------------------------------------------------------------------
// VIEW: Cyber Attack Map
// ------------------------------------------------------------------
async function attackMapView(container, ctx) {
  await withLoading(container, async (c) => {
    const data = await endpoints.attackMap();
    const typeFilters = new Set(Object.keys(MAP_TYPE_LABEL));
    const sevFilters = new Set(["critical", "high", "medium", "low", "info", "none"]);

    const detail = el("div", { class: "map-node-detail", id: "mapDetail" });
    const canvas = el("canvas", { id: "attackMap" });
    const legend = el("div", { class: "map-legend" },
      Object.entries(MAP_TYPE_LABEL).map(([t, label]) =>
        el("span", { class: "lg" }, el("i", { style: { background: MAP_TYPE_COLOR[t], boxShadow: `0 0 8px ${MAP_TYPE_COLOR[t]}` } }), label)));

    const typeRow = el("div", { class: "map-filters" }, Object.entries(MAP_TYPE_LABEL).map(([t, label]) => {
      const b = el("button", { class: "btn sm", text: label });
      b.classList.add("primary");
      b.addEventListener("click", () => {
        if (typeFilters.has(t)) { typeFilters.delete(t); b.classList.remove("primary"); }
        else { typeFilters.add(t); b.classList.add("primary"); }
        am.setTypeFilter([...typeFilters]);
      });
      return b;
    }));

    const sevRow = el("div", { class: "map-filters" }, ["critical", "high", "medium", "low", "info"].map((s) => {
      const b = el("button", { class: "btn sm", text: s });
      b.classList.add("primary");
      b.addEventListener("click", () => {
        if (sevFilters.has(s)) { sevFilters.delete(s); b.classList.remove("primary"); }
        else { sevFilters.add(s); b.classList.add("primary"); }
        am.setSevFilter([...sevFilters]);
      });
      return b;
    }));

    c.appendChild(viewHead("Cyber Attack Map", "Target → Scan → Finding → SOC Event → Purple Team, from stored relationships only"));
    c.appendChild(el("div", { class: "panel" },
      legend,
      el("div", { class: "section-title", text: "Entity type" }), typeRow,
      el("div", { class: "section-title", text: "Severity" }), sevRow,
      data.has_data
        ? el("div", { class: "map-wrap" },
            el("div", { class: "earth-map-bg", "aria-hidden": "true" }),
            canvas,
            detail)
        : emptyState("NO LINKED SECURITY ACTIVITY", "Create linked targets, scans, findings and events to build the graph.")
    ));

    if (data.has_data) {
      const am = new AttackMap(canvas, document.getElementById("mapTip"), {
        onSelect: (n) => {
          if (!n) { detail.classList.remove("open"); return; }
          detail.innerHTML = "";
          detail.appendChild(el("h4", { text: (MAP_TYPE_LABEL[n.type] || n.type) + " — " + (n.label || "") }));
          detail.appendChild(el("div", { class: "kv", html: `<b>Status:</b> ${n.status || "—"}` }));
          if (n.severity) detail.appendChild(el("div", { class: "kv", html: `<b>Severity:</b> ${n.severity}` }));
          Object.entries(n.meta || {}).forEach(([k, v]) => {
            detail.appendChild(el("div", { class: "kv", html: `<b>${k}:</b> ${String(v ?? "—")}` }));
          });
          detail.appendChild(el("div", { style: { marginTop: "10px", display: "flex", gap: "6px" } },
            el("button", { class: "btn ghost sm", text: "Close", onClick: () => detail.classList.remove("open") })));
          detail.classList.add("open");
        },
      });
      am.setData(data);
    }
  }, "Building attack map…");
}

// ------------------------------------------------------------------
// VIEW: Purple Team
// ------------------------------------------------------------------
async function purpleView(container, ctx) {
  await withLoading(container, async (c) => {
    async function reload() {
      const rows = await endpoints.purple();
      const tbl = table(
        [
          { key: "id", label: "ID", render: (r) => el("span", { class: "mono", text: "#" + r.id }) },
          { key: "name", label: "Test" },
          { key: "technique", label: "Technique", render: (r) => el("span", { class: "muted", text: r.technique || "—" }) },
          { key: "status", label: "Status", render: (r) => statusBadge(r.status) },
          { key: "detection_status", label: "Detection", render: (r) => statusBadge(r.detection_status) },
          { key: "created_at", label: "Created", render: (r) => el("span", { class: "muted", text: fmtDate(r.created_at) }) },
          { label: "Actions", render: (r) => el("div", { class: "row-actions" },
              el("button", { class: "btn ghost sm", text: "View", onClick: () => show(r) }),
              el("button", { class: "btn ghost sm", text: "Edit", onClick: () => form(r) }),
              el("button", { class: "btn danger sm", text: "Delete", onClick: () => del(r) })) },
        ],
        rows
      );
      listHost.innerHTML = "";
      listHost.appendChild(rows.length ? tbl : emptyState("No purple team tests", "Record a safe detection-validation test."));
    }

    async function form(existing) {
      const aOpts = await assessmentOptions();
      const tOpts = [["", "— none —"]].concat((await endpoints.targets()).map((t) => [String(t.id), t.name || t.value]));
      const fOpts = [["", "— none —"]].concat((await endpoints.findings()).map((x) => [String(x.id), `#${x.id} ${x.title}`]));
      const f = el("form", {},
        field("Name", input("name", { value: existing?.name || "", required: "true", placeholder: "e.g. Brute-force detection validation" })),
        el("div", { class: "field-row" },
          field("Technique", input("technique", { value: existing?.technique || "", placeholder: "e.g. T1110 Brute Force" })),
          field("Status", select("status", [["planned", "Planned"], ["in_progress", "In progress"], ["executed", "Executed"], ["completed", "Completed"], ["cancelled", "Cancelled"]]))
        ),
        field("Objective", textarea("objective", { placeholder: "What detection capability is being validated…" })),
        field("Detection status", select("detection_status", [["pending", "Pending"], ["detected", "Detected"], ["missed", "Missed"], ["partial", "Partial"]])),
        el("div", { class: "field-row" },
          field("Assessment", select("assessment_id", aOpts)),
          field("Target", select("target_id", tOpts))
        ),
        field("Linked finding", select("finding_id", fOpts)),
        field("Notes / Evidence", textarea("notes")),
      );
      if (existing) {
        f.querySelector('[name="technique"]').value = existing.technique || "";
        f.querySelector('[name="status"]').value = existing.status || "planned";
        f.querySelector('[name="detection_status"]').value = existing.detection_status || "pending";
        f.querySelector('[name="objective"]').value = existing.objective || "";
        f.querySelector('[name="notes"]').value = existing.notes || "";
        f.querySelector('[name="assessment_id"]').value = existing.assessment_id != null ? String(existing.assessment_id) : "";
        f.querySelector('[name="target_id"]').value = existing.target_id != null ? String(existing.target_id) : "";
        f.querySelector('[name="finding_id"]').value = existing.finding_id != null ? String(existing.finding_id) : "";
      }
      const save = el("button", { class: "btn primary", text: existing ? "Save changes" : "Create test" });
      save.addEventListener("click", async () => {
        const body = readForm(f, { numbers: ["assessment_id", "target_id", "finding_id"], optionalEmpty: ["technique", "objective", "notes"] });
        if (!body.name) { toast("Name required", "", "warn"); return; }
        try {
          if (existing) await endpoints.updatePurple(existing.id, body);
          else await endpoints.createPurple(body);
          closeModal(); toast(existing ? "Test updated" : "Test created", "", "ok"); reload();
        } catch (e) { toast("Save failed", e.message, "err"); }
      });
      openModal(existing ? `Edit test #${existing.id}` : "New purple team test", f, [el("button", { class: "btn ghost", text: "Cancel", onClick: closeModal }), save]);
    }

    function show(r) {
      const body = el("div", {},
        el("div", { style: { display: "flex", gap: "8px", marginBottom: "12px" } }, statusBadge(r.status), statusBadge(r.detection_status)),
        el("div", { class: "kv-list" },
          kv("Technique", r.technique || "—"),
          kv("Objective", r.objective || "—"),
          kv("Assessment", r.assessment_id ? "#" + r.assessment_id : "—"),
          kv("Target", r.target_label || (r.target_id ? "#" + r.target_id : "—")),
          kv("Finding", r.finding_id ? "#" + r.finding_id : "—"),
          kv("Created", fmtDate(r.created_at)),
        ),
        section("Notes / Evidence", r.notes),
        r.recommendation ? section("Recommendation", r.recommendation) : null,
      );
      openModal(`Purple Team — ${r.name}`, body, [el("button", { class: "btn primary", text: "Close", onClick: closeModal })]);
    }

    function del(r) {
      confirmModal("Delete test", `Delete purple team test "${r.name}"?`, async () => {
        try { await endpoints.deletePurple(r.id); toast("Test deleted", "", "ok"); reload(); }
        catch (e) { toast("Delete failed", e.message, "err"); }
      }, "Delete");
    }

    const listHost = el("div", {});
    c.appendChild(viewHead("Purple Team", "Safe simulation & detection-validation records",
      [el("button", { class: "btn primary", text: "+ New test", onClick: () => form(null) })]));
    c.appendChild(el("div", { class: "panel" }, listHost));
    await reload();
  }, "Loading purple team…");
}

// ------------------------------------------------------------------
// VIEW: Wi-Fi Security
// ------------------------------------------------------------------
async function wifiView(container, ctx) {
  await withLoading(container, async (c) => {
    async function reload() {
      const [rows, sensor] = await Promise.all([endpoints.wifi(), endpoints.wifiSensor()]);
      sensorHost.innerHTML = "";
      sensorHost.appendChild(el("div", { class: "panel" },
        el("h3", {}, "📶 Sensor Status"),
        el("div", { class: "kv-list" },
          kv("Sensor", sensor.sensor_status),
          kv("Source", sensor.source || "CLOUD"),
          kv("Agent", sensor.agent_name || "—"),
          kv("Interface", sensor.interface || "—"),
          kv("Current SSID", sensor.current_ssid || "—"),
          kv("Local network", sensor.local_network || "—"),
          kv("Visible networks", Array.isArray(sensor.networks) ? sensor.networks.length : 0),
          kv("Detail", sensor.reason || "—")),
        Array.isArray(sensor.networks) && sensor.networks.length
          ? table(
              [
                { key: "ssid", label: "SSID" },
                { key: "authentication", label: "Authentication", render: (n) => badge(n.authentication || "Unknown", wifiSecClass(n.authentication)) },
                { key: "encryption", label: "Encryption", render: (n) => el("span", { class: "muted", text: n.encryption || "—" }) },
                { key: "channel", label: "Channel", render: (n) => el("span", { class: "mono", text: n.channel || "—" }) },
                { key: "signal", label: "Signal", render: (n) => el("span", { class: "mono", text: n.signal || "—" }) },
                { key: "bssid", label: "BSSID", render: (n) => el("span", { class: "mono muted", text: n.bssid || "—" }) },
              ],
              sensor.networks.slice(0, 50)
            )
          : null));
      const tbl = table(
        [
          { key: "id", label: "ID", render: (r) => el("span", { class: "mono", text: "#" + r.id }) },
          { key: "ssid", label: "SSID" },
          { key: "security_type", label: "Security", render: (r) => badge(r.security_type || "unknown", wifiSecClass(r.security_type)) },
          { key: "channel", label: "Channel", render: (r) => el("span", { class: "mono", text: r.channel || "—" }) },
          { key: "status", label: "Status", render: (r) => statusBadge(r.status) },
          { key: "created_at", label: "Created", render: (r) => el("span", { class: "muted", text: fmtDate(r.created_at) }) },
          { label: "Actions", render: (r) => el("div", { class: "row-actions" },
              el("button", { class: "btn ghost sm", text: "Discover", onClick: () => discover(r) }),
              el("button", { class: "btn ghost sm", text: "Edit", onClick: () => form(r) }),
              el("button", { class: "btn danger sm", text: "Delete", onClick: () => del(r) })) },
        ],
        rows
      );
      listHost.innerHTML = "";
      listHost.appendChild(rows.length ? tbl : emptyState("No Wi-Fi assessments", "Add a network and run passive discovery."));
    }

    function wifiSecClass(s) {
      const v = (s || "").toUpperCase();
      if (v.includes("WPA3")) return "ok";
      if (v.includes("WPA2")) return "low";
      if (v.includes("WPA") || v.includes("WEP")) return "warn";
      if (v.includes("OPEN")) return "critical";
      return "neutral";
    }

    function form(existing) {
      const f = el("form", {},
        field("SSID / Network name", input("ssid", { value: existing?.ssid || "", required: "true", placeholder: "e.g. CorpGuest" })),
        el("div", { class: "field-row" },
          field("Security type", select("security_type", [["WPA3", "WPA3"], ["WPA2", "WPA2"], ["WPA", "WPA"], ["WEP", "WEP"], ["Open", "Open"], ["Unknown", "Unknown"]])),
          field("Channel", input("channel", { value: existing?.channel || "", placeholder: "e.g. 6" }))
        ),
        field("Status", select("status", [["created", "Created"], ["in_progress", "In progress"], ["completed", "Completed"]])),
        field("Assessment notes", textarea("assessment", { placeholder: "Configuration review, weaknesses…" })),
        field("Notes", textarea("notes")),
      );
      if (existing) {
        f.querySelector('[name="security_type"]').value = existing.security_type || "Unknown";
        f.querySelector('[name="status"]').value = existing.status || "created";
        f.querySelector('[name="assessment"]').value = existing.assessment || "";
        f.querySelector('[name="notes"]').value = existing.notes || "";
      }
      const save = el("button", { class: "btn primary", text: existing ? "Save changes" : "Add assessment" });
      save.addEventListener("click", async () => {
        const body = readForm(f, { optionalEmpty: ["channel", "assessment", "notes"] });
        if (!body.ssid) { toast("SSID required", "", "warn"); return; }
        try {
          if (existing) await endpoints.updateWifi(existing.id, body);
          else await endpoints.createWifi(body);
          closeModal(); toast(existing ? "Wi-Fi updated" : "Wi-Fi assessment added", "", "ok"); reload();
        } catch (e) { toast("Save failed", e.message, "err"); }
      });
      openModal(existing ? `Edit Wi-Fi #${existing.id}` : "New Wi-Fi assessment", f, [el("button", { class: "btn ghost", text: "Cancel", onClick: closeModal }), save]);
    }

    async function discover(r) {
      toast("Running passive discovery…", "This uses local Wi-Fi scanning only.", "info", 2500);
      try {
        const res = await endpoints.discoverWifi(r.id);
        toast("Discovery " + (res.status || "done"), res.security_summary || "", "ok");
        reload();
      } catch (e) { toast("Discovery failed", e.message, "err"); }
    }

    function del(r) {
      confirmModal("Delete Wi-Fi assessment", `Delete "${r.ssid}"?`, async () => {
        try { await endpoints.deleteWifi(r.id); toast("Deleted", "", "ok"); reload(); }
        catch (e) { toast("Delete failed", e.message, "err"); }
      }, "Delete");
    }

    const sensorHost = el("div", { style: { marginBottom: "16px" } });
    const listHost = el("div", {});
    c.appendChild(viewHead("Wi-Fi Security", "Configuration assessment + passive network discovery",
      [el("button", { class: "btn primary", text: "+ Add network", onClick: () => form(null) })]));
    c.appendChild(sensorHost);
    c.appendChild(el("div", { class: "panel" }, listHost));
    await reload();
  }, "Loading Wi-Fi…");
}

// ------------------------------------------------------------------
// VIEW: NexCYR Intelligence (Ask NexCYR)
// ------------------------------------------------------------------
async function aiView(container, ctx) {
  await withLoading(container, async (c) => {
    const status = await endpoints.aiStatus();
    const panel = askPanel(ctx, { title: "Ask NexCYR", tall: true });
    c.appendChild(viewHead("NexCYR Intelligence", "Contextual cybersecurity assistant grounded in stored platform data"));
    c.appendChild(el("div", { class: "panel" },
      el("h3", {}, "Engine Status"),
      el("div", { class: "kv-list" },
        kv("Engine", status.engine || "—"),
        kv("Provider", status.provider || "—"),
        kv("Model", status.model || "—"),
        kv("External configured", status.external_provider_configured ? "yes" : "no"),
        kv("Fallback", status.fallback_engine || "—"),
      ),
      el("p", { class: "muted", style: { marginTop: "10px", fontSize: "12px" }, text: "NexCYR remains fully functional without an external AI key via the Fallback Engine, which answers from the real database." })
    ));
    c.appendChild(panel);

    // context shortcuts
    try {
      const [findings, assessments] = await Promise.all([endpoints.findings(), endpoints.assessments()]);
      const shortcuts = el("div", { class: "panel" }, el("h3", {}, "Context shortcuts"));
      const chips = el("div", { class: "ask" }, el("div", { class: "quick" }));
      const quick = chips.querySelector(".quick");
      findings.slice(0, 8).forEach((f) => quick.appendChild(el("button", { text: `Finding #${f.id}: ${f.title}`, onClick: () => openContext("finding", f.id, f.title) })));
      assessments.slice(0, 8).forEach((a) => quick.appendChild(el("button", { text: `Assessment: ${a.name}`, onClick: () => openContext("assessment", a.id, a.name) })));
      shortcuts.appendChild(chips);
      c.appendChild(shortcuts);
    } catch (_) {}

    function openContext(type, id, label) {
      const body = el("div", {}, askPanel(ctx, { contextType: type, contextId: id, title: label, tall: true }));
      openModal(`NexCYR Intelligence — ${label}`, body, [el("button", { class: "btn primary", text: "Done", onClick: closeModal })]);
    }
  }, "Loading intelligence…");
}

// ------------------------------------------------------------------
// VIEW: Reports
// ------------------------------------------------------------------
async function reportsView(container, ctx) {
  await withLoading(container, async (c) => {
    async function reload() {
      const rows = await endpoints.reports();
      const tbl = table(
        [
          { key: "id", label: "ID", render: (r) => el("span", { class: "mono", text: "#" + r.id }) },
          { key: "report_name", label: "Report" },
          { key: "assessment_id", label: "Assessment", render: (r) => r.assessment_id ? "#" + r.assessment_id : "Platform-wide" },
          { key: "risk_level", label: "Risk", render: (r) => badge(r.risk_level || "unknown", riskLevelClass(r.risk_level)) },
          { key: "status", label: "Status", render: (r) => statusBadge(r.status) },
          { key: "created_at", label: "Generated", render: (r) => el("span", { class: "muted", text: fmtDate(r.created_at) }) },
          { label: "Actions", render: (r) => el("div", { class: "row-actions" },
              el("a", { class: "btn ghost sm", text: "Download", href: r.download_url, target: "_blank" }),
              el("button", { class: "btn danger sm", text: "Delete", onClick: () => del(r) })) },
        ],
        rows
      );
      listHost.innerHTML = "";
      listHost.appendChild(rows.length ? tbl : emptyState("No reports", "Generate a professional PDF assessment report."));
    }

    async function generate() {
      const aOpts = await assessmentOptions();
      const f = el("form", {},
        field("Scope", select("assessment_id", [["", "Platform-wide (all assessments)"]].concat(aOpts.filter(([v]) => v))),
          "The PDF is built from real stored data — findings, scans, SOC, correlation, purple team and Wi-Fi.")
      );
      const go = el("button", { class: "btn primary", text: "Generate PDF" });
      go.addEventListener("click", async () => {
        const body = readForm(f, { numbers: ["assessment_id"] });
        go.disabled = true; go.textContent = "Generating…";
        try {
          const res = await endpoints.createReport(body);
          closeModal(); toast("Report generated", res.report_name, "ok"); reload();
          // offer direct download of freshly generated PDF
          window.open(endpoints.pdfUrl(body.assessment_id ?? undefined), "_blank");
        } catch (e) { toast("Generation failed", e.message, "err"); }
        finally { go.disabled = false; go.textContent = "Generate PDF"; }
      });
      openModal("Generate security report", f, [el("button", { class: "btn ghost", text: "Cancel", onClick: closeModal }), go]);
    }

    function del(r) {
      confirmModal("Delete report", `Delete report record #${r.id}?`, async () => {
        try { await endpoints.deleteReport(r.id); reload(); toast("Report deleted", "", "ok"); }
        catch (e) { toast("Delete failed", e.message, "err"); }
      }, "Delete");
    }

    const listHost = el("div", {});
    c.appendChild(viewHead("Reports", "Professional ReportLab PDF assessment reports",
      [el("button", { class: "btn ghost", text: "⬇ Download PDF now", onClick: () => window.open(endpoints.pdfUrl(), "_blank") }),
       el("button", { class: "btn primary", text: "+ Generate report", onClick: generate })]));
    c.appendChild(el("div", { class: "panel" }, listHost));
    await reload();
  }, "Loading reports…");
}

// ------------------------------------------------------------------
// VIEW: Settings
// ------------------------------------------------------------------
async function settingsView(container, ctx) {
  await withLoading(container, async (c) => {
    const s = await endpoints.settings();
    const f = el("form", {},
      el("div", { class: "section-title", text: "Platform" }),
      el("div", { class: "field-row" },
        field("Platform name", input("platform_name", { value: s.platform.platform_name || "NexCYR" })),
        field("Environment", select("environment", [["local", "local"], ["staging", "staging"], ["production", "production"]]))
      ),
      el("div", { class: "section-title", style: { marginTop: "18px" }, text: "Analysis" }),
      el("div", { class: "field-row" },
        el("div", { class: "field" }, checkbox("ai_enabled", s.ai.ai_enabled, " AI enabled")),
        el("div", { class: "field" }, checkbox("automatic_analysis", s.ai.automatic_analysis, " Automatic analysis"))
      ),
      el("div", { class: "field-row" },
        el("div", { class: "field" }, checkbox("soc_event_analysis", s.ai.soc_event_analysis, " SOC event analysis")),
        el("div", { class: "field" }, checkbox("finding_analysis", s.ai.finding_analysis, " Finding analysis"))
      ),
      el("div", { class: "field" }, checkbox("purple_team_analysis", s.ai.purple_team_analysis, " Purple team analysis")),
      el("div", { class: "section-title", style: { marginTop: "18px" }, text: "AI Voice" }),
      el("div", { class: "field-row" },
        el("div", { class: "field" }, checkbox("voice_enabled", s.voice.voice_enabled, " Voice output enabled")),
        field("Voice language", input("voice_language", { value: s.voice.voice_language || "en-US", placeholder: "en-US" }))
      ),
      el("div", { class: "field-row" },
        field("Voice rate", input("voice_rate", { type: "number", step: "0.1", min: "0.5", max: "2", value: s.voice.voice_rate ?? 1 })),
        field("Voice volume", input("voice_volume", { type: "number", step: "0.1", min: "0", max: "1", value: s.voice.voice_volume ?? 1 }))
      ),
      el("div", { class: "field-row" },
        el("div", { class: "field" }, checkbox("speak_critical_alerts", s.voice.speak_critical_alerts, " Speak critical alerts")),
        el("div", { class: "field" }, checkbox("speak_high_alerts", s.voice.speak_high_alerts, " Speak high alerts"))
      ),
      el("div", { class: "field" }, checkbox("speak_medium_alerts", s.voice.speak_medium_alerts, " Speak medium alerts")),
    );
    f.querySelector('[name="environment"]').value = s.platform.environment || "local";

    const runtime = el("div", { class: "panel" },
      el("h3", {}, "AI Runtime"),
      el("div", { class: "kv-list" },
        kv("Engine", s.ai_runtime.engine || "—"),
        kv("Provider", s.ai_runtime.provider || "—"),
        kv("Model", s.ai_runtime.model || "—"),
        kv("External configured", s.ai_runtime.external_provider_configured ? "yes" : "no"),
      ));

    const save = el("button", { class: "btn primary", text: "Save settings" });
    save.addEventListener("click", async () => {
      const body = readForm(f, {
        bools: ["ai_enabled", "automatic_analysis", "soc_event_analysis", "finding_analysis", "purple_team_analysis", "voice_enabled", "speak_critical_alerts", "speak_high_alerts", "speak_medium_alerts"],
      });
      body.voice_rate = Number(body.voice_rate);
      body.voice_volume = Number(body.voice_volume);
      try {
        const updated = await endpoints.updateSettings(body);
        voice.configureVoice(updated.voice);
        toast("Settings saved", "", "ok");
        ctx.refreshAiChip?.();
      } catch (e) { toast("Save failed", e.message, "err"); }
    });

    c.appendChild(viewHead("Settings", "Platform, analysis and voice configuration", [save]));
    c.appendChild(el("div", { class: "grid cols-2" },
      el("div", { class: "panel" }, el("h3", {}, "Configuration"), f),
      runtime));
  }, "Loading settings…");
}

// ------------------------------------------------------------------
// VIEW: NexCYR Agents (Hybrid Cloud)
// ------------------------------------------------------------------
function agentStatusBadge(s) {
  const v = (s || "").toLowerCase();
  const map = {
    online: "ok", degraded: "warn", offline: "neutral",
    enrolled: "info", disabled: "warn", revoked: "critical",
  };
  return badge(v || "unknown", map[v] || "neutral");
}

function agoLabel(secs) {
  if (secs === null || secs === undefined) return "never";
  const n = Number(secs);
  if (n < 60) return `${n}s ago`;
  if (n < 3600) return `${Math.floor(n / 60)}m ago`;
  if (n < 86400) return `${Math.floor(n / 3600)}h ago`;
  return `${Math.floor(n / 86400)}d ago`;
}

const JOB_TYPE_OPTIONS = [
  ["NMAP_HOST_DISCOVERY", "NMAP_HOST_DISCOVERY — host discovery"],
  ["NMAP_PORT_SCAN", "NMAP_PORT_SCAN — port scan"],
  ["NMAP_SERVICE_ENUMERATION", "NMAP_SERVICE_ENUMERATION — service enumeration"],
  ["AUTHORIZED_RECON", "AUTHORIZED_RECON — authorized recon"],
];

async function agentsView(container, ctx) {
  await withLoading(container, async (c) => {
    const sumHost = el("div", { style: { marginBottom: "16px" } });
    const listHost = el("div", {});

    async function reload() {
      const rows = await endpoints.agents();
      const online = rows.filter((a) => a.status === "online").length;
      const degraded = rows.filter((a) => a.status === "degraded").length;
      const offline = rows.filter((a) => ["offline", "enrolled"].includes(a.status)).length;
      sumHost.innerHTML = "";
      sumHost.appendChild(el("div", { class: "grid cols-4" },
        metric("Agents", rows.length, "registered", "info"),
        metric("Online", online, "recent heartbeat", online ? "good" : "warn"),
        metric("Degraded", degraded, "stale heartbeat", degraded ? "warn" : "good"),
        metric("Offline / Enrolled", offline, "no recent heartbeat", "info"),
      ));

      const tbl = table(
        [
          { key: "id", label: "ID", render: (r) => el("span", { class: "mono", text: "#" + r.id }) },
          { key: "name", label: "Agent", render: (r) => el("div", {}, el("div", { text: r.name }), el("div", { class: "mono muted", style: { fontSize: "11px" }, text: r.agent_key })) },
          { key: "status", label: "Status", render: (r) => agentStatusBadge(r.status) },
          { key: "platform", label: "Platform", render: (r) => el("span", { class: "muted", text: r.platform ? `${r.platform}${r.arch ? " · " + r.arch : ""}` : "—" }) },
          { key: "version", label: "Version", render: (r) => el("span", { class: "mono muted", text: r.version || "—" }) },
          { key: "nmap", label: "Nmap", render: (r) => r.nmap_available ? badge("available", "ok") : badge("no", "neutral") },
          { key: "last_seen_seconds_ago", label: "Last seen", render: (r) => el("span", { class: "muted", text: agoLabel(r.last_seen_seconds_ago) }) },
          { label: "Actions", render: (r) => el("div", { class: "row-actions" },
              el("button", { class: "btn ghost sm", text: "View", onClick: () => showAgent(r) }),
              el("button", { class: "btn ghost sm", text: "Capabilities", onClick: () => showCaps(r) }),
              el("button", { class: "btn ghost sm", text: "Health", onClick: () => showHealth(r) }),
              el("button", { class: "btn ghost sm", text: "Assign scan", onClick: () => assignScan(r) }),
              el("button", { class: "btn ghost sm", text: "Jobs", onClick: () => showJobs(r) }),
              el("button", { class: "btn ghost sm", text: r.enabled ? "Disable" : "Enable", onClick: () => toggleEnabled(r) }),
              el("button", { class: "btn danger sm", text: "Revoke", onClick: () => revoke(r) })) },
        ],
        rows
      );
      listHost.innerHTML = "";
      listHost.appendChild(rows.length ? tbl : emptyState("No NexCYR Agents", "Register an agent to run authorized scans from inside a target network. Cloud scanning remains available without agents."));
    }

    function registerForm() {
      const f = el("form", {},
        field("Agent name", input("name", { required: "true", placeholder: "e.g. NexCYR Agent 01" })),
        field("Agent key", input("agent_key", { placeholder: "optional — unique identifier (auto-generated if blank)" })),
        field("Assigned scope", textarea("assigned_scope", { placeholder: "Authorized network scope this agent may operate within…" })),
        el("p", { class: "muted", style: { fontSize: "12px", marginTop: "8px" }, text: "Enrollment issues a one-time credential. It is shown once and stored only as a hash — never again retrievable." })
      );
      const create = el("button", { class: "btn primary", text: "Create enrollment" });
      create.addEventListener("click", async () => {
        const body = readForm(f, { optionalEmpty: ["agent_key", "assigned_scope"] });
        if (!body.name) { toast("Name required", "", "warn"); return; }
        create.disabled = true;
        try {
          const res = await endpoints.enrollAgent(body);
          showEnrollmentToken(res);
          reload();
        } catch (e) { toast("Enrollment failed", e.message, "err"); }
        finally { create.disabled = false; }
      });
      openModal("Register NexCYR Agent", f, [el("button", { class: "btn ghost", text: "Cancel", onClick: closeModal }), create]);
    }

    function showEnrollmentToken(res) {
      const server = window.location.origin.replace(/\/$/, "");
      const token = String(res.enrollment_token || "");
      const command = `$env:NEXCYR_NMAP_PATH="D:\\NexCYR\\NexCYR\\nmap.exe"; .\\.venv\\Scripts\\python.exe agent\\nexcyr_agent.py --server "${server}" --token "${token}"`;
      const tokenBox = el("div", { class: "pre", style: { wordBreak: "break-all", whiteSpace: "pre-wrap" }, text: token });
      const commandBox = el("div", { class: "pre", style: { wordBreak: "break-all", whiteSpace: "pre-wrap", marginTop: "8px", fontSize: "11px" }, text: command });
      const body = el("div", {},
        el("div", { class: "state", style: { textAlign: "left" } },
          el("div", { class: "big", text: "ENROLLMENT CREATED" }),
          el("div", { class: "sm", text: `${res.name} · ${res.agent_key}` })),
        el("div", { class: "section-title", style: { marginTop: "14px" }, text: "One-time agent credential" }),
        tokenBox,
        el("div", { class: "section-title", style: { marginTop: "14px" }, text: "Connect this Agent to this exact server" }),
        el("div", { class: "muted", style: { fontSize: "12px" }, text: server }),
        commandBox,
        el("p", { class: "muted", style: { fontSize: "12px", marginTop: "8px", color: "var(--warn, #f5c518)" }, text: "Important: a token created on localhost:8001 works only with localhost:8001. A token created on Railway works only with that Railway URL. Do not mix them." })
      );
      const copyToken = el("button", { class: "btn ghost", text: "Copy token", onClick: async () => {
        try { await navigator.clipboard.writeText(token); toast("Token copied", "", "ok", 2000); }
        catch (_) { toast("Copy blocked", "Select and copy manually", "warn"); }
      } });
      const copyCommand = el("button", { class: "btn primary", text: "Copy Agent command", onClick: async () => {
        try { await navigator.clipboard.writeText(command); toast("Agent command copied", "Paste it into PowerShell on the Agent PC.", "ok", 2500); }
        catch (_) { toast("Copy blocked", "Select the command manually", "warn"); }
      } });
      openModal("Agent enrollment credential", body, [el("button", { class: "btn ghost", text: "Done", onClick: closeModal }), copyToken, copyCommand]);
    }

    function showAgent(r) {
      const body = el("div", {},
        el("div", { style: { display: "flex", gap: "8px", marginBottom: "12px" } }, agentStatusBadge(r.status), r.enabled ? badge("enabled", "ok") : badge("disabled", "warn")),
        el("div", { class: "kv-list" },
          kv("Agent key", r.agent_key),
          kv("Hostname", r.hostname || "—"),
          kv("Platform", r.platform || "—"),
          kv("OS", r.os_info || "—"),
          kv("Arch", r.arch || "—"),
          kv("Version", r.version || "—"),
          kv("Assigned scope", r.assigned_scope || "—"),
          kv("Last seen", r.last_seen ? fmtDate(r.last_seen) + ` (${agoLabel(r.last_seen_seconds_ago)})` : "never"),
          kv("Registered", fmtDate(r.registered_at)),
          kv("Current job", r.current_job_id ? "#" + r.current_job_id : "—"),
        )
      );
      openModal(`Agent — ${r.name}`, body, [el("button", { class: "btn primary", text: "Close", onClick: closeModal })]);
    }

    async function showCaps(r) {
      const body = el("div", {}, loadingState("Loading capabilities…"));
      openModal(`Capabilities — ${r.name}`, body, [el("button", { class: "btn ghost", text: "Close", onClick: closeModal })]);
      try {
        const res = await endpoints.agentCapabilities(r.id);
        const caps = res.capabilities || {};
        body.innerHTML = "";
        body.appendChild(el("div", { class: "kv-list" },
          Object.entries(caps).map(([k, v]) => kv(k.replace(/_/g, " "), v ? "yes" : "no"))));
        body.appendChild(el("p", { class: "muted", style: { fontSize: "12px", marginTop: "10px" }, text: "Capabilities are reported by the agent at registration/heartbeat. Job assignment is gated on them." }));
      } catch (e) { body.innerHTML = ""; body.appendChild(emptyState("Error", e.message)); }
    }

    async function showHealth(r) {
      const body = el("div", {}, loadingState("Loading health…"));
      openModal(`Health — ${r.name}`, body, [el("button", { class: "btn ghost", text: "Close", onClick: closeModal })]);
      try {
        const h = await endpoints.agentHealth(r.id);
        const health = h.health || {};
        body.innerHTML = "";
        body.appendChild(el("div", { style: { marginBottom: "10px" } }, agentStatusBadge(h.status)));
        body.appendChild(el("div", { class: "kv-list" },
          kv("Last seen", h.last_seen ? fmtDate(h.last_seen) + ` (${agoLabel(h.last_seen_seconds_ago)})` : "never"),
          kv("Version", h.version || "—"),
          kv("CPU", health.cpu != null ? health.cpu + "%" : "—"),
          kv("Memory", health.memory != null ? health.memory + "%" : "—"),
          kv("Uptime", health.uptime || "—"),
          kv("Reported at", health.reported_at ? fmtDate(health.reported_at) : "—"),
        ));
      } catch (e) { body.innerHTML = ""; body.appendChild(emptyState("Error", e.message)); }
    }

    async function assignScan(r) {
      if (r.status !== "online") {
        openModal("Assign scan", emptyState("NO AVAILABLE NEXCYR AGENT", "This agent is not online (no recent heartbeat). Scans are only routed to online, capable agents — NexCYR never claims a scan started when it did not."),
          [el("button", { class: "btn primary", text: "Close", onClick: closeModal })]);
        return;
      }
      const tOpts = await authorizedTargetOptions();
      const f = el("form", {},
        field("Authorized target", select("target_id", [["", tOpts.length ? "— Select one authorized target —" : "No authorized targets"], ...tOpts]),
          tOpts.length ? "Only explicitly authorized targets may be scanned." : "Add and authorize a target first."),
        field("Job type", select("job_type", JOB_TYPE_OPTIONS)),
        el("div", { class: "field-row" },
          field("Port profile", select("ports_profile", [["safe_default", "Safe default"], ["common", "Common ports"], ["top10", "Top 10"]])),
          field("Assessment", select("assessment_id", await assessmentOptions()))
        ),
        el("p", { class: "muted", style: { fontSize: "12px" }, text: "The Cloud sends only a structured job type and parameters — never shell commands." })
      );
      const go = el("button", { class: "btn primary", text: "Queue job" });
      go.addEventListener("click", async () => {
        const body = readForm(f, { numbers: ["target_id", "assessment_id"] });
        if (!body.target_id) { toast("No authorized target selected", "", "warn"); return; }
        body.agent_id = r.id;
        go.disabled = true;
        try {
          const job = await endpoints.createJob(body);
          closeModal(); toast("Job queued", `${job.job_type} → ${r.name}`, "ok"); showJobs(r);
        } catch (e) { toast("Could not queue job", e.message, "err"); }
        finally { go.disabled = false; }
      });
      openModal(`Assign scan — ${r.name}`, f, [el("button", { class: "btn ghost", text: "Cancel", onClick: closeModal }), go]);
    }

    async function showJobs(r) {
      const body = el("div", {}, loadingState("Loading jobs…"));
      openModal(`Job history — ${r.name}`, body, [el("button", { class: "btn ghost", text: "Close", onClick: closeModal })]);
      try {
        const jobs = await endpoints.agentJobs(r.id);
        body.innerHTML = "";
        body.appendChild(jobs.length
          ? table([
              { key: "id", label: "ID", render: (j) => el("span", { class: "mono", text: "#" + j.id }) },
              { key: "job_type", label: "Type", render: (j) => el("span", { class: "mono muted", text: j.job_type }) },
              { key: "status", label: "Status", render: (j) => statusBadge(j.status) },
              { key: "created_at", label: "Created", render: (j) => el("span", { class: "muted", text: fmtDate(j.created_at) }) },
            ], jobs)
          : emptyState("No jobs", "No scan jobs have been routed to this agent yet."));
      } catch (e) { body.innerHTML = ""; body.appendChild(emptyState("Error", e.message)); }
    }

    function toggleEnabled(r) {
      const next = !r.enabled;
      confirmModal(next ? "Enable agent" : "Disable agent", `${next ? "Enable" : "Disable"} "${r.name}"? ${next ? "" : "A disabled agent cannot claim jobs or authenticate."}`, async () => {
        try { await endpoints.updateAgent(r.id, { enabled: next }); toast(next ? "Agent enabled" : "Agent disabled", "", "ok"); reload(); }
        catch (e) { toast("Update failed", e.message, "err"); }
      }, next ? "Enable" : "Disable", !next);
    }

    function revoke(r) {
      confirmModal("Revoke agent", `Revoke "${r.name}"? Its credential is invalidated immediately and it can no longer authenticate. This cannot be undone.`, async () => {
        try { await endpoints.revokeAgent(r.id); toast("Agent revoked", "Credential invalidated", "ok"); reload(); }
        catch (e) { toast("Revoke failed", e.message, "err"); }
      }, "Revoke");
    }

    async function showAudit() {
      const body = el("div", {}, loadingState("Loading audit trail…"));
      openModal("Agent audit trail", body, [el("button", { class: "btn ghost", text: "Close", onClick: closeModal })]);
      try {
        const rows = await endpoints.agentAudit();
        body.innerHTML = "";
        body.appendChild(rows.length
          ? table([
              { key: "created_at", label: "When", render: (a) => el("span", { class: "muted", text: fmtDate(a.created_at) }) },
              { key: "action", label: "Action", render: (a) => badge((a.action || "").replace(/_/g, " "), "neutral") },
              { key: "actor", label: "Actor", render: (a) => el("span", { class: "mono muted", text: a.actor || "—" }) },
              { key: "detail", label: "Detail", render: (a) => el("span", { class: "muted", text: a.detail || "—" }) },
            ], rows)
          : emptyState("No audit events", "Agent lifecycle actions are recorded here."));
      } catch (e) { body.innerHTML = ""; body.appendChild(emptyState("Error", e.message)); }
    }

    c.appendChild(viewHead("NexCYR Agents", "Hybrid Cloud command center + distributed authorized scanning agents",
      [el("button", { class: "btn ghost", text: "Audit trail", onClick: showAudit }),
       el("button", { class: "btn primary", text: "+ Register agent", onClick: registerForm })]));
    c.appendChild(sumHost);
    c.appendChild(el("div", { class: "panel" }, listHost));
    await reload();
  }, "Loading agents…");
}

// ------------------------------------------------------------------
// View registry
// ------------------------------------------------------------------
export const views = {
  dashboard: dashboardView,
  assessments: assessmentsView,
  targets: targetsView,
  scans: scansView,
  recon: reconView,
  findings: findingsView,
  soc: socView,
  attackmap: attackMapView,
  purple: purpleView,
  wifi: wifiView,
  agents: agentsView,
  ai: aiView,
  reports: reportsView,
  settings: settingsView,
};
