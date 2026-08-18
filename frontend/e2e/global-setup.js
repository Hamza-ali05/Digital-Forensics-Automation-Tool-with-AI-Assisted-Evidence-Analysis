const { spawnSync } = require("child_process");
const path = require("path");
const { API_BASE, investigator } = require("./helpers/credentials");

const API_HEALTH = "http://127.0.0.1:8000/api/v1/health";
const REPO_ROOT = path.resolve(__dirname, "../..");

async function waitForHealth(url, attempts = 90) {
  for (let i = 0; i < attempts; i += 1) {
    try {
      const res = await fetch(url);
      if (res.ok) return;
    } catch {
      // retry
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

async function canLogin() {
  const body = new URLSearchParams();
  body.set("username", investigator.username);
  body.set("password", investigator.password);
  try {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    return res.ok;
  } catch {
    return false;
  }
}

/**
 * Seed development users/cases once the API webServer is healthy.
 * Soft-fails when users already exist and login still works (seed can time out
 * under heavy SQLite audit load on Windows).
 */
module.exports = async function globalSetup() {
  await waitForHealth(API_HEALTH);
  const result = spawnSync("python", ["scripts/seed_dev_data.py"], {
    cwd: REPO_ROOT,
    env: {
      ...process.env,
      PYTHONPATH: path.join(REPO_ROOT, "src"),
      DFAT_API_BASE: API_BASE,
    },
    encoding: "utf8",
    timeout: 120_000,
  });
  if (result.stdout) process.stdout.write(result.stdout);
  if (result.stderr) process.stderr.write(result.stderr);
  if (result.status !== 0) {
    if (await canLogin()) {
      console.warn(
        "seed_dev_data.py failed, but investigator login works — continuing E2E."
      );
      return;
    }
    throw new Error(`seed_dev_data.py failed with exit ${result.status}`);
  }
};
