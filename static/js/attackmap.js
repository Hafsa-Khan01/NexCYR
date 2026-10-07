// NexCYR Cyber Attack Map — original relationship/network graph.
// Renders ONLY real stored relationships. No fabricated nodes.
//   Target -> Scan -> Finding -> SOC Event -> Purple Team Test

const TYPE_COLOR = {
  target: "#22e0ff",
  scan: "#3b82f6",
  finding: "#ff7a18",
  soc_event: "#e11d8f",
  purple_team: "#8b5cf6",
  agent: "#4ade80",
  cloud: "#94a3b8",
};
const TYPE_LABEL = {
  target: "Target",
  scan: "Scan",
  finding: "Finding",
  soc_event: "SOC Event",
  purple_team: "Purple Team Test",
  agent: "NexCYR Agent",
  cloud: "Cloud Scanner",
};
const SEV_COLOR = {
  critical: "#ff2d55", high: "#ff7a18", medium: "#f5c518", low: "#38bdf8", info: "#8b98a5",
};
const TYPE_RADIUS = { target: 13, scan: 10, finding: 11, soc_event: 10, purple_team: 10, agent: 12, cloud: 12 };

function nodeColor(n) {
  if (n.type === "finding" && n.severity) return SEV_COLOR[String(n.severity).toLowerCase()] || TYPE_COLOR.finding;
  if (n.type === "soc_event" && n.severity) return SEV_COLOR[String(n.severity).toLowerCase()] || TYPE_COLOR.soc_event;
  return TYPE_COLOR[n.type] || "#8ea0bb";
}

export class AttackMap {
  constructor(canvas, tipEl, { onSelect } = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.tip = tipEl;
    this.onSelect = onSelect || (() => {});
    this.nodes = [];
    this.edges = [];
    this.typeFilter = new Set(Object.keys(TYPE_COLOR));
    this.sevFilter = new Set(["critical", "high", "medium", "low", "info", "none"]);
    this.hover = null;
    this.selected = null;
    this.dash = 0;
    this.raf = null;
    this.reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    this._bind();
  }

  setData(data) {
    const W = this.canvas.clientWidth || 800;
    const H = this.canvas.clientHeight || 560;
    this.nodes = (data.nodes || []).map((n, i) => ({
      ...n,
      x: W / 2 + Math.cos((i / Math.max(1, data.nodes.length)) * Math.PI * 2) * (H * 0.32) + (Math.random() * 40 - 20),
      y: H / 2 + Math.sin((i / Math.max(1, data.nodes.length)) * Math.PI * 2) * (H * 0.32) + (Math.random() * 40 - 20),
      vx: 0, vy: 0,
    }));
    this.byId = new Map(this.nodes.map((n) => [n.id, n]));
    this.edges = (data.edges || []).filter((e) => this.byId.has(e.source) && this.byId.has(e.target));
    this.hover = null; this.selected = null;
    if (!this.raf) this._loop();
  }

  setTypeFilter(types) { this.typeFilter = new Set(types); }
  setSevFilter(sevs) { this.sevFilter = new Set(sevs); }

  _visible(n) {
    if (!this.typeFilter.has(n.type)) return false;
    const sev = n.severity ? String(n.severity).toLowerCase() : "none";
    return this.sevFilter.has(sev) || sev === "none";
  }

  _bind() {
    const c = this.canvas;
    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      const w = c.clientWidth, h = c.clientHeight;
      c.width = w * dpr; c.height = h * dpr;
      this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    window.addEventListener("resize", () => { resize(); });

    c.addEventListener("mousemove", (e) => {
      const r = c.getBoundingClientRect();
      const mx = e.clientX - r.left, my = e.clientY - r.top;
      const hit = this._hitTest(mx, my);
      this.hover = hit;
      c.style.cursor = hit ? "pointer" : "";
      if (hit && this.tip) {
        this.tip.innerHTML = `<b style="color:${nodeColor(hit)}">${TYPE_LABEL[hit.type] || hit.type}</b><br/>${this._esc(hit.label || "")}` +
          (hit.severity ? `<br/><span class="muted">severity: ${hit.severity}</span>` : "") +
          (hit.meta && hit.meta.value ? `<br/><span class="muted">${this._esc(hit.meta.value)}</span>` : "");
        this.tip.style.display = "block";
        this.tip.style.left = (e.clientX + 14) + "px";
        this.tip.style.top = (e.clientY + 14) + "px";
      } else if (this.tip) {
        this.tip.style.display = "none";
      }
    });
    c.addEventListener("mouseleave", () => { this.hover = null; if (this.tip) this.tip.style.display = "none"; });
    c.addEventListener("click", (e) => {
      const r = c.getBoundingClientRect();
      const hit = this._hitTest(e.clientX - r.left, e.clientY - r.top);
      this.selected = hit;
      this.onSelect(hit);
    });
  }

