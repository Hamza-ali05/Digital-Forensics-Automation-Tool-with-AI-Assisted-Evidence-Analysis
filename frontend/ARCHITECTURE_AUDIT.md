# Volt React Dashboard — Architecture Audit (DFAT Prompt 7.1)

**Source:** [themesberg/volt-react-dashboard](https://github.com/themesberg/volt-react-dashboard) v1.0.1  
**Audited:** 2026-08-10  
**Host:** Node.js v22.19.0 / npm 10.9.3  
**Purpose:** Baseline inventory before DFAT frontend adaptation. No files deleted in this prompt.

---

## 0. Install & Dev-Server Verification

| Step | Result | Notes |
|------|--------|-------|
| `git clone … frontend` | OK | Nested `.git` removed so DFAT owns history |
| `npm install` | **Fails** without flags | `ERESOLVE`: `react-chartist@0.14.4` peers `chartist@^0.10.1` but root pins `chartist@^0.11.4` |
| `npm install --legacy-peer-deps` | OK | 2044 packages; **210** reported vulnerabilities (CRA 3 / webpack 4 stack) |
| `npm start` (Node 22) | **Fails** | `error:0308010C:digital envelope routines::unsupported` (OpenSSL 3 vs webpack 4) |
| `NODE_OPTIONS=--openssl-legacy-provider npm start` | **OK** | Compiles with ESLint/Sass warnings; WDS on port 3000 |

**Recommended local start (Windows PowerShell):**

```powershell
cd frontend
$env:BROWSER = "none"
$env:NODE_OPTIONS = "--openssl-legacy-provider"
npm start --legacy-peer-deps   # or ensure .npmrc has legacy-peer-deps=true later
```

**Additional warnings observed:**

- Dart Sass deprecations (`@import`, `lighten`/`darken`, legacy JS API) — hundreds of messages
- ESLint: `Presentation.js` missing `rel="noopener noreferrer"`; unused imports in `Footer.js`
- `package.json` `"homepage": "https://demo.themesberg.com/volt-react-dashboard"` causes CRA public-path redirects under `/volt-react-dashboard` (must reset for DFAT)
- Outdated `caniuse-lite` browserslist database

**Stack age note:** React 16.13 + `react-scripts` 3.4.3 + React Router 5. Prompt 7 preamble assumed React 17+, React Router 6, and Chart.js — **Volt ships Chartist + RR5**. Migration plan covers upgrade decisions.

---

## 1. Directory Listing (`src/` excluding `node_modules`)

```text
src/
├── index.js                          # Entry: HashRouter + HomePage
├── routes.js                         # Path constants object
├── assets/
│   ├── img/                          # Brand, favicon, flags (100+ SVGs), illustrations,
│   │                                 # page photos, team portraits, tech logos, Themesberg assets
│   └── syntax-themes/                # Prism themes: ghcolors.json, xonokai.json
├── components/                       # Shared UI building blocks (14 modules)
├── data/                             # Static demo JSON/JS datasets (8 modules)
├── pages/
│   ├── HomePage.js                   # Route Switch + layout wrappers
│   ├── Presentation.js               # Marketing landing
│   ├── Settings.js / Transactions.js / Upgrade.js
│   ├── components/                   # Bootstrap component demo pages (17)
│   ├── dashboard/DashboardOverview.js
│   ├── documentation/                # Template docs (7)
│   ├── examples/                     # Auth + error demos (7)
│   └── tables/BootstrapTables.js
└── scss/
    ├── volt.scss                     # Main stylesheet entry
    └── volt/                         # Variables, components, layout, themes, vendor (Chartist)
```

Root also contains: `public/`, `package.json`, `README.md`, `LICENSE.md`, Themesberg docs assets.

---

## 2. Pages / Routes and Purpose

Routing is defined in `src/routes.js` (path map) and wired in `src/pages/HomePage.js` (`Switch` + `Route`).

### Layout wrappers

| Wrapper | Purpose |
|---------|---------|
| `RouteWithLoader` | Full-page routes; shows `Preloader` ~1s then page (no sidebar) |
| `RouteWithSidebar` | App shell: `Preloader` + `Sidebar` + `Navbar` + page + `Footer` |

### Application / demo pages

| Route key | Path | Component | Purpose |
|-----------|------|-----------|---------|
| Presentation | `/` | `Presentation` | Marketing landing / product pitch |
| DashboardOverview | `/dashboard/overview` | `DashboardOverview` | Demo KPI widgets + charts |
| Transactions | `/transactions` | `Transactions` | Demo transaction table page |
| Settings | `/settings` | `Settings` | Demo profile/settings forms |
| Upgrade | `/upgrade` | `Upgrade` | Themesberg pro upsell |
| BootstrapTables | `/tables/bootstrap-tables` | `BootstrapTables` | Table pattern showcase |

### Auth / error examples (`RouteWithLoader`)

| Route key | Path | Component | Purpose |
|-----------|------|-----------|---------|
| Signin | `/examples/sign-in` | `Signin` | Static email/password UI (no API) |
| Signup | `/examples/sign-up` | `Signup` | Static registration UI |
| ForgotPassword | `/examples/forgot-password` | `ForgotPassword` | Static recovery UI |
| ResetPassword | `/examples/reset-password` | `ResetPassword` | Static reset UI |
| Lock | `/examples/lock` | `Lock` | Screen-lock demo |
| NotFound | `/examples/404` | `NotFound` | 404 page |
| ServerError | `/examples/500` | `ServerError` | 500 page |

### Component gallery (`/components/*`)

Accordion, Alerts, Badges, Breadcrumbs, Buttons, Forms, Modals, Navs, Navbars, Pagination, Popovers, Progress, Tables, Tabs, Tooltips, Toasts — each is a **documentation showcase page**, not production DFAT UI.

### Documentation (`/documentation/*`)

DocsOverview, DocsDownload, DocsQuickStart, DocsLicense, DocsFolderStructure, DocsBuild, DocsChangelog — Volt template documentation.

**Catch-all:** unmatched paths `Redirect` → `/examples/404`.

---

## 3. Reusable Components and Props

Located in `src/components/`.

| Module | Export | Props / API | Notes |
|--------|--------|-------------|-------|
| `Sidebar.js` | default | none (reads `useLocation`) | Nested `NavItem`: `title`, `link`, `external`, `target`, `icon`, `image`, `badgeText`, `badgeBg`, `badgeColor`; `CollapsableNavItem`: `eventKey`, `title`, `icon`, `children` |
| `Navbar.js` | default | unused `props` | Local notification state from `data/notifications`; nested `Notification`: `link`, `sender`, `image`, `time`, `message`, `read` |
| `Footer.js` | default | `showSettings`, `toggleSettings` | Themesberg promo + GitHub star; year via `moment-timezone` |
| `Preloader.js` | default | `show: boolean` | Full-screen loader; inverted CSS class (`show` prop false → CSS class `show` hides) |
| `ScrollToTop.js` | default | none | Scrolls window on pathname change |
| `Charts.js` | `SalesValueChart` | none | Hard-coded Chartist line |
| | `SalesValueChartphone` | none | Mobile line chart |
| | `CircleChart` | `series[]`, `donutWidth` | Donut/pie |
| | `BarChart` | `labels[]`, `series[]`, `chartClassName` | Bar chart |
| `Tables.js` | `PageVisitsTable`, `PageTrafficTable`, `RankingTable`, `TransactionsTable`, `CommandsTable` | mostly none (demo data imports) | Row subcomponents take row fields from `data/*` |
| `Widgets.js` | `ProfileCardWidget` | none | Demo profile |
| | `ChoosePhotoWidget` | `title`, `photo` | Photo upload card demo |
| | `CounterWidget` | `icon`, `iconColor`, `category`, `title`, `period`, `percentage` | KPI card |
| | `CircleChartWidget` | `title`, `data[]` | Chart + legend |
| | `BarChartWidget` | `title`, `value`, `percentage`, `data[]` | Orders widget |
| | `TeamMembersWidget`, `ProgressTrackWidget`, `RankingWidget`, `AcquisitionWidget` | none / internal | Demo lists |
| | `SalesValueWidget`, `SalesValueWidgetPhone` | `title`, `value`, `percentage` | Sales KPI + chart |
| `Forms.js` | `GeneralInfoForm` | none | Demo profile form + `react-datetime` |
| `Progress.js` | default | `label`, `variant`, `value`, `type` (`label`\|`tooltip`), `size` | Progress bar wrapper; random value if omitted |
| `AccordionComponent.js` | default | `defaultKey`, `data[]` (`id`, `eventKey`, `title`, `description`), `className` | Data-driven accordion |
| `Code.js` | default | `code`, `language` | Prism highlight + copy |
| `CodeEditor.js` | default | `code`, `language`, `scope`, `imports`, `maxHeight` | `react-live` playground |
| `Documentation.js` | default | `title`, `description`, `example`, `imports`, `scope`, `maxHeight` | Docs page section wrapper |

UI primitives (Button, Card, Table, Modal, Toast, etc.) come from **`@themesberg/react-bootstrap`** (Bootstrap 5 React bindings), not custom wrappers.

---

## 4. Routing Structure

- **Router:** `react-router-dom` **v5** with **`HashRouter`** (`src/index.js`)
- **Route table:** `src/routes.js` exports `Routes` object of `{ path }` entries
- **Composition:** `HomePage` uses `Switch` + exact `Route`s
- **No route guards:** every route is public; no JWT/session checks
- **Hash URLs:** e.g. `/#/dashboard/overview` (good for static hosting; DFAT may prefer `BrowserRouter`)

---

## 5. State Management

| Concern | Approach |
|---------|----------|
| Global store | **None** (no Redux, MobX, Zustand, Context API) |
| Local UI | `useState` / `useEffect` in pages and layout wrappers |
| Persistence | `localStorage` key `settingsVisible` (footer theme panel) |
| Notifications | In-memory array copied from `data/notifications.js` in `Navbar` |
| Forms | Uncontrolled / local state only; no form library |

DFAT will need new contexts (`AuthContext`, etc.) — Volt does not provide them.

---

## 6. API / Data Fetching Patterns

**None.** No Axios/Fetch clients, no environment-based API base URL, no React Query/SWR.

All lists/charts load from static modules under `src/data/`:

| File | Contents |
|------|----------|
| `charts.js` | `trafficShares`, `totalOrders` |
| `tables.js` | `pageVisits`, `pageTraffic`, `pageRanking` |
| `transactions.js` | Fake bank/commerce transactions |
| `notifications.js` | Topbar notification feed |
| `teamMembers.js` | Team list for widgets |
| `commands.js` | CLI-style table demo rows |
| `features.js` / `pages.js` | Presentation / marketing content |

---

## 7. Authentication Flow

**Demo-only.** Sign-in / sign-up / forgot / reset / lock pages are presentational:

- No credential submission handlers wired to a backend
- No token storage
- No protected routes
- Social buttons (Facebook/GitHub/Twitter) are non-functional UI chrome

DFAT must replace these with JWT login (OAuth2 password form), refresh interceptors, and role guards per Prompts 2–6 API surface.

---

## 8. Styling Approach

| Layer | Detail |
|-------|--------|
| Entry | `src/scss/volt.scss` imported from `index.js` |
| Framework | Bootstrap **5.0.0-beta1** SCSS + Volt overrides |
| Variables | `scss/volt/_variables.scss` — greys, `$primary: #262B40`, `$secondary: #61DAFB`, `$tertiary: #1B998B`, Chartist series colours |
| Themes | `themes/_variables-dark.scss`, `_variables-light.scss`, `_variables-sunset.scss` (partial theme support) |
| Layout SCSS | `_sidebar.scss`, `_sidenav.scss`, `_navbar.scss`, `_footer.scss`, `_section.scss` |
| Components | Large set under `scss/volt/components/` (cards, tables, preloader, charts, …) |
| Vendor | Chartist SCSS, datepicker, headroom, prism, wizard |
| Extra CSS | `react-datetime/css/react-datetime.css` |
| Icons | Font Awesome 5 via `@fortawesome/*` SVG React components |
| Breakpoints | Standard Bootstrap responsive utilities (`d-md-none`, grid `Col`, etc.) |

---

## 9. Chart / Visualisation Components

| Library | Role |
|---------|------|
| **chartist** + **react-chartist** | Primary charts (Line, Bar, Pie/Donut) |
| **chartist-plugin-tooltips-updated** | Hover tooltips |

**Not present:** Chart.js / react-chartjs-2 (despite DFAT Prompt 7 preamble). Benchmark visualisation should either:

1. Adapt Chartist wrappers in `Charts.js`, or  
2. Introduce Chart.js in a later prompt and retire Chartist.

Available reusable chart exports: `SalesValueChart`, `SalesValueChartphone`, `CircleChart`, `BarChart`, plus widget compositions in `Widgets.js`.

---

## 10. Third-Party Dependencies (`package.json`)

### Runtime / UI

| Package | Version | Role |
|---------|---------|------|
| `react` / `react-dom` | ^16.13.1 | UI runtime |
| `react-scripts` | 3.4.3 | CRA build (webpack 4) |
| `react-router-dom` | ^5.2.0 | Routing |
| `react-router-hash-link` | ^2.3.1 | Hash fragment links |
| `@themesberg/react-bootstrap` | ^1.4.1 | Bootstrap 5 React components |
| `bootstrap` | 5.0.0-beta1 | CSS/SCSS |
| `sass` | ^1.50.0 | Styles compilation |
| `@fortawesome/fontawesome-svg-core` + free solid/regular/brands | ^1.2.36 / ^5.15.4 | Icons |
| `@fortawesome/react-fontawesome` | ^0.1.17 | Icon React bindings |
| `chartist` | ^0.11.4 | Charts |
| `react-chartist` | ^0.14.4 | React Chartist bridge |
| `chartist-plugin-tooltips-updated` | ^0.1.4 | Chart tooltips |
| `simplebar-react` | ^2.3.0 | Sidebar custom scrollbar |
| `react-transition-group` | ^4.4.1 | Sidebar CSSTransition |
| `moment-timezone` | ^0.5.31 | Dates / footer year |
| `react-datetime` | ^3.0.4 | Date picker |
| `react-copy-to-clipboard` | ^5.0.3 | Code copy |
| `react-live` | ^2.2.3 | Live code demos |
| `react-github-btn` | ^1.2.0 | GitHub star button |

### Dev / test (bundled as dependencies in this template)

| Package | Version |
|---------|---------|
| `@testing-library/jest-dom` | ^4.2.4 |
| `@testing-library/react` | ^9.3.2 |
| `@testing-library/user-event` | ^7.1.2 |

### Scripts

`start`, `build`, `build-local`, `test`, `eject`, `predeploy`/`deploy` (gh-pages).

---

## 11. Architectural Implications for DFAT

1. **Keep shell, replace content** — Sidebar/Navbar/Preloader/SCSS are the valuable assets.
2. **Introduce a real API layer** — Volt has zero HTTP; DFAT services must be greenfield.
3. **Introduce auth & RBAC** — no guards today.
4. **Plan CRA/React upgrade** — Node 22 + OpenSSL workaround is temporary; later prompts should move to Vite or CRA5+/React 18.
5. **Chart stack decision** — Chartist now vs Chart.js as specified in the Prompt 7 preamble.
6. **Reset `homepage`** — required before usable localhost browsing without path loops.
7. **Do not treat gallery/docs pages as product surface** — strip in Prompt 7.2.

---

*End of architecture audit. See `MIGRATION_PLAN.md` for KEEP / REMOVE / ADAPT.*
