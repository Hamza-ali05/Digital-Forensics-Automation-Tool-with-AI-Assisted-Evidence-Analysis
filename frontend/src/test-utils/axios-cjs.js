/* eslint-disable global-require, import/no-extraneous-dependencies */
/**
 * Jest-only axios shim. CRA's Jest file transform treats ``.cjs`` as an asset
 * (returns the filename string), so we load the Node build via createRequire.
 */
const path = require("path");
const { createRequire } = require("module");

const requireFromHere = createRequire(__filename);
const axiosPath = path.join(
  __dirname,
  "..",
  "..",
  "node_modules",
  "axios",
  "dist",
  "node",
  "axios.cjs"
);

const axios = requireFromHere(axiosPath);

module.exports = axios;
module.exports.default = axios;
module.exports.__esModule = true;
