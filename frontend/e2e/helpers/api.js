const { API_BASE, investigator } = require("./credentials");

async function sleep(ms) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Obtain an OAuth2 access token from the live API.
 */
async function apiLogin(
  username = investigator.username,
  password = investigator.password
) {
  const body = new URLSearchParams();
  body.set("username", username);
  body.set("password", password);
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!res.ok) {
    throw new Error(`API login failed: ${res.status} ${await res.text()}`);
  }
  const data = await res.json();
  return data.access_token;
}

async function apiGet(token, path) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    throw new Error(`GET ${path} failed: ${res.status} ${await res.text()}`);
  }
  return res.json();
}

async function apiPost(token, path, json = {}, attempts = 6) {
  let lastError = null;
  for (let i = 0; i < attempts; i += 1) {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(json),
    });
    if (res.ok) {
      const text = await res.text();
      return text ? JSON.parse(text) : {};
    }
    const body = await res.text();
    lastError = new Error(`POST ${path} failed: ${res.status} ${body}`);
    if (res.status === 429) {
      await sleep(12_000);
      continue;
    }
    throw lastError;
  }
  throw lastError;
}

async function getMe(token) {
  return apiGet(token, "/users/me");
}

/**
 * Ensure at least one OPEN/ACTIVE case exists (required for evidence registration).
 */
async function ensureOpenCase(token) {
  const list = await apiGet(token, "/cases");
  const cases = list.cases || [];
  const eligible = cases.find((c) =>
    ["open", "active"].includes(String(c.status || "").toLowerCase())
  );
  if (eligible) return eligible;

  const me = await getMe(token);
  const userId = me.id || me.user_id;
  const created = await apiPost(token, "/cases", {
    case_name: `E2E Case ${Date.now()}`,
    description: "Auto-created for Playwright E2E",
  });
  const caseId = created.case_id;
  await apiPost(token, `/cases/${caseId}/investigators`, {
    user_id: userId,
    role: "lead",
  });
  await apiPost(token, `/cases/${caseId}/open`, {});
  try {
    await apiPost(token, `/cases/${caseId}/activate`, {});
  } catch {
    // OPEN is still eligible for evidence registration.
  }
  return apiGet(token, `/cases/${caseId}`);
}

/**
 * Register sample evidence via API; returns the evidence payload.
 */
async function ensureValidatedEvidence(token, filePath) {
  const inventory = await apiGet(token, "/evidence/inventory");
  const items = inventory.items || inventory.evidence || [];
  const validated = items.find(
    (item) => String(item.status || "").toLowerCase() === "validated"
  );
  if (validated) return validated;
  const processed = items.find(
    (item) => String(item.status || "").toLowerCase() === "processed"
  );
  if (processed) return processed;

  const openCase = await ensureOpenCase(token);
  return apiPost(token, "/evidence/register", {
    file_path: filePath,
    case_id: openCase.case_id,
    evidence_type: "disk_image",
    description: "E2E registered evidence",
  });
}

/**
 * Wait until a pipeline job reaches a terminal status.
 */
async function waitForJob(token, jobId, timeoutMs = 120_000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const job = await apiGet(token, `/pipeline/${jobId}`);
    const status = String(job.status || "").toLowerCase();
    if (["completed", "failed", "cancelled", "error"].includes(status)) {
      return job;
    }
    await sleep(2000);
  }
  throw new Error(`Job ${jobId} did not finish within ${timeoutMs}ms`);
}

/**
 * Ensure at least one completed pipeline report exists and is fetchable.
 */
async function ensureCompletedReport(token, filePath) {
  const jobsPayload = await apiGet(token, "/pipeline/jobs");
  const list = Array.isArray(jobsPayload)
    ? jobsPayload
    : jobsPayload.jobs || jobsPayload.items || [];

  for (const job of list) {
    if (
      job.report_id &&
      String(job.status || "").toLowerCase() === "completed"
    ) {
      try {
        await apiGet(token, `/reports/${job.report_id}`);
        return job;
      } catch {
        // Stale job.report_id without a persisted report — keep looking.
      }
    }
  }

  const evidence = await ensureValidatedEvidence(token, filePath);
  const started = await apiPost(token, "/pipeline/run", {
    evidence_id: evidence.evidence_id,
    case_id: evidence.case_id,
    mode: "full",
    use_fallback: true,
  });
  const finished = await waitForJob(token, started.job_id, 180_000);
  if (!finished.report_id) {
    throw new Error(
      `Pipeline job ${started.job_id} finished as ${finished.status} without report_id`
    );
  }
  await apiGet(token, `/reports/${finished.report_id}`);
  return finished;
}

module.exports = {
  apiLogin,
  apiGet,
  apiPost,
  getMe,
  ensureOpenCase,
  ensureValidatedEvidence,
  waitForJob,
  ensureCompletedReport,
};
