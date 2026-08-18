# DFAT Quick Start

Follow these steps to run DFAT locally, log in as admin, create a case, register
evidence, run the pipeline, and view results.

On Windows, use **Git Bash**, **WSL**, or another environment that provides GNU
`make`. Equivalent Python commands are listed where `make` is inconvenient.

## 1. Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.11 or newer | Backend (`requires-python = ">=3.11"`) |
| Node.js | 18 or newer | Frontend (CRA 3.4 needs `NODE_OPTIONS=--openssl-legacy-provider` on Node 17+) |
| npm | 8+ | Ships with Node.js |
| Ollama | Latest | Local LLaMA-3 inference; optional if you only use rule-based fallback |
| GNU Make | Optional | `Makefile` targets; Git for Windows / WSL |

Pull the default model after installing Ollama:

```bash
ollama serve
ollama pull llama3
```

Confirm Ollama is listening on `http://localhost:11434`. DFAT rejects non-local
LLM URLs ([ADR-017](../architecture/adr/017-local-llm-only.md)).

## 2. Installation

From the repository root:

```bash
python -m venv .venv
# Linux / macOS / Git Bash:
source .venv/bin/activate
# Windows PowerShell:
# .venv\Scripts\Activate.ps1

pip install -e ".[dev,auth,reporting]"
# Optional native forensic parsers (pytsk3, Volatility3, python-evtx, …):
pip install -e ".[forensic]"

make frontend-install
# or: cd frontend && npm install --legacy-peer-deps
```

Copy environment examples if you do not already have a `.env`:

```bash
# Backend (optional — defaults live in config/default.yaml)
# Frontend:
cp frontend/.env.example frontend/.env
```

Default frontend API base is `/api/v1` (proxied to the backend in development).

## 3. Database setup

```bash
make db-init
```

This creates `data/` and runs Alembic migrations (`alembic upgrade head`).
The default database is SQLite at `./data/dfat.db`.

Without Make:

```bash
mkdir -p data
# Windows PowerShell: New-Item -ItemType Directory -Force data
set PYTHONPATH=src   # Windows: $env:PYTHONPATH = "src"
alembic -c src/dfat/database/migrations/alembic.ini upgrade head
```

## 4. Seed development data

`make seed-dev` talks to the **running HTTP API**. Start the backend first:

```bash
make dev-backend
```

In a second terminal (venv activated):

```bash
make seed-dev
```

This creates four users and two sample cases via `scripts/seed_dev_data.py`.

| Username | Password | Role |
|----------|----------|------|
| `admin` | `Admin!Pass#2026` | admin |
| `investigator1` | `Invest!Pass#2026` | investigator |
| `analyst1` | `Analyst!Pass#2026` | analyst |
| `viewer1` | `Viewer!Pass#2026` | viewer |

Alternatively, `make dev-setup` installs dependencies, initialises the database,
starts the API long enough to seed, then launches backend and frontend together.

## 5. Start services

With the backend already running from step 4, start the UI in another terminal:

```bash
make dev-frontend
```

Or start both (if the backend is not already up):

```bash
make dev-start
```

| Service | URL |
|---------|-----|
| Frontend | http://127.0.0.1:3000 |
| API | http://127.0.0.1:8000 |
| OpenAPI | http://127.0.0.1:8000/docs |
| Health | http://127.0.0.1:8000/api/v1/health |

Docker alternative (backend, frontend, Ollama):

```bash
docker compose -f docker-compose.dev.yml up --build
```

After Compose starts, pull the model. The API only accepts loopback LLM URLs
(`127.0.0.1` / `localhost`). Prefer Ollama on the host (`ollama serve` +
`DFAT_AI_ENGINE__LLM_API_URL=http://127.0.0.1:11434/api/generate`) rather than
the Compose service hostname `ollama`.

```bash
ollama pull llama3
```

Then seed against `http://localhost:8000/api/v1` (`make seed-dev`).

## 6. Login with the admin account

1. Open http://127.0.0.1:3000/auth/login
2. Username: `admin`
3. Password: `Admin!Pass#2026`

You should land on the dashboard. Admin also sees **Settings**, **User
Management**, and **Audit Logs** in the sidebar.

## 7. Create the first case

1. Open **Cases** → **New Case** (`/cases/new`).
2. Enter a case name (required) and optional description.
3. Submit. The case starts in status `created`.
4. Open the case. Assign a **lead** investigator if prompted, then use
   **Open** (`created` → `open`) and **Activate** (`open` → `active`).

Evidence can only be registered against a case that is **open** or **active**.

Seeded cases `Dev Sample — Open` and `Dev Sample — Active` are already usable.

## 8. Register evidence

1. Place a disk image or memory dump under `data/evidence/` (or another path
   the API process can read). Supported extensions include `.dd`, `.raw`,
   `.e01`, `.img`, `.001` (disk) and `.raw`, `.vmem`, `.dmp`, `.mem` (memory).
2. Open **Evidence** → **Register** (`/evidence/register`).
3. Choose the case, evidence type (`disk_image` or `memory_dump`), file path
   **on the server**, and optional description.
4. Submit. DFAT hashes the file, records chain-of-custody, and validates
   metadata. The case must be `open` or `active`.

Path traversal (`..`) is rejected. The path is a **server filesystem path**,
not a browser upload of the raw image.

## 9. Run the pipeline

1. Open **Pipeline** → **Run** (`/pipeline/run`).
2. Select the case, evidence item, and mode (`full`, `parse-only`, or
   `triage-only`).
3. Leave **use fallback** unchecked to prefer the local LLM; check it to force
   rule-based triage (works without Ollama).
4. Submit. The job is queued (HTTP 202). Open the job page
   (`/pipeline/:jobId`) and wait for stages to complete.

If forensic extras are not installed, parsers that need pytsk3 or Volatility3
are marked unavailable and the remaining stages continue.

## 10. View results

When the job finishes:

| What | Where |
|------|--------|
| Stage timings and artefact counts | Pipeline job detail |
| Artefacts by category / suspicion | **Artefacts** explorer, timeline, IOC dashboard |
| AI classify / summarise / Q&A | **AI Analysis** (`/ai`) — needs parsed artefacts |
| Dual-output report | **Reports** → report detail: JSON, narrative, PDF/HTML/JSON export |
| Integrity / custody | Report **Verify** tab; evidence **Integrity** page |
| Benchmarks | **Evaluation** → Benchmark (needs local ground-truth files) |

Interactive API examples: http://127.0.0.1:8000/docs

Full feature tour: [USER_MANUAL.md](USER_MANUAL.md).
API contracts: [../development/API_REFERENCE.md](../development/API_REFERENCE.md).
