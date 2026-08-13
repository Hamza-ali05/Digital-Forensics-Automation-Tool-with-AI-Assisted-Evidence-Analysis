import { rest } from "msw";

import authService from "services/auth.service";
import config from "config";
import { AUTH_CONFIG } from "config/auth.config";
import { server } from "../../test-utils/msw/server";

const API = config.apiBaseUrl;

describe("auth.service", () => {
  test("test_login_stores_tokens", async () => {
    server.use(
      rest.post(`${API}/auth/login`, (req, res, ctx) =>
        res(
          ctx.status(200),
          ctx.json({
            access_token: "access-abc",
            refresh_token: "refresh-xyz",
            token_type: "bearer",
            expires_in: 3600,
          })
        )
      ),
      rest.get(`${API}/users/me`, (req, res, ctx) =>
        res(
          ctx.status(200),
          ctx.json({
            id: "u1",
            username: "alice",
            email: "alice@example.com",
            full_name: "Alice",
            role_name: "admin",
            is_active: true,
            created_at: "2026-01-01T00:00:00Z",
          })
        )
      )
    );

    const user = await authService.login("alice", "LifeCyclePass1!");

    expect(user.username).toBe("alice");
    expect(localStorage.getItem(AUTH_CONFIG.tokenKey)).toBe("access-abc");
    expect(localStorage.getItem(AUTH_CONFIG.refreshTokenKey)).toBe("refresh-xyz");
    expect(JSON.parse(localStorage.getItem(AUTH_CONFIG.userKey)).role_name).toBe(
      "admin"
    );
  });

  test("test_logout_clears_state", async () => {
    localStorage.setItem(AUTH_CONFIG.tokenKey, "access");
    localStorage.setItem(AUTH_CONFIG.refreshTokenKey, "refresh");
    localStorage.setItem(
      AUTH_CONFIG.userKey,
      JSON.stringify({ username: "alice", role_name: "admin" })
    );

    server.use(
      rest.post(`${API}/auth/logout`, (req, res, ctx) => res(ctx.status(204)))
    );

    await authService.logout();

    expect(localStorage.getItem(AUTH_CONFIG.tokenKey)).toBeNull();
    expect(localStorage.getItem(AUTH_CONFIG.refreshTokenKey)).toBeNull();
    expect(localStorage.getItem(AUTH_CONFIG.userKey)).toBeNull();
  });

  test("test_isAuthenticated_checks_token", () => {
    expect(authService.isAuthenticated()).toBe(false);

    localStorage.setItem(AUTH_CONFIG.tokenKey, "access");
    localStorage.setItem(
      AUTH_CONFIG.tokenExpiryKey,
      String(Date.now() + 60_000)
    );
    expect(authService.isAuthenticated()).toBe(true);

    localStorage.setItem(
      AUTH_CONFIG.tokenExpiryKey,
      String(Date.now() - 1000)
    );
    expect(authService.isAuthenticated()).toBe(false);
  });

  test("test_getRole_extracts_from_user", () => {
    expect(authService.getRole()).toBeNull();
    localStorage.setItem(
      AUTH_CONFIG.userKey,
      JSON.stringify({ username: "bob", role_name: "viewer" })
    );
    expect(authService.getRole()).toBe("viewer");
  });
});