  _esc(s) { return String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

  _hitTest(mx, my) {
    for (let i = this.nodes.length - 1; i >= 0; i--) {
      const n = this.nodes[i];
      if (!this._visible(n)) continue;
      const r = (TYPE_RADIUS[n.type] || 10) + 4;
      if ((n.x - mx) ** 2 + (n.y - my) ** 2 <= r * r) return n;
    }
    return null;
  }

  _physics() {
    const W = this.canvas.clientWidth, H = this.canvas.clientHeight;
    const vis = this.nodes.filter((n) => this._visible(n));
    // repulsion
    for (let i = 0; i < vis.length; i++) {
      for (let j = i + 1; j < vis.length; j++) {
        const a = vis[i], b = vis[j];
        let dx = b.x - a.x, dy = b.y - a.y;
        let d2 = dx * dx + dy * dy || 0.01;
        if (d2 > 40000) continue;
        const d = Math.sqrt(d2);
        const f = 1400 / d2;
        dx /= d; dy /= d;
        a.vx -= dx * f; a.vy -= dy * f;
        b.vx += dx * f; b.vy += dy * f;
      }
    }
    // springs
    for (const e of this.edges) {
      const a = this.byId.get(e.source), b = this.byId.get(e.target);
      if (!a || !b || !this._visible(a) || !this._visible(b)) continue;
      const dx = b.x - a.x, dy = b.y - a.y;
      const d = Math.sqrt(dx * dx + dy * dy) || 0.01;
      const target = 90;
      const f = (d - target) * 0.006;
      const ux = dx / d, uy = dy / d;
      a.vx += ux * f; a.vy += uy * f;
      b.vx -= ux * f; b.vy -= uy * f;
    }
    // gravity + integrate
    for (const n of vis) {
      n.vx += (W / 2 - n.x) * 0.0016;
      n.vy += (H / 2 - n.y) * 0.0016;
      n.vx *= 0.86; n.vy *= 0.86;
      n.x += Math.max(-6, Math.min(6, n.vx));
      n.y += Math.max(-6, Math.min(6, n.vy));
      n.x = Math.max(18, Math.min(W - 18, n.x));
      n.y = Math.max(18, Math.min(H - 18, n.y));
    }
  }

  _draw() {
    const ctx = this.ctx;
    const W = this.canvas.clientWidth, H = this.canvas.clientHeight;
    ctx.clearRect(0, 0, W, H);
    this.dash = this.reduce ? 0 : (this.dash + 0.5) % 1000;

    // edges
    for (const e of this.edges) {
      const a = this.byId.get(e.source), b = this.byId.get(e.target);
      if (!a || !b || !this._visible(a) || !this._visible(b)) continue;
      const active = this.hover && (this.hover.id === a.id || this.hover.id === b.id);
      ctx.strokeStyle = active ? "rgba(34,224,255,0.75)" : "rgba(120,160,220,0.22)";
      ctx.lineWidth = active ? 1.8 : 1.1;
      ctx.setLineDash([5, 6]);
      ctx.lineDashOffset = -this.dash;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // nodes
    for (const n of this.nodes) {
      if (!this._visible(n)) continue;
      const r = TYPE_RADIUS[n.type] || 10;
      const col = nodeColor(n);
      const isHover = this.hover && this.hover.id === n.id;
      const isSel = this.selected && this.selected.id === n.id;
      // glow
      ctx.beginPath();
      ctx.arc(n.x, n.y, r + (isHover || isSel ? 6 : 3), 0, Math.PI * 2);
      ctx.fillStyle = col + (isHover || isSel ? "44" : "1f");
      ctx.fill();
      // core
      ctx.beginPath();
      ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(6,10,20,0.92)";
      ctx.fill();
      ctx.lineWidth = isSel ? 2.6 : 1.8;
      ctx.strokeStyle = col;
      ctx.shadowColor = col;
      ctx.shadowBlur = isHover || isSel ? 16 : 8;
      ctx.stroke();
      ctx.shadowBlur = 0;
      // label
      if (isHover || isSel || r >= 11) {
        ctx.font = "10px 'Segoe UI', sans-serif";
        ctx.fillStyle = isHover || isSel ? "#eafcff" : "rgba(190,210,235,0.6)";
        ctx.textAlign = "center";
        const label = (n.label || TYPE_LABEL[n.type] || "").slice(0, 22);
        ctx.fillText(label, n.x, n.y + r + 13);
      }
    }
  }

  _loop() {
    this._physics();
    this._draw();
    this.raf = requestAnimationFrame(() => this._loop());
  }

  destroy() {
    if (this.raf) cancelAnimationFrame(this.raf);
    this.raf = null;
  }
}

export const MAP_TYPE_LABEL = TYPE_LABEL;
export const MAP_TYPE_COLOR = TYPE_COLOR;
export const MAP_SEV_COLOR = SEV_COLOR;
