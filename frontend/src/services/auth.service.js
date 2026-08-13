import apiClient, { apiGet, apiPost, apiPut } from "services/api";
import { API_ENDPOINTS } from "config/api.config";
import { AUTH_CONFIG } from "config/auth.config";

/**
 * Persist token pair (+ optional expiry) to localStorage.
 */
function storeTokens({ access_token, refresh_token, expires_in }) {
  localStorage.setItem(AUTH_CONFIG.tokenKey, access_token);
  localStorage.setItem(AUTH_CONFIG.refreshTokenKey, refresh_token);
  if (typeof expires_in === "number") {
    localStorage.setItem(
      AUTH_CONFIG.tokenExpiryKey,
      String(Date.now() + expires_in * 1000)
    );
  }
}

/**
 * Persist the public user profile for session continuity.
 */
function storeUser(user) {
  if (user) {
    localStorage.setItem(AUTH_CONFIG.userKey, JSON.stringify(user));
  }
}

/**
 * Clear all auth-related localStorage keys.
 */
function clearAuthStorage() {
  localStorage.removeItem(AUTH_CONFIG.tokenKey);
  localStorage.removeItem(AUTH_CONFIG.refreshTokenKey);
  localStorage.removeItem(AUTH_CONFIG.userKey);
  localStorage.removeItem(AUTH_CONFIG.tokenExpiryKey);
}

/**
 * OAuth2 password-form login (application/x-www-form-urlencoded).
 * Stores tokens, loads `/users/me`, persists user, and returns the profile.
 */
export async function login(username, password) {
  const form = new URLSearchParams();
  form.append("username", username);
  form.append("password", password);

  const { data: tokens } = await apiClient.post(
    API_ENDPOINTS.AUTH.LOGIN,
    form,
    { headers: { "Content-Type": "application/x-www-form-urlencoded" } }
  );

  storeTokens(tokens);

  const { data: user } = await apiGet(API_ENDPOINTS.USERS.ME);
  storeUser(user);
  return user;
}

/**
 * Register a new user (requires admin/investigator JWT).
 * @param {{ username: string, email: string, password: string, full_name: string, role_name?: string }} data
 */
export async function register(data) {
  const { data: user } = await apiPost(API_ENDPOINTS.AUTH.REGISTER, data);
  return user;
}

/**
 * Revoke current session and clear local auth state.
 */
export async function logout() {
  try {
    await apiPost(API_ENDPOINTS.AUTH.LOGOUT);
  } catch {
    // Always clear local session even if the revoke call fails.
  } finally {
    clearAuthStorage();
  }
}

/**
 * Revoke all sessions for the current user and clear local auth state.
 */
export async function logoutAll() {
  try {
    await apiPost(API_ENDPOINTS.AUTH.LOGOUT_ALL);
  } catch {
    // Always clear local session even if the revoke call fails.
  } finally {
    clearAuthStorage();
  }
}

/**
 * Exchange refresh token for a new pair and update localStorage.
 */
export async function refreshToken() {
  const refresh_token = localStorage.getItem(AUTH_CONFIG.refreshTokenKey);
  if (!refresh_token) {
    throw new Error("No refresh token available");
  }

  // Use bare axios path via apiClient would still attach Bearer; refresh is public.
  // Prefer apiPost so normalised errors stay consistent; backend accepts body only.
  const { data } = await apiPost(API_ENDPOINTS.AUTH.REFRESH, { refresh_token });
  storeTokens(data);
  return data;
}

/**
 * Change password for the authenticated user.
 */
export async function changePassword(currentPassword, newPassword) {
  await apiPut(API_ENDPOINTS.AUTH.CHANGE_PASSWORD, {
    current_password: currentPassword,
    new_password: newPassword,
  });
}

/**
 * Fetch the current user profile from the API.
 */
export async function getCurrentUser() {
  const { data: user } = await apiGet(API_ENDPOINTS.USERS.ME);
  storeUser(user);
  return user;
}

/**
 * Read the cached user profile from localStorage (no network).
 */
export function getStoredUser() {
  const raw = localStorage.getItem(AUTH_CONFIG.userKey);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    localStorage.removeItem(AUTH_CONFIG.userKey);
    return null;
  }
}

/**
 * True when an access token exists and has not passed its stored expiry.
 */
export function isAuthenticated() {
  const token = localStorage.getItem(AUTH_CONFIG.tokenKey);
  if (!token) return false;

  const expiryRaw = localStorage.getItem(AUTH_CONFIG.tokenExpiryKey);
  if (!expiryRaw) return true;

  const expiry = Number(expiryRaw);
  if (Number.isNaN(expiry)) return true;
  return Date.now() < expiry;
}

/**
 * Role name from the stored user object (`role_name`), or null.
 */
export function getRole() {
  const user = getStoredUser();
  return user?.role_name || null;
}

export function hasRefreshToken() {
  return Boolean(localStorage.getItem(AUTH_CONFIG.refreshTokenKey));
}

const authService = {
  login,
  register,
  logout,
  logoutAll,
  refreshToken,
  changePassword,
  getCurrentUser,
  getStoredUser,
  isAuthenticated,
  getRole,
  hasRefreshToken,
  clearAuthStorage,
  storeTokens,
  storeUser,
};

export default authService;
