import { rest } from "msw";
import { setupServer } from "msw/node";

import config from "config";

const API = config.apiBaseUrl;

/**
 * Shared MSW handlers for DFAT API mocking in Jest.
 */
export const handlers = [
  rest.post(`${API}/auth/login`, (req, res, ctx) =>
    res(
      ctx.status(200),
      ctx.json({
        access_token: "access-token",
        refresh_token: "refresh-token",
        token_type: "bearer",
        expires_in: 3600,
      })
    )
  ),
  rest.post(`${API}/auth/refresh`, (req, res, ctx) =>
    res(
      ctx.status(200),
      ctx.json({
        access_token: "new-access-token",
        refresh_token: "new-refresh-token",
        token_type: "bearer",
        expires_in: 3600,
      })
    )
  ),
  rest.post(`${API}/auth/logout`, (req, res, ctx) => res(ctx.status(204))),
  rest.get(`${API}/users/me`, (req, res, ctx) =>
    res(
      ctx.status(200),
      ctx.json({
        id: "user-1",
        username: "investigator",
        email: "investigator@example.com",
        full_name: "Test Investigator",
        role_name: "investigator",
        is_active: true,
        last_login: "2026-06-25T14:30:00Z",
        created_at: "2026-01-01T00:00:00Z",
      })
    )
  ),
  rest.get(`${API}/health`, (req, res, ctx) =>
    res(ctx.status(200), ctx.json({ status: "healthy" }))
  ),
];

export const server = setupServer(...handlers);
