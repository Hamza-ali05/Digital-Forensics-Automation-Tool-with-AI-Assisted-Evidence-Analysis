import config from "./index";

/**
 * App-facing settings derived from the shared config object.
 */
export const APP_CONFIG = {
  name: config.appName,
  version: config.appVersion,
  pollingIntervalMs: config.pollingInterval,
  tokenRefreshIntervalMs: config.tokenRefreshInterval,
  maxFileSizeMB: config.maxFileSizeMB,
  debug: config.debug,
};

export default APP_CONFIG;
