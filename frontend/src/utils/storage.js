const DFAT_PREFIX = "dfat_";

/**
 * Lightweight localStorage helpers with JSON serialisation.
 * ``clearAll`` only removes keys prefixed with ``dfat_``.
 */

export function getItem(key) {
  try {
    const raw = localStorage.getItem(key);
    if (raw === null || raw === undefined) {
      return null;
    }
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function setItem(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}

export function removeItem(key) {
  try {
    localStorage.removeItem(key);
  } catch {
    // Ignore storage failures.
  }
}

/**
 * Remove all keys that start with ``dfat_``.
 */
export function clearAll() {
  try {
    const keys = [];
    for (let i = 0; i < localStorage.length; i += 1) {
      const key = localStorage.key(i);
      if (key && key.startsWith(DFAT_PREFIX)) {
        keys.push(key);
      }
    }
    keys.forEach((key) => localStorage.removeItem(key));
  } catch {
    // Ignore storage failures.
  }
}

export function hasItem(key) {
  try {
    return localStorage.getItem(key) !== null;
  } catch {
    return false;
  }
}
