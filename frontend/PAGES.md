# DFAT Frontend Pages

Reference for every routed page: path, access control, API usage, and key UI components.

Routes are defined in `src/routes.js`. Role checks use `RoleGuard` and/or `usePermission` / sidebar `ROUTE_PERMISSIONS`.

| Page | Route | Permissions | API endpoints (via services) | Key components |
|------|-------|-------------|------------------------------|----------------|
| **Login** | `/auth/login` | Guest only (`GuestGuard`) | `auth.service` → login | `AuthLayout`, login form |
| **Register** | `/auth/register` | Guest only | `auth.service` → register | `AuthLayout`, `PasswordStrength` |
| **Questionnaire** | `/questionnaire` | Public (`MinimalLayout`, no auth) | `evaluation.service` → getQuestionnaire, submitQuestionnaire | Likert scales, thank-you state |
| **Dashboard** | `/dashboard` | Authenticated | `cases.service` list; `evidence.service` getStatistics; `pipeline.service` listJobs; `reports.service` getTotal / getJson / getAuditTrail; `health.service` ready | `PageHeader`, `StatCard`, charts (`Bar`/`Doughnut`), `HealthBar` |
| **Profile** | `/profile` | Authenticated | `users.service` getMe; `auth.service` changePassword | Profile form, password change |
| **Case list** | `/cases` | admin, investigator, analyst (`RoleGuard`); create needs cases:create | `cases.service` list, close | `PageHeader`, `DataTable`, filters, `StatusBadge` |
| **Case create** | `/cases/new` | admin, investigator | `cases.service` create | Case form |
| **Case detail** | `/cases/:id` | Authenticated (page-level actions gated) | `cases.service` getById / summary / lifecycle / investigators; `evidence.service`; `pipeline.service`; `users.service` list | Tabs, evidence/pipeline panels, confirm dialogs |
| **Evidence inventory** | `/evidence` | admin, investigator, analyst | `evidence.service` getInventory / statistics; `cases.service` list | `DataTable`, filters |
| **Evidence register** | `/evidence/register` | admin, investigator | `evidence.service` register; `cases.service` list | Upload / register form |
| **Integrity check** | `/evidence/integrity` | admin, investigator, analyst | `evidence.service` verifyIntegrity / getCustody; `cases.service` | Integrity / custody UI |
| **Evidence detail** | `/evidence/:id` | Authenticated | `evidence.service` getDetail / validate / custody; `pipeline.service` listJobs | Detail cards, actions |
| **Pipeline jobs** | `/pipeline` | admin, investigator, analyst | `pipeline.service` listJobs; `cases.service`; `evidence.service` | Job table, status filters |
| **Pipeline run** | `/pipeline/run` | admin, investigator, analyst | `pipeline.service` run; `evidence.service` getInventory; `cases.service`; `ai.service` health | Run form, mode selector |
| **Pipeline detail** | `/pipeline/:jobId` | Authenticated | `pipeline.service` getJob / getProgress / cancel; `reports.service` getJson | Stage progress, polling (`usePolling`), results |
| **Artefact explorer** | `/artefacts/:id` | admin, investigator, analyst | `evidence.service` getInventory; `pipeline.service` listJobs; `reports.service` getJson; `ai.service` explain | Category tabs, `SuspicionFilter`, category tables, `ArtefactDetailModal` |
| **Timeline** | `/artefacts/timeline` | admin, investigator, analyst | Same artefact data path (jobs + report JSON) | Timeline filters, suspicion colouring |
| **IOC dashboard** | `/artefacts/iocs` | admin, investigator, analyst | Report / artefact IOC extraction | IOC tables / filters |
| **AI analysis** | `/ai` | Authenticated | `ai.service` health / classify / summarize / ask / explain | Chat / analysis panels |
| **AI summary** | `/ai/summary` | Authenticated | `reports.service` getJson (narrative) | Summary viewer |
| **Reports list** | `/reports` | Authenticated | `reports.service`; `pipeline.service` listJobs; `cases.service` | Report table, export actions |
| **JSON viewer** | `/reports/json` | Authenticated | `reports.service` getJson | `JSONTreeViewer` |
| **Report detail** | `/reports/:id` | Authenticated | `reports.service` detail / exports / verify / custody / audit / compare; `pipeline.service` | Multi-tab report UI |
| **Evaluation hub** | `/evaluation` | Authenticated | Navigation only | Links to benchmark / performance / usability |
| **Benchmark run** | `/evaluation/benchmark` | Authenticated | `evaluation.service` datasets / run | Dataset picker, run controls |
| **Benchmark history** | `/evaluation/benchmark/history` | Authenticated | `evaluation.service` getResults / getResult | Trend chart, `MetricGauge`, FP/FN lists |
| **Performance** | `/evaluation/performance` | Authenticated | `evaluation.service` performance; `pipeline.service` | Performance charts / baseline |
| **Usability results** | `/evaluation/usability` | admin, investigator | (placeholder / ComingSoon) | Coming soon |
| **System settings** | `/settings` | **admin only** | `health.service` detailed; `ai.service` health / cache stats / clearCache; `pipeline.service` listParsers | Health, AI engine, parsers, DB / config read-only |
| **User management** | `/settings/users` | **admin only** | `users.service` list / getById / deactivate; register via `auth.service` | `DataTable`, register modal, `ConfirmDialog`, `PasswordStrength` |
| **Audit logs** | `/settings/audit` | **admin only** | `audit.service` listAggregated (jobs + report audit trails); `users.service` list | Filters, expandable details, CSV export |
| **Help** | `/help` | Authenticated | None (static); links to `/docs` | Getting started, workflow, roles, FAQ, version |
| **Not found** | `/404` | Public | — | Error page |
| **Server error** | `/500` | Public | — | Error page |

## Admin section notes

- Sidebar shows **Settings**, **User Management**, and **Audit Logs** only when the user role is `admin`.
- Help is available to all authenticated roles.
- Re-exports under `pages/settings/` point at `pages/admin/` implementations for Settings and User Management.

## Tests

Page tests live under `src/__tests__/pages/`.

```bash
npm run test:pages
# or
make frontend-test-pages
```

`StatusBadge` colour coverage: `src/__tests__/components/StatusBadge.test.js`.
