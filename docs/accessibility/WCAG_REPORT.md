# DFAT WCAG 2.1 AA accessibility report

**Scope:** Login, Dashboard, Cases, Evidence detail, Questionnaire, Report detail  
**Standard:** WCAG 2.1 Level AA  
**Tooling:** `@axe-core/playwright` 4.13, Chromium, Playwright E2E  
**Date:** 17 August 2026  

Automated scans fail the build on **critical** and **serious** axe impacts. Moderate and minor findings are logged for review.

## How to run

```bash
make test-accessibility   # frontend/e2e/accessibility.spec.js (6 pages)
make test-responsive      # frontend/e2e/responsive.spec.js (4 viewports)
```

Both targets start the API (`:8000`) and CRA frontend (`:3000`) via Playwright `webServer`.

## Audit results (blocking)

| Page | Route | Critical/serious |
|------|--------|------------------|
| Login | `/auth/login` | 0 |
| Dashboard | `/dashboard` | 0 |
| Case list | `/cases` | 0 |
| Evidence detail | `/evidence/{id}` | 0 |
| Questionnaire | `/questionnaire` | 0 |
| Report detail | `/reports/{id}` | 0 |

Responsive checks (375×667, 768×1024, 1920×1080):

- Sidebar collapses on mobile; hamburger is visible; content uses full width
- Data tables keep `overflow-x: auto` and a 640px minimum width
- Dashboard statistic cards stack on mobile and sit in a row on desktop
- Login and case-search controls fill most of the mobile content width

## Fixes applied

### Structure and keyboard

- Skip-to-content link on auth, dashboard, and questionnaire layouts, targeting `#main-content`
- Page titles via `usePageTitle`; primary headings are `h1`
- Associated labels / `htmlFor` on login, case filters, and questionnaire fields
- `aria-label` on icon-only controls (sidebar toggle, notifications, user menu, close navigation, search clear)
- Table captions, `aria-sort` on sortable headers, pagination `nav`
- Likert scales use `fieldset` / `legend` / `aria-labelledby`
- `:focus-visible` outlines on links, buttons, and form controls; white outline on sidebar links

### Colour contrast (1.4.3)

Volt grey `#66799e` on white or `#f5f8fb` was 4.11–4.38:1 (below 4.5:1). Updates:

- Form text colour set to `#262b40`; placeholders to `#495057`
- Muted copy on light surfaces forced to `#495057` (not applied inside the dark sidebar)
- Breadcrumb links use `#262b40`
- Theme tokens darkened so filled buttons still pass with white text: success `#047857`, danger `#c53030`, secondary `#155e75`
- Warning buttons use dark text on yellow
- Status badges pick white or `#262b40` from background luminance

### Responsive

- Volt `.sidebar { display: block }` no longer overrides Bootstrap collapse on viewports below `md` (`display: none !important` when not `.show`)
- `.content` is full width on mobile (`margin-left: 0`)
- `.table-responsive` / `.dfat-data-table` scroll horizontally; tables have `min-width: 640px`
- Form controls set to 100% width below 768px

## Remaining known issues (non-blocking)

These are **moderate** (or lower) and do not fail the E2E gate:

1. **Heading order** — Some Volt card titles still skip from `h1` to `h5` visually (Dashboard/Report cards). Evidence detail card titles were promoted to `h2` with `h5` styling. Further pages can follow the same pattern.
2. **Duplicate breadcrumb landmarks** — Compact topbar crumbs and `PageHeader` crumbs both expose `nav`. They now have distinct labels (`Toolbar breadcrumb` / `Page breadcrumb`). Compact crumbs could be removed later if UX allows a single trail.
3. **Decorative charts** — Chart.js canvases expose `role="img"` with `aria-label`. Screen-reader users still get less than a data table; a text summary would be an enhancement.
4. **Third-party widgets** — `react-datetime` date filters and SimpleBar may add extra generic roles. Not flagged as serious on the audited pages.
5. **Colour is not the only status cue** — Status badges now meet contrast, but colour-only meaning remains; keep the text label (already present).

## WCAG 2.1 AA mapping (audited flows)

| Criterion | Status on key pages | Notes |
|-----------|---------------------|--------|
| 1.1.1 Non-text content | Pass (automated) | Icon-only controls named; FA icons `aria-hidden`; login illustration is CSS background |
| 1.3.1 Info and relationships | Pass (automated) | Labels, headings, table captions |
| 1.4.3 Contrast (minimum) | Pass (automated) | See token/CSS changes above |
| 1.4.4 Resize / 1.4.10 Reflow | Pass (manual E2E) | Mobile 375px layouts; no loss of primary content |
| 2.1.1 Keyboard | Pass (spot-check + focus CSS) | Skip link, sortable headers, dropdowns |
| 2.4.1 Bypass blocks | Pass | Skip to main content |
| 2.4.2 Page titled | Pass | `usePageTitle` + default document title |
| 2.4.4 Link purpose | Pass (automated) | Stat cards expose `aria-label` with title and value |
| 2.4.7 Focus visible | Pass | Global `:focus-visible` |
| 3.3.2 Labels or instructions | Pass (automated) | Login, questionnaire, case filters |
| 4.1.2 Name, Role, Value | Pass (automated) | Buttons, radios, comboboxes |

## Components touched

Layouts (`AuthLayout`, `DashboardLayout`, `MinimalLayout`), `Sidebar`, `Topbar`, `SkipToContent`, `PageHeader`, `DataTable`, `SearchInput`, `StatCard`, `StatusBadge`, `EmptyState`, Login, Questionnaire, Case list, Evidence detail, `frontend/src/styles/custom.scss`, `frontend/src/styles/_variables.scss`.
