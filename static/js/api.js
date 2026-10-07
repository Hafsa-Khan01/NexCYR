// NexCYR API client — every call maps to a real FastAPI route.

class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === "string" ? detail : JSON.stringify(detail));
    this.status = status;
    this.detail = detail;
  }
}

async function request(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(path, opts);
  } catch (e) {
    throw new ApiError(0, "Network error — is the NexCYR server running?");
  }
  const ct = res.headers.get("content-type") || "";
  let data = null;
  if (ct.includes("application/json")) {
    data = await res.json().catch(() => null);
  } else {
    data = await res.text().catch(() => "");
  }
  if (!res.ok) {
    const detail = data && data.detail ? data.detail : `HTTP ${res.status}`;
    throw new ApiError(res.status, detail);
  }
  return data;
}

export const api = {
  get: (p) => request("GET", p),
  post: (p, b) => request("POST", p, b ?? {}),
  put: (p, b) => request("PUT", p, b ?? {}),
  del: (p) => request("DELETE", p),
  ApiError,
};

// Convenience endpoints
export const endpoints = {
  health: () => api.get("/health"),
  dashboard: () => api.get("/api/dashboard/summary"),

  assessments: () => api.get("/api/assessments"),
  assessment: (id) => api.get(`/api/assessments/${id}`),
  createAssessment: (b) => api.post("/api/assessments", b),
  updateAssessment: (id, b) => api.put(`/api/assessments/${id}`, b),
  deleteAssessment: (id) => api.del(`/api/assessments/${id}`),

  targets: (q = "") => api.get("/api/targets" + q),
  createTarget: (b) => api.post("/api/targets", b),
  updateTarget: (id, b) => api.put(`/api/targets/${id}`, b),
  deleteTarget: (id) => api.del(`/api/targets/${id}`),

  scans: (q = "") => api.get("/api/scans" + q),
  scan: (id) => api.get(`/api/scans/${id}`),
  scanStatus: (id) => api.get(`/api/scans/${id}/status`),
  scanResults: (id) => api.get(`/api/scans/${id}/results`),
  scanSummary: () => api.get("/api/scans/summary"),
  createScan: (b) => api.post("/api/scans", b),
  deleteScan: (id) => api.del(`/api/scans/${id}`),

  recon: (q = "") => api.get("/api/recon" + q),
  reconResult: (id) => api.get(`/api/recon/${id}`),
  createRecon: (b) => api.post("/api/recon", b),

  findings: (q = "") => api.get("/api/findings" + q),
  finding: (id) => api.get(`/api/findings/${id}`),
  createFinding: (b) => api.post("/api/findings", b),
  updateFinding: (id, b) => api.put(`/api/findings/${id}`, b),
  deleteFinding: (id) => api.del(`/api/findings/${id}`),

  socEvents: (q = "") => api.get("/api/soc/events" + q),
  socEvent: (id) => api.get(`/api/soc/events/${id}`),
  createSocEvent: (b) => api.post("/api/soc/events", b),
  updateSocEvent: (id, b) => api.put(`/api/soc/events/${id}`, b),
  deleteSocEvent: (id) => api.del(`/api/soc/events/${id}`),
  socSummary: () => api.get("/api/soc/summary"),
  socCorrelation: (q = "") => api.get("/api/soc/correlation" + q),

  ai: (b) => api.post("/api/ai", b),
  aiStatus: () => api.get("/api/ai/status"),
  aiHistory: () => api.get("/api/ai/history"),

  purple: (q = "") => api.get("/api/purple-team/tests" + q),
  purpleTest: (id) => api.get(`/api/purple-team/tests/${id}`),
  createPurple: (b) => api.post("/api/purple-team/tests", b),
  updatePurple: (id, b) => api.put(`/api/purple-team/tests/${id}`, b),
  deletePurple: (id) => api.del(`/api/purple-team/tests/${id}`),

  attackMap: (q = "") => api.get("/api/attack-map" + q),

  wifi: (q = "") => api.get("/api/wifi/assessments" + q),
  wifiSensor: () => api.get("/api/wifi/sensor/status"),
  createWifi: (b) => api.post("/api/wifi/assessments", b),
  updateWifi: (id, b) => api.put(`/api/wifi/assessments/${id}`, b),
  deleteWifi: (id) => api.del(`/api/wifi/assessments/${id}`),
  discoverWifi: (id) => api.post(`/api/wifi/assessments/${id}/discover`),

  reports: () => api.get("/api/reports"),
  createReport: (b) => api.post("/api/reports", b),
  deleteReport: (id) => api.del(`/api/reports/${id}`),
  pdfUrl: (assessmentId) =>
    "/api/reports/pdf" + (assessmentId ? `?assessment_id=${assessmentId}` : ""),

  settings: () => api.get("/api/settings"),
  updateSettings: (b) => api.put("/api/settings", b),

  search: (q) => api.get("/api/search?q=" + encodeURIComponent(q)),

  agents: () => api.get("/api/agents"),
  agent: (id) => api.get(`/api/agents/${id}`),
  enrollAgent: (b) => api.post("/api/agents", b),
  updateAgent: (id, b) => api.put(`/api/agents/${id}`, b),
  revokeAgent: (id) => api.post(`/api/agents/${id}/revoke`),
  agentHealth: (id) => api.get(`/api/agents/${id}/health`),
  agentCapabilities: (id) => api.get(`/api/agents/${id}/capabilities`),
  agentJobs: (id) => api.get(`/api/agents/${id}/jobs`),
  jobs: () => api.get("/api/agents/jobs"),
  createJob: (b) => api.post("/api/agents/jobs", b),
  cancelJob: (id) => api.post(`/api/agents/jobs/${id}/cancel`),
  agentAudit: () => api.get("/api/agents/audit"),
};
