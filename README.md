# NexCYR

**NexCYR — Unified Cybersecurity Assessment & Purple Team Platform** (v1.0.0)

A single, self-contained web application for authorized security assessment work:
engagement tracking, authorized reconnaissance and scanning, risk-scored findings,
SOC event monitoring with correlation, purple-team detection validation, wireless
assessment, a contextual intelligence assistant, professional PDF reporting, and a
hybrid Cloud + Agent execution model.

NexCYR is built to be **fully functional without any external AI provider or cloud
dependency**. It runs as one FastAPI process that serves both the JSON API and the
HTML/CSS/JS frontend, backed by SQLite.

> **Authorized use only.** NexCYR will only scan or run reconnaissance against
> targets explicitly marked as authorized. It never fabricates findings, scan
> results, attacks, SOC incidents, risk claims, or metrics — empty states are shown
> honestly instead.

---

## Tech stack

- **Backend:** Python 3.13, FastAPI, SQLAlchemy 2.x, Pydantic v2
- **Database:** SQLite (schema/engine stay PostgreSQL-ready — change `DATABASE_URL`)
- **Frontend:** Jinja2 templates + vanilla ES-module JavaScript + hand-written CSS
  (no React/Node/Next/Vue build step, no Docker/K8s/Redis/Kafka/Celery)
- **Reporting:** ReportLab (PDF)
- **Scanning:** Nmap when available (safe, fixed, non-destructive arguments);
  returns a clean `NMAP_UNAVAILABLE` status otherwise — never fabricated results
- **Intelligence:** optional OpenAI-compatible provider, plus a mandatory
  **NexCYR Intelligence Fallback Engine** that answers from the local database
- **Testing:** pytest + HTTPX (FastAPI `TestClient`) against an isolated test DB

---

## Quick start (local)

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
# Windows (Git Bash):
source .venv/Scripts/activate
# macOS/Linux:
# source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) configure environment
cp .env.example .env      # then edit .env — never commit it

# 4. Run the app
uvicorn main:app --reload
```

Open http://127.0.0.1:8000

The first request to the app initializes/migrates the SQLite schema automatically.

### Flow

`LOGIN → BOOT (WELCOME TO NexCYR, animated Cyber DNA Core) → COMMAND CENTER`

The boot animation respects `prefers-reduced-motion`. The login gate stores the
operator name in `sessionStorage` only — it is a UI gate, not an auth boundary.

---

## Deployment

NexCYR is one process serving both the API and the UI, so any Python host works.
Pick the option that matches what you need to demonstrate.

| Option | Files | Persistent data | Good for |
| --- | --- | --- | --- |
| **Railway** | `railway.json`, `Dockerfile` | volume mounted at `/data` | Zero-config public URL for a viva demo |
| **Fly.io** | `fly.toml`, `Dockerfile` | `nexcyr_data` volume at `/data` | Same, with a warm machine (no cold starts) |
| **Any container host** | `Dockerfile`, `.dockerignore`, `Procfile` | bind-mount `/data` | Render, ECS, Docker Compose, local Docker |
| **VPS** | `deploy/` (systemd + nginx + bootstrap) | real disk at `/var/lib/nexcyr` | Demoing **real Agents** connecting from inside a target network |

### Required environment variables

| Variable | Purpose | Default |
| --- | --- | --- |
| `DATABASE_URL` | SQLAlchemy database URL | `sqlite:///./nexcyr.db` |
| `REPORTS_DIR` | Directory for generated PDFs | `./reports` |
| `AI_PROVIDER` | External AI provider name (optional) | *(empty → fallback engine)* |
| `AI_MODEL` | External AI model (optional) | *(empty)* |
| `OPENAI_API_KEY` | External AI key (optional) | *(empty)* |
| `OPENAI_BASE_URL` | OpenAI-compatible base URL | `https://api.openai.com/v1` |
| `NMAP_PATH` | Explicit path to the nmap binary (optional) | auto-detected on `PATH` |

No secrets are hardcoded. Without an AI key the platform runs on its local
Intelligence Fallback Engine and stays fully functional.

### Cloud Nmap

