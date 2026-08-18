/**
 * CRA automatically loads this file before tests.
 * Set absolute API base before any module reads config (Node axios needs it).
 */
require("./test-utils/env");
require("./test-utils/setup");
