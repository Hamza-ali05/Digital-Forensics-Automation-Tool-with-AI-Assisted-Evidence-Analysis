# Changelog

All notable changes to the DFAT frontend will be documented in this file.

## [0.1.0] — 2026-08-13

### Added

- Initial frontend architecture on Volt React Dashboard (Bootstrap 5).
- Axios API client with JWT interceptors, refresh handling, and normalised errors.
- Auth context/service, RBAC guards, and permission helpers mirroring backend roles.
- Theme and notification contexts; reusable common components and hooks.
- Route tree with lazy-loaded Prompt 8 placeholders (including public `/questionnaire`).
- Layout shell (Sidebar, Topbar, Footer, Breadcrumbs) with health indicators.
- Formatters, validators, and `dfat_`-scoped storage helpers.
- Jest + Testing Library + MSW foundational test suite.
- Makefile targets: `frontend-install`, `frontend-start`, `frontend-build`, `frontend-test`, `frontend-lint`.
