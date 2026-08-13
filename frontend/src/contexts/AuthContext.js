import React, {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import config from "config";
import authService from "services/auth.service";

export const AuthContext = createContext(null);

/**
 * Provides auth state and actions to the entire app.
 * Restores session from localStorage on mount and refreshes tokens on an interval.
 */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => authService.getStoredUser());
  const [isLoading, setIsLoading] = useState(true);
  const refreshTimerRef = useRef(null);

  const role = user?.role_name || null;
  const isAuthenticated = Boolean(user) && authService.isAuthenticated();

  const clearSession = useCallback(() => {
    authService.clearAuthStorage();
    setUser(null);
  }, []);

  const refreshUser = useCallback(async () => {
    const profile = await authService.getCurrentUser();
    setUser(profile);
    return profile;
  }, []);

  const bootstrapSession = useCallback(async () => {
    setIsLoading(true);
    try {
      const hasAccess = authService.isAuthenticated();
      const hasRefresh = authService.hasRefreshToken();

      if (!hasAccess && !hasRefresh) {
        setUser(null);
        return;
      }

      if (!hasAccess && hasRefresh) {
        await authService.refreshToken();
      }

      const profile = await authService.getCurrentUser();
      setUser(profile);
    } catch {
      clearSession();
    } finally {
      setIsLoading(false);
    }
  }, [clearSession]);

  useEffect(() => {
    bootstrapSession();
  }, [bootstrapSession]);

  // Proactive token refresh while a session is present.
  useEffect(() => {
    if (refreshTimerRef.current) {
      clearInterval(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }

    if (!user || !authService.hasRefreshToken()) {
      return undefined;
    }

    const intervalMs = config.tokenRefreshInterval || 300000;

    refreshTimerRef.current = setInterval(async () => {
      try {
        await authService.refreshToken();
      } catch {
        clearSession();
      }
    }, intervalMs);

    return () => {
      if (refreshTimerRef.current) {
        clearInterval(refreshTimerRef.current);
        refreshTimerRef.current = null;
      }
    };
  }, [user, clearSession]);

  const login = useCallback(async (username, password) => {
    const profile = await authService.login(username, password);
    setUser(profile);
    return profile;
  }, []);

  const logout = useCallback(async () => {
    try {
      await authService.logout();
    } finally {
      setUser(null);
    }
  }, []);

  const register = useCallback(async (data) => {
    return authService.register(data);
  }, []);

  const value = useMemo(
    () => ({
      user,
      role,
      isAuthenticated: Boolean(user) && (authService.isAuthenticated() || authService.hasRefreshToken()),
      isLoading,
      login,
      logout,
      register,
      refreshUser,
    }),
    [user, role, isLoading, login, logout, register, refreshUser]
  );

  // Keep derived flag consistent with memo (avoid stale isAuthenticated const above).
  void isAuthenticated;

  return (
    <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
  );
}

export default AuthContext;