The deployment Docker image includes the Nmap system package, so a deployed NexCYR instance does not depend on Nmap being installed on an operator's PC. Railway builds the repository's root Dockerfile for each deployment. citeturn316260search0turn316260search6

Cloud Nmap is for targets that the cloud service can reach and that are explicitly marked authorized in NexCYR. A private LAN/CIDR still needs an online NexCYR Agent inside that network; the cloud service cannot magically reach a user's local network.

### Railway

`railway.json` already pins the Dockerfile build, the start command
(`uvicorn main:app --host 0.0.0.0 --port $PORT`), the `/health` healthcheck and a
single replica. You only need to attach storage:

```bash
railway init
railway volume add -m /data          # SQLite DB + PDFs survive redeploys
railway up
railway domain                       # public HTTPS URL
```

Then set `DATABASE_URL=sqlite:////data/nexcyr.db` and `REPORTS_DIR=/data/reports`
as Railway variables (four slashes = absolute path).

> **Without a volume the database is wiped on every deploy.** Railway's container
> filesystem is ephemeral. If you would rather not manage a volume, create a
> Railway PostgreSQL plugin and set `DATABASE_URL` to its URL — uncomment
> `psycopg[binary]` in `requirements.txt` and you are done; the models and engine
> setup are dialect-agnostic, so no code changes are needed.

### Fly.io

```bash
fly launch --no-deploy --copy-config
fly volumes create nexcyr_data --size 1 --region lhr
fly deploy
```

`fly.toml` keeps `min_machines_running = 1` and `auto_stop_machines = false` so a
cold start cannot interrupt a live demo or an agent's job poll.

### Docker (anywhere)

```bash
docker build -t nexcyr .
docker volume create nexcyr-data
docker run -d --name nexcyr -p 8000:8000 -v nexcyr-data:/data nexcyr
```

The image runs as a non-root `nexcyr` user, defaults to the `/data` volume and
has a `/health` HEALTHCHECK.

### VPS (systemd + nginx) — recommended for the hybrid Agent story

This is the only option where field Agents can reach the Cloud over the internet
with TLS while you also control the host. One command provisions it:

```bash
git clone https://github.com/Hafsa-Khan01/NexCYR.git /tmp/nexcyr-src
cd /tmp/nexcyr-src && sudo bash deploy/setup-vps.sh
```

The script is idempotent and never deletes data — an existing
`/var/lib/nexcyr/nexcyr.db` is reused, not overwritten. Afterwards replace
`nexcyr.example.com` in `/etc/nginx/sites-available/nexcyr` with your hostname
and run `sudo certbot --nginx -d your.hostname`.

Layout it creates:

- `/opt/nexcyr` — application + `.venv`, owned by the `nexcyr` system user
- `/var/lib/nexcyr/nexcyr.db` — database (`chmod 750` on the directory)
- `/var/lib/nexcyr/reports/` — generated PDFs (`chmod 700`)
- uvicorn bound to **127.0.0.1:8000**; nginx is the only public entry point
- systemd hardening: `NoNewPrivileges`, `ProtectSystem=strict`, `PrivateTmp`,
  `ReadWritePaths=/var/lib/nexcyr`

Useful commands: `sudo journalctl -u nexcyr -f`, `sudo systemctl restart nexcyr`.

Back up the database without stopping the service:

```bash
sudo -u nexcyr sqlite3 /var/lib/nexcyr/nexcyr.db ".backup '/root/nexcyr-$(date +%F).db'"
```

### Connecting an Agent after deployment

The Cloud side of the hybrid architecture is fully implemented; an Agent is any
client that enrolls and then talks to the agent-facing endpoints with its token:

1. **Agents → Register agent** in the UI. Copy the enrollment token — it is
   shown **once** and only its SHA-256 hash is stored.
2. From a host inside the authorized target network, using
   `X-NexCYR-Agent-Token: <token>` (or `Authorization: Bearer <token>`):
   - `POST /api/agents/register` — announce hostname, platform, capabilities
   - `POST /api/agents/heartbeat` — keep status `online` (90s window)
   - `GET  /api/agents/me/jobs/next` — claim a structured job
   - `POST /api/agents/jobs/{id}/result` — return validated results
