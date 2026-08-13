# DFAT Frontend Migration Plan (from Volt React Dashboard)

**Prompt:** 7.1 (document only — **no deletions in this step**)  
**Companion:** [`ARCHITECTURE_AUDIT.md`](./ARCHITECTURE_AUDIT.md)  
**Target product:** Digital Forensics Automation Tool (DFAT) UI consuming Prompts 1–6 APIs

---

## KEEP (adapt for DFAT)

These pieces form the reusable shell and design system. Preserve structure; replace demo content and wiring.

| Asset | Why keep | DFAT adaptation notes |
|-------|----------|------------------------|
| **Dashboard layout** (`Sidebar` + `Navbar` + `content` + `Footer` via `RouteWithSidebar`) | Proven admin shell | Remap nav items; drop Themesberg footer promo; keep responsive collapse |
| **`Preloader`** | Consistent route transition UX | Swap React logo for DFAT mark; drive `show` from real loading state later |
| **`ScrollToTop`** | Hash/Browser router UX | Keep as-is |
| **`@themesberg/react-bootstrap` + Bootstrap 5 SCSS** | Full component library (Card, Table, Modal, Form, Toast, Badge, …) | Prefer these primitives over new CSS frameworks |
| **Sass architecture** (`scss/volt.scss`, `_variables.scss`, layout/component partials) | Theming without ejecting Bootstrap | Override palette in variables / `_overrides` for forensic branding |
| **Responsive breakpoints** | Mobile sidebar + Bootstrap grid | Keep `d-md-none` mobile navbar pattern |
| **Routing infrastructure** (`routes.js` + `HomePage` Switch pattern) | Clear path registry | Replace demo routes with DFAT paths; consider `BrowserRouter` |
| **Table patterns** (`Tables.js`, Bootstrap `Table` usage) | Column layout, pagination, action dropdowns | Generalise into forensic artefact / case / evidence tables (Prompt 8) |
| **Card / widget patterns** (`Widgets.js` `CounterWidget`, chart widgets) | KPI cards for dashboard | Bind to health, pipeline, benchmark metrics |
| **Chart wrappers** (`Charts.js` Chartist Line/Bar/Pie) | Immediate visualisation capability | Feed from evaluation/benchmark APIs **or** swap to Chart.js (see ADAPT) |
| **Notification UI pattern** (`Navbar` dropdown + ListGroup) | Toast/bell affordance | Replace mock `notifications.js` with NotificationContext / API events |
| **Auth page layouts** (`examples/Signin`, `Signup`, …) | Layout/spacing for credential forms | Keep layout chrome; wire real auth (form-urlencoded login) |
| **Font Awesome icon set (solid/regular)** | Dense admin iconography | Keep solid/regular; drop unused brand icons where possible |
| **`simplebar-react` sidebar scroll** | Long nav lists | Keep for forensic section menus |
| **Error page shells** (404 / 500) | Operator-facing failures | Rebrand copy; keep illustrations optionally |

### Tooling keep (with caveats)

| Item | Action |
|------|--------|
| `npm start` / CRA scripts | Keep short-term; document OpenSSL + `--legacy-peer-deps` |
| Testing-library deps | Keep for Prompt 7 tests; upgrade versions later |

---

## REMOVE (demo content — execute in Prompt 7.2+)

Do **not** delete in 7.1. Schedule removal when scaffolding DFAT tree.

### Pages to remove

- Marketing: `Presentation.js`, `Upgrade.js`
- Demo app pages: `Transactions.js`, `Settings.js` (after DFAT settings exists), `tables/BootstrapTables.js` (after forensic tables exist)
- Entire `pages/components/` gallery (17 showcase pages)
- Entire `pages/documentation/` Volt docs (7 pages)
- Auth demos once DFAT auth pages exist (or heavily rewrite in place): social OAuth buttons, “Themesberg” copy
- Upsell / GitHub star chrome in `Footer.js`

### Data & assets to remove

| Path | Reason |
|------|--------|
| `src/data/*` | All mock datasets (charts, tables, transactions, notifications, team, commands, features, pages) |
| `src/assets/img/flags/*` | Unused country flags (~100 SVGs) |
| `src/assets/img/team/*` | Stock portraits |
| `src/assets/img/pages/*` | Demo page screenshots |
| Themesberg / PayPal / presentation mockups | Marketing assets |
| `react-github-btn` usage | External promo |

### Components / deps likely removable after cleanup

- `Code.js`, `CodeEditor.js`, `Documentation.js` — docs playground only
- `react-live`, `react-github-btn` — if no remaining consumers
- Brand icon packages partially unused (`free-brands-svg-icons` if social buttons gone)
- Routes entries for gallery/docs/upgrade/presentation

### Config cleanup

- Reset `package.json` `name`, `homepage`, `repository`, `author` to DFAT
- Remove gh-pages deploy scripts if unused

---

## ADAPT (modify for forensic tool)

### 1. Sidebar navigation → DFAT sections

Replace Themesberg demo links with RBAC-aware sections aligned to the backend API map:

