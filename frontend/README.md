# DFAT Frontend

React UI for the **Digital Forensics Automation Tool (DFAT)** — case lifecycle, evidence custody, forensic pipeline control, AI triage, dual-output reporting, and evaluation dashboards.

Built on a cleaned [Volt React Dashboard](https://github.com/themesberg/volt-react-dashboard) (Bootstrap 5) shell, wired to the DFAT FastAPI backend (`/api/v1`).

## Tech stack

| Layer | Choice |
| --- | --- |
| UI | React 16, React Router 5, `@themesberg/react-bootstrap` (Bootstrap 5) |
| Base theme | Volt React Dashboard (MIT) |
| HTTP | Axios client with JWT attach, refresh, error normalisation |
| State | React Context (`Auth`, `Theme`, `Notification`) + custom hooks |
| Icons | Font Awesome 5 |
| Tests | Jest (CRA), Testing Library, MSW |

## Setup

```bash
cd frontend
npm install --legacy-peer-deps
cp .env.example .env.development   # adjust REACT_APP_* as needed
```

Required Node options on Node 17+ (OpenSSL):

```bash
# Windows PowerShell
$env:NODE_OPTIONS = "--openssl-legacy-provider"
npm start
```

Environment variables (see `.env.example`):

- `REACT_APP_API_BASE_URL` — default `http://localhost:8000/api/v1`
- `REACT_APP_APP_NAME` / `REACT_APP_APP_VERSION`
- `REACT_APP_TOKEN_REFRESH_INTERVAL_MS`
- `REACT_APP_POLLING_INTERVAL_MS`
- `REACT_APP_DEBUG`

## Scripts

| Script | Purpose |
| --- | --- |
| `npm start` | Dev server (with OpenSSL legacy provider on Windows) |
| `npm run build` | Production build |
| `npm test` | Jest watch mode |
| `npm run test:coverage` | One-shot tests with coverage |
| `npm test -- --watchAll=false` | CI-style single run |

From the repo root Makefile:

```bash
make frontend-install
make frontend-start
make frontend-build
make frontend-test
make frontend-lint
```

## Directory structure

```
frontend/src/
  App.js, routes.js, index.js
  config/           # env-backed config, API endpoints, auth keys
  services/         # Axios client + domain API services
  contexts/         # Auth, Theme, Notification providers
  hooks/            # useAuth, useApi, usePolling, usePermission, …
  guards/           # AuthGuard, RoleGuard, GuestGuard
  layouts/          # Dashboard, Auth, Minimal shells
  components/
    layout/         # Sidebar, Topbar, Footer, Breadcrumbs
    common/         # DataTable, StatusBadge, toasts, skeletons, …
    forensic/       # Domain widgets (Prompt 8+)
  pages/            # Route pages (placeholders until Prompt 8)
  utils/            # constants, permissions, formatters, validators, storage
  __tests__/        # Unit/integration tests + MSW setup
```

## Architecture decisions

1. **Volt base** — Keep Volt’s Bootstrap/Sass layout primitives; strip demo marketing pages; DFAT navigation and forensic pages own the product surface.
2. **Context pattern** — Auth, theme, and notifications are app-wide via providers (order: Theme → Auth → Notification → Router).
3. **Axios service layer** — Single `apiClient` with Bearer tokens, `X-Request-ID`, 401 refresh queue, normalised `{ status, message, details, requestId }` errors.
4. **Lazy routes** — `routes.js` code-splits pages; guards wrap auth/role checks; `/questionnaire` stays public (ethics).
5. **RBAC mirror** — `utils/permissions.js` copies backend `ROLE_PERMISSIONS` exactly (`admin` / `investigator` / `analyst` / `viewer`).

## Backend API dependency

All relative paths are under `REACT_APP_API_BASE_URL` (see `config/api.config.js`):

- **Auth:** `/auth/login` (OAuth2 form), `/auth/register`, `/auth/refresh`, `/auth/logout`, `/auth/logout-all`, `/auth/change-password`
- **Users:** `/users/me`, `/users`, …
- **Health:** `/health`, `/health/ready`, `/health/detailed`
- **Cases / Evidence / Pipeline / AI / Reports / Evaluation:** full inventory in `API_ENDPOINTS`

Login must use `application/x-www-form-urlencoded` (`username` / `password`), not JSON.

## RBAC

| Role | Typical access |
| --- | --- |
| `admin` | All resources via synthetic `all` permission |
| `investigator` | Cases/evidence CRUD-ish, analysis/reports/evaluation create+read |
| `analyst` | Read-heavy + analysis create |
| `viewer` | Reports + evaluation read only |

UI enforcement: `RoleGuard`, `usePermission`, sidebar admin-only links. Server remains authoritative.

## Coding standards

- **Components:** PascalCase files; default export; prefer function components.
- **Hooks:** `useX` naming; one concern per hook; no JSX in data hooks.
- **Services:** Thin Axios wrappers; no React imports.
- **Paths:** Absolute imports from `src` (`jsconfig` `baseUrl`).
- **Tests:** Colocate under `src/__tests__/` mirroring area (`services/`, `hooks/`, `guards/`, …).
- **Styles:** Prefer Volt/Bootstrap utilities; DFAT overrides in `styles/_overrides.scss`.

## License

MIT (Volt React Dashboard attribution retained where required). DFAT application code follows the repository root license.