3. Select that agent as the scan location in the UI. If it is not `online`, the
   Cloud refuses with **`NO AVAILABLE NEXCYR AGENT`** rather than fabricating
   results.

> **Do not install nmap on a public cloud host.** Scanning from Railway/Fly can
> breach provider terms and may touch networks you are not authorized to test.
> The container image deliberately omits nmap, so Cloud-side scans report
> `NMAP_UNAVAILABLE` and real enumeration is routed to an enrolled Agent inside
> the authorized network. Run nmap only on your own lab machine or on an Agent
> you control, against targets with recorded authorization.

---

## API contract

All routes are served by the same FastAPI app and documented at `/docs`.

**System / pages:** `GET /` (login), `GET /boot`, `GET /dashboard`, `GET /health`, `GET /docs`

**Core modules**

| Area | Endpoints |
| --- | --- |
| Assessments | `GET/POST /api/assessments`, `GET/PUT/DELETE /api/assessments/{id}` |
| Targets | `GET/POST /api/targets`, `GET/PUT/DELETE /api/targets/{id}` |
| Findings | `GET/POST /api/findings`, `GET/PUT/DELETE /api/findings/{id}` |
| Scans | `GET/POST /api/scans`, `GET /api/scans/{id}`, `/status`, `/results`, `GET /api/scans/summary`, `DELETE /api/scans/{id}` |
| Recon | `GET/POST /api/recon`, `GET /api/recon/{id}` |
| SOC | `GET/POST /api/soc/events`, `GET/PUT/DELETE /api/soc/events/{id}`, `GET /api/soc/summary`, `GET /api/soc/correlation` |
| Intelligence | `POST /api/ai`, `GET /api/ai/status`, `GET /api/ai/history` |
| Purple Team | `GET/POST /api/purple-team/tests`, `GET/PUT/DELETE /api/purple-team/tests/{id}` |
| Attack Map | `GET /api/attack-map` |
| Wi-Fi | `GET/POST /api/wifi/assessments`, `GET/PUT/DELETE /api/wifi/assessments/{id}`, `GET /api/wifi/sensor/status`, `POST /api/wifi/assessments/{id}/discover` |
| Reports | `GET/POST /api/reports`, `GET /api/reports/{id}`, `GET /api/reports/{id}/download`, `GET /api/reports/pdf`, `DELETE /api/reports/{id}` |
| Settings | `GET/PUT /api/settings` |
| Search | `GET /api/search?q=` |
| Dashboard | `GET /api/dashboard/summary` |

**Hybrid Cloud + Agents** (`/api/agents`)

Operator endpoints: `GET/POST /api/agents`, `GET/PUT /api/agents/{id}`,
`GET /api/agents/{id}/health`, `/capabilities`, `/jobs`,
`POST /api/agents/{id}/revoke`, `GET /api/agents/audit`,
`GET/POST /api/agents/jobs`, `GET /api/agents/jobs/{id}`, `POST /api/agents/jobs/{id}/cancel`.

Agent-facing endpoints (token authenticated via `X-NexCYR-Agent-Token` or
`Authorization: Bearer`): `POST /api/agents/register`, `POST /api/agents/heartbeat`,
`GET /api/agents/me/jobs/next`, `POST /api/agents/jobs/{id}/result`,
`POST /api/agents/jobs/{id}/status`.

---

## Hybrid Cloud + Agent architecture

NexCYR Cloud is the command center. Distributed **NexCYR Agents** can run authorized
scans from inside a target network. The model is zero-trust and command-free:

- **The Cloud never sends shell commands.** Agents accept only structured job types:
  `NMAP_HOST_DISCOVERY`, `NMAP_PORT_SCAN`, `NMAP_SERVICE_ENUMERATION`, `AUTHORIZED_RECON`.
- **Enrollment credentials** are issued once (plaintext shown a single time, stored
  only as a SHA-256 hash). Unknown agents are never auto-trusted.
- **Status is heartbeat-derived** — `ONLINE` / `DEGRADED` / `OFFLINE` (plus
  `ENROLLED` / `DISABLED` / `REVOKED`). NexCYR never claims an agent is online
  without a recent heartbeat.
