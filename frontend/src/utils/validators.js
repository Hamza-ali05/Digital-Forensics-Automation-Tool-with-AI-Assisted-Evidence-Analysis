/**
 * Client-side validation helpers aligned with DFAT backend rules.
 */

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * Basic email shape check.
 */
export function validateEmail(email) {
  if (typeof email !== "string") return false;
  return EMAIL_RE.test(email.trim());
}

/**
 * Password strength — mirrors ``dfat.auth.password.validate_password_strength``.
 *
 * @param {string} password
 * @param {number} [minLength=12]
 * @returns {{ isValid: boolean, errors: string[] }}
 */
export function validatePassword(password, minLength = 12) {
  const errors = [];
  const value = typeof password === "string" ? password : "";

  if (value.length < minLength) {
    errors.push(`Password must be at least ${minLength} characters`);
  }
  if (!/[A-Z]/.test(value)) {
    errors.push("Password must contain an uppercase letter");
  }
  if (!/[a-z]/.test(value)) {
    errors.push("Password must contain a lowercase letter");
  }
  if (!/\d/.test(value)) {
    errors.push("Password must contain a digit");
  }
  if (!/[^A-Za-z0-9]/.test(value)) {
    errors.push("Password must contain a special character");
  }

  return { isValid: errors.length === 0, errors };
}

/**
 * Required-field check. Returns an error string or ``null`` when valid.
 */
export function validateRequired(value, fieldName = "This field") {
  if (value === null || value === undefined) {
    return `${fieldName} is required`;
  }
  if (typeof value === "string" && value.trim() === "") {
    return `${fieldName} is required`;
  }
  if (Array.isArray(value) && value.length === 0) {
    return `${fieldName} is required`;
  }
  return null;
}

/**
 * Whether ``filename`` ends with one of ``allowed`` extensions (with or without dot).
 */
export function validateFileExtension(filename, allowed = []) {
  if (typeof filename !== "string" || !filename) return false;
  const list = Array.isArray(allowed) ? allowed : [];
  if (list.length === 0) return true;

  const lower = filename.toLowerCase();
  const dot = lower.lastIndexOf(".");
  if (dot < 0) return false;
  const ext = lower.slice(dot + 1);

  return list.some((item) => {
    const normalised = String(item).toLowerCase().replace(/^\./, "");
    return normalised === ext;
  });
}

/**
 * Basic path safety: non-empty, no null bytes, no ``..`` traversal segments.
 */
export function validateFilePath(path) {
  if (typeof path !== "string") return false;
  const trimmed = path.trim();
  if (!trimmed) return false;
  if (trimmed.includes("\0")) return false;

  const normalised = trimmed.replace(/\\/g, "/");
  const segments = normalised.split("/");
  if (segments.some((segment) => segment === "..")) {
    return false;
  }

  return true;
}
