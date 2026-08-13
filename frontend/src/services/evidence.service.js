import { apiGet, apiPost } from "services/api";
import { API_ENDPOINTS } from "config/api.config";

/**
 * Evidence register, inventory, custody, and statistics helpers.
 */
export async function register(payload) {
  const { data } = await apiPost(API_ENDPOINTS.EVIDENCE.REGISTER, payload);
  return data;
}

export async function getInventory(params = {}) {
  const { data } = await apiGet(API_ENDPOINTS.EVIDENCE.INVENTORY, params);
  return data;
}

export async function getDetail(id) {
  const { data } = await apiGet(API_ENDPOINTS.EVIDENCE.DETAIL(id));
  return data;
}

export async function getStatistics(params = {}) {
  const { data } = await apiGet(API_ENDPOINTS.EVIDENCE.STATS, params);
  return data;
}

export async function validate(id) {
  const { data } = await apiPost(API_ENDPOINTS.EVIDENCE.VALIDATE(id));
  return data;
}

export async function verifyIntegrity(id) {
  const { data } = await apiPost(API_ENDPOINTS.EVIDENCE.VERIFY(id));
  return data;
}

export async function getCustody(id) {
  const { data } = await apiGet(API_ENDPOINTS.EVIDENCE.CUSTODY(id));
  return data;
}

export async function getStatus(id) {
  const { data } = await apiGet(API_ENDPOINTS.EVIDENCE.STATUS(id));
  return data;
}

export async function quarantine(id, payload = {}) {
  const { data } = await apiPost(API_ENDPOINTS.EVIDENCE.QUARANTINE(id), payload);
  return data;
}

/**
 * Client-side custody chain structural checks + integrity verification.
 * Backend exposes chain fetch and hash verify; no dedicated verify-custody route.
 */
export async function verifyCustody(id) {
  const chainPayload = await getCustody(id);
  const entries = Array.isArray(chainPayload?.entries)
    ? chainPayload.entries
    : [];
  const issues = [];
  const total = entries.length;

  if (total === 0) {
    issues.push("No custody records found");
    return {
      is_valid: false,
      total_entries: 0,
      integrity_verified: false,
      issues,
    };
  }

  const first = entries[0];
  const firstAction = String(first.action || "").toLowerCase();
  if (firstAction !== "acquired") {
    issues.push(`First entry must be ACQUIRED, found ${first.action}`);
  }
  if (first.entry_number != null && Number(first.entry_number) !== 1) {
    issues.push(`First entry_number must be 1, found ${first.entry_number}`);
  }

  const numbers = entries
    .map((e) => e.entry_number)
    .filter((n) => n != null)
    .map(Number);
  for (let i = 1; i <= total; i += 1) {
    if (!numbers.includes(i)) {
      issues.push(`Missing entry_number ${i} (gap in chain)`);
    }
  }

  const baseline = String(first.hash_at_action || "").toLowerCase();
  entries.slice(1).forEach((record) => {
    if (
      baseline &&
      String(record.hash_at_action || "").toLowerCase() !== baseline
    ) {
      issues.push(
        `Hash mismatch at entry ${record.entry_number}: digest differs from acquisition baseline`
      );
    }
  });

  let integrityVerified = false;
  try {
    const integrity = await verifyIntegrity(id);
    integrityVerified = Boolean(integrity?.integrity_verified);
    if (!integrityVerified) {
      issues.push("Current file hash does not match registered digest");
    }
  } catch (err) {
    issues.push(err?.message || "Integrity verification request failed");
  }

  return {
    is_valid: issues.length === 0 && integrityVerified,
    total_entries: total,
    integrity_verified: integrityVerified,
    issues,
  };
}

const evidenceService = {
  register,
  getInventory,
  getDetail,
  getStatistics,
  validate,
  verifyIntegrity,
  getCustody,
  getStatus,
  quarantine,
  verifyCustody,
};

export default evidenceService;
