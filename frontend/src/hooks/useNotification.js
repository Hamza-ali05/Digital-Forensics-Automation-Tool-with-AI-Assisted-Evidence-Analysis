import { useMemo } from "react";

import { useNotificationContext } from "contexts/NotificationContext";

/**
 * Convenience helpers that call addNotification with a fixed type.
 *
 * @example
 * const { success, error } = useNotification();
 * success("Case Created", "Case XYZ has been created successfully.");
 */
export default function useNotification() {
  const { addNotification, removeNotification, clearAll, notifications } =
    useNotificationContext();

  return useMemo(
    () => ({
      notifications,
      addNotification,
      removeNotification,
      clearAll,
      success: (title, message, options = {}) =>
        addNotification({ type: "success", title, message, ...options }),
      error: (title, message, options = {}) =>
        addNotification({ type: "error", title, message, ...options }),
      warning: (title, message, options = {}) =>
        addNotification({ type: "warning", title, message, ...options }),
      info: (title, message, options = {}) =>
        addNotification({ type: "info", title, message, ...options }),
    }),
    [addNotification, removeNotification, clearAll, notifications]
  );
}
