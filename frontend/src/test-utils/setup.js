import "@testing-library/jest-dom/extend-expect";

import { server } from "./msw/server";

/**
 * DFAT Jest setup — localStorage mock + MSW lifecycle.
 */

const localStorageMock = (() => {
  let store = {};
  return {
    getItem: (key) =>
      Object.prototype.hasOwnProperty.call(store, key) ? store[key] : null,
    setItem: (key, value) => {
      store[key] = String(value);
    },
    removeItem: (key) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
    key: (index) => Object.keys(store)[index] || null,
    get length() {
      return Object.keys(store).length;
    },
  };
})();

Object.defineProperty(window, "localStorage", {
  value: localStorageMock,
  writable: true,
});

Object.defineProperty(global, "localStorage", {
  value: localStorageMock,
  writable: true,
});

if (!global.crypto) {
  global.crypto = {};
}
if (typeof global.crypto.randomUUID !== "function") {
  let seq = 0;
  global.crypto.randomUUID = () => {
    seq += 1;
    return `00000000-0000-4000-8000-${String(seq).padStart(12, "0")}`;
  };
}

delete window.location;
window.location = {
  href: "http://localhost/",
  origin: "http://localhost",
  protocol: "http:",
  host: "localhost",
  hostname: "localhost",
  port: "",
  pathname: "/",
  search: "",
  hash: "",
  assign: jest.fn(),
  replace: jest.fn(),
  reload: jest.fn(),
};

if (typeof Element !== "undefined" && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = jest.fn();
}

beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => {
  server.resetHandlers();
  localStorage.clear();
  window.location.href = "http://localhost/";
  window.location.origin = "http://localhost";
  window.location.pathname = "/";
  window.location.search = "";
});
afterAll(() => server.close());

export { server };