- **Capability-gated routing.** A scan is only routed to an agent that is online and
  reports the required scanner capability. Otherwise the API returns
  `409 NO AVAILABLE NEXCYR AGENT …` and does **not** claim the scan started.
- **Job lifecycle:** `PENDING → QUEUED → RUNNING → COMPLETED / FAILED / CANCELLED`.
- **Results are validated and re-derived centrally.** Agent-submitted services are
  structurally validated (ports clamped to 1–65535, capped), then findings and risk
  scores are computed by NexCYR's own engines — agent payloads are never trusted
  verbatim.
- **Scan source tracking** (`CLOUD` / `AGENT` with agent id/name/version) flows into
  the attack map (Agent → Scan and Cloud Scanner → Scan edges), PDF reports (a
  "Source" column), and AI context ("Which agent ran this scan?").
- **Auditing.** Important agent/job actions are recorded and viewable at
  `GET /api/agents/audit`.

---

## Security model

- Only targets explicitly flagged `authorized` may be scanned or reconned; every
  scan/recon/job route enforces this and returns `400` otherwise.
- No arbitrary shell/command execution, no `shell=True`; Nmap is invoked with fixed,
  non-destructive arguments and only against validated, safe target values.
- When Nmap is unavailable the result is a clean `NMAP_UNAVAILABLE` status — no
  fabricated services or findings.
- Secrets come only from environment variables; agent credentials are stored hashed
  and returned in plaintext exactly once.
- Demo/sample data, if ever added, must be explicitly labeled **DEMO DATA**.

---

## Testing

Tests run against an **isolated temporary database** (configured in `conftest.py`
before the app is imported) and never call an external LLM. The real `nexcyr.db`
and `reports/` directory are untouched.

```bash
pytest -q
```

Coverage includes the full API contract (system/pages, CRUD for every module,
authorization gating, validation errors, SOC correlation, attack-map honesty,
AI fallback, settings, search, PDF generation) and the hybrid architecture
(enrollment one-time token, agent auth, heartbeat status, capability-gated routing,
the full job lifecycle with centrally-derived findings, honest `409` refusal,
disable/revoke, audit trail, and agent-aware map/reports/AI).

A quick syntax/compile check of the whole package:

```bash
python -m compileall -q . -x "\.venv"
```

---

## Project structure

```
NexCYR/
├── main.py                 # FastAPI app, router registration, page routes, lifespan
├── config.py               # Environment-driven configuration (no hardcoded secrets)
├── database.py             # Engine, session, additive/legacy schema migration
├── conftest.py             # Pytest fixtures — isolated test DB, helper factories
├── requirements.txt
├── .env.example
├── api/
│   ├── utils.py
│   └── routes/             # assessments, targets, scans, findings, recon, soc,
│                           # ai, purple_team, attack_map, wifi, reports, settings,
│                           # search, dashboard, agents
├── models/                 # SQLAlchemy 2.x models (incl. agent, scan_job, audit_event)
├── services/               # risk, vulnerability, recon, nmap, correlation,
│                           # intelligence, agent, report, pdf, settings services
├── templates/              # login.html, boot.html, dashboard.html (Jinja2)
├── static/
│   ├── css/                # nexcyr.css, boot.css, login.css
│   └── js/                 # api.js, ui.js, voice.js, attackmap.js, views.js, app.js
├── tests/                  # test_api_contract.py, test_hybrid_agents.py
├── Dockerfile              # Single-image deploy (non-root, /data volume, healthcheck)
├── .dockerignore
├── railway.json            # Railway build/start/healthcheck/replica policy
├── fly.toml                # Fly.io with a mounted nexcyr_data volume
├── Procfile                # Generic PaaS start command
├── .python-version
└── deploy/                 # VPS path
    ├── setup-vps.sh        #   Idempotent bootstrap (user, venv, dirs, units)
    ├── nexcyr.service      #   Hardened systemd unit, loopback-only uvicorn
    ├── nginx.conf          #   TLS reverse proxy to 127.0.0.1:8000
    └── nginx-upgrade-map.conf
```

---

## License / disclaimer

NexCYR is a defensive/authorized-assessment tool. Operators are responsible for
obtaining and recording explicit authorization before any scanning or
reconnaissance, and for complying with all applicable laws and rules of engagement.
