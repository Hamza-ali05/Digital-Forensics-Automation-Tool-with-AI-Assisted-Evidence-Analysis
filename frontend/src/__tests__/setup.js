/**
 * Prompt 7.15 setup entrypoint (discovered under ``__tests__/``).
 * Runtime hooks are registered via ``src/setupTests.js`` → ``test-utils/setup.js``.
 */
import { server, handlers } from "../test-utils/msw/server";

describe("test setup", () => {
  test("msw_server_and_localStorage_are_configured", () => {
    expect(server).toBeTruthy();
    expect(Array.isArray(handlers)).toBe(true);
    expect(typeof localStorage.getItem).toBe("function");
    expect(typeof localStorage.setItem).toBe("function");
  });
});

export { server, handlers };