| Section | Typical routes (proposed) | Roles (indicative) |
|---------|---------------------------|--------------------|
| Dashboard | `/` overview (cases, jobs, health) | analyst+ |
| Cases | list / detail / lifecycle actions | analyst+ / investigator+ |
| Evidence | inventory, register, custody, integrity | analyst+ / investigator+ |
| Pipeline | run, jobs, progress, parsers | analyst+ |
| AI Analysis | classify, summarize, explain, ask | analyst+ |
| Reports | view, JSON/narrative, PDF/HTML, verify | analyst+ |
| Evaluation | benchmarks, datasets, usability results | analyst+ / investigator+ |
| Usability survey | public questionnaire (minimal layout) | public |
| Admin | users, AI cache, detailed health | admin |

Implement `RoleGuard` / `usePermission` so viewer/analyst/investigator/admin see appropriate items.

### 2. Colour palette → professional forensic branding

Adapt `scss/volt/_variables.scss` (and optional DFAT `_overrides.scss`):

- Move away from Volt “React cyan” secondary (`#61DAFB`) as brand signal
- Prefer restrained neutrals + one strong accent (e.g. deep slate primary, muted teal/amber for status)
- Map suspicion levels to badge colours: critical / high / medium / low / informational (align with HTML report exporters)
- Avoid purple-glow / consumer dashboard clichés; keep high-contrast for evidence tables

### 3. Authentication pages → DFAT login / register

| Volt today | DFAT target |
|------------|-------------|
| Email field, no submit API | Username + password → `POST /api/v1/auth/login` (OAuth2 form body) |
| Sign-up public demo | Register only for admin/investigator via authenticated API |
| No tokens | Store access + refresh; Axios interceptor refresh on 401 |
| No guards | `AuthGuard`, `GuestGuard`, `RoleGuard` |

Layouts: keep card-centred auth shell; strip social buttons.

### 4. Tables → forensic artefact / evidence / case tables

Generalise patterns from `PageVisitsTable` / `TransactionsTable`:

- Server-driven or client-filtered columns: artefact id, category, suspicion, score, timestamps
- Colour-coded suspicion badges (match reporting HTML)
- Row actions: explain, open report, verify integrity
- Empty / loading / error states (`EmptyState`, `LoadingSpinner` from Prompt 7 architecture)

### 5. Charts → benchmark & pipeline metrics

**Decision required in Prompt 7.x:**

| Option | Pros | Cons |
|--------|------|------|
| **A. Keep Chartist** | Already wired in Volt | Diverges from Prompt 7 preamble (Chart.js) |
| **B. Adopt Chart.js + react-chartjs-2** | Matches preamble; richer ecosystem | Extra dependency; rewrite `Charts.js` |

Recommended for DFAT research UI: **Option B** for evaluation dashboards (precision/recall, TTT, Tobin bar), while optionally keeping Chartist until Prompt 8 pages land.

Data sources: `/evaluation/benchmark/results`, `/evaluation/benchmark/performance`, pipeline progress polling.

### 6. Routing & app entry

- Change `HashRouter` → `BrowserRouter` (proxy API via CRA/`setupProxy` or env base URL)
- Set `homepage: "."` or omit homepage
- Split layouts: `DashboardLayout`, `AuthLayout`, `MinimalLayout` (usability questionnaire)
- Central `routes.js` mirroring DFAT IA

### 7. State & services (greenfield on Volt shell)

Add per Prompt 7 architecture (not in Volt today):

- `services/api.js` (Axios + interceptors)
- Domain services: auth, cases, evidence, pipeline, ai, reports, evaluation, users, health
- `AuthContext`, `NotificationContext`
- Hooks: `useAuth`, `useApi`, `usePolling` (pipeline progress), `usePermission`

### 8. Dependency / Node compatibility (blocking for daily UX)

| Issue | Mitigation (Prompt 7.2+) |
|-------|---------------------------|
| Peer dependency conflict | Commit `.npmrc` with `legacy-peer-deps=true` |
| OpenSSL error on Node 17+ | Document `NODE_OPTIONS=--openssl-legacy-provider` **or** upgrade to Vite / react-scripts 5 |
| 210 npm audit findings | Plan controlled upgrade after shell stabilises |
| React 16 / Router 5 | Upgrade path: React 18 + RR6 in a dedicated prompt if required by Volt-React migration cost |

### 9. package identity

Rename `@themesberg/volt-react-dashboard` → e.g. `dfat-frontend`; update README to DFAT; retain MIT attribution to Themesberg in LICENSE notice.

---

## Suggested execution order (later prompts)

1. **7.2** — Strip REMOVE list; reset homepage; add `.npmrc`; stabilise `npm start`
2. **7.3+** — Config, Axios, AuthContext, guards, DFAT layouts
3. **7.x services** — Wire endpoint map (including deltas vs preamble: JSON-file export, usability export/delete, analysis routes, OAuth2 login form)
4. **Prompt 8** — Forensic pages & domain components under `components/forensic/` and `pages/`

---

## Explicit non-goals of Prompt 7.1

- No file deletions
- No DFAT pages yet
- No API integration yet
- No colour finalisation beyond documenting ADAPT intent

---

## Prompt 7.2 status (completed)

Demo pages, `src/data/*`, marketing assets, and gallery/docs trees removed.
DFAT sidebar + placeholder section routes added. `package.json` renamed to
`dfat-frontend@0.1.0`. `sass` pinned to `1.32.13` for CRA production builds.
`.npmrc` sets `legacy-peer-deps=true`. `npm run build` succeeds.

*Proceed to Prompt 7.3+ for config/API/auth scaffolding.*
