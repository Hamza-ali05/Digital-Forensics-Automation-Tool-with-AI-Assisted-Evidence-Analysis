import { rest } from "msw";

import apiClient, { normaliseApiError } from "services/api";
import config from "config";
import { AUTH_CONFIG } from "config/auth.config";
import { server } from "../../test-utils/msw/server";

const API = config.apiBaseUrl;

describe("api client", () => {
  test("test_request_attaches_jwt_token", async () => {
    localStorage.setItem(AUTH_CONFIG.tokenKey, "jwt-test-token");

    let authHeader = null;
    let requestId = null;

    server.use(
      rest.get(`${API}/health`, (req, res, ctx) => {
        authHeader = req.headers.get("Authorization");
        requestId = req.headers.get("X-Request-ID");
        return res(ctx.status(200), ctx.json({ status: "healthy" }));
      })
    );

    await apiClient.get("/health");

    expect(authHeader).toBe("Bearer jwt-test-token");
    expect(requestId).toBeTruthy();
  });

  test("test_401_triggers_refresh", async () => {
    localStorage.setItem(AUTH_CONFIG.tokenKey, "expired-token");
    localStorage.setItem(AUTH_CONFIG.refreshTokenKey, "refresh-token");

    let protectedCalls = 0;
    let refreshCalls = 0;

    server.use(
      rest.get(`${API}/protected`, (req, res, ctx) => {
        protectedCalls += 1;
        const auth = req.headers.get("Authorization");
        if (auth === "Bearer new-access-token") {
          return res(ctx.status(200), ctx.json({ ok: true }));
        }
        return res(ctx.status(401), ctx.json({ detail: "expired" }));
      }),
      rest.post(`${API}/auth/refresh`, (req, res, ctx) => {
        refreshCalls += 1;
        return res(
          ctx.status(200),
          ctx.json({
            access_token: "new-access-token",
            refresh_token: "new-refresh-token",
            token_type: "bearer",
            expires_in: 3600,
          })
        );
      })
    );

    const { data } = await apiClient.get("/protected");

    expect(refreshCalls).toBe(1);
    expect(protectedCalls).toBeGreaterThanOrEqual(2);
    expect(data).toEqual({ ok: true });
    expect(localStorage.getItem(AUTH_CONFIG.tokenKey)).toBe("new-access-token");
  });

  test("test_failed_refresh_redirects_to_login", async () => {
    localStorage.setItem(AUTH_CONFIG.tokenKey, "expired-token");
    localStorage.setItem(AUTH_CONFIG.refreshTokenKey, "bad-refresh");
    window.location.pathname = "/dashboard";

    server.use(
      rest.get(`${API}/protected`, (req, res, ctx) =>
        res(ctx.status(401), ctx.json({ detail: "expired" }))
      ),
      rest.post(`${API}/auth/refresh`, (req, res, ctx) =>
        res(ctx.status(401), ctx.json({ detail: "invalid refresh" }))
      )
    );

    await expect(apiClient.get("/protected")).rejects.toBeTruthy();

    expect(localStorage.getItem(AUTH_CONFIG.tokenKey)).toBeNull();
    expect(window.location.href).toBe("/auth/login");
  });

  test("test_errors_are_normalised", async () => {
    server.use(
      rest.get(`${API}/boom`, (req, res, ctx) =>
        res(
          ctx.status(422),
          ctx.set("x-request-id", "req-123"),
          ctx.json({
            message: "Validation failed",
            details: { field: "name" },
          })
        )
      )
    );

    try {
      await apiClient.get("/boom");
      throw new Error("expected rejection");
    } catch (error) {
      expect(error).toEqual(
        expect.objectContaining({
          status: 422,
          message: "Validation failed",
          details: { field: "name" },
          requestId: "req-123",
        })
      );
    }

    const normalised = normaliseApiError({
      message: "Network Error",
      response: undefined,
    });
    expect(normalised.status).toBe(0);
    expect(normalised.message).toBe("Network Error");
  });
});
