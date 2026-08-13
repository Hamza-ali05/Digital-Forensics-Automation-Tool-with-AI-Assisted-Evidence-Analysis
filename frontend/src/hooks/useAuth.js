import { useContext } from "react";

import { AuthContext } from "contexts/AuthContext";

/**
 * Convenience hook for auth state and actions.
 * Must be used inside an AuthProvider.
 */
export default function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
