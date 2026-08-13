import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

const MAX_VISIBLE = 5;
const DEFAULT_DURATION = 5000;

export const NotificationContext = createContext(null);

function createId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `notif-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/**
 * Application-wide toast notifications (max 5, auto-dismiss).
 * Visual rendering is handled by ``components/common/ToastContainer``.
 */
export function NotificationProvider({ children }) {
  const [notifications, setNotifications] = useState([]);
  const timersRef = useRef({});

  const removeNotification = useCallback((id) => {
    setNotifications((prev) => prev.filter((item) => item.id !== id));
    if (timersRef.current[id]) {
      window.clearTimeout(timersRef.current[id]);
      delete timersRef.current[id];
    }
  }, []);

  const clearAll = useCallback(() => {
    Object.values(timersRef.current).forEach((timerId) => {
      window.clearTimeout(timerId);
    });
    timersRef.current = {};
    setNotifications([]);
  }, []);

  const addNotification = useCallback(
    ({
      type = "info",
      title = "",
      message = "",
      duration = DEFAULT_DURATION,
      dismissible = true,
    }) => {
      const id = createId();
      const next = {
        id,
        type,
        title,
        message,
        duration,
        dismissible,
        createdAt: Date.now(),
      };

      setNotifications((prev) => {
        const merged = [...prev, next];
        if (merged.length <= MAX_VISIBLE) {
          return merged;
        }
        const overflow = merged.slice(0, merged.length - MAX_VISIBLE);
        overflow.forEach((item) => {
          if (timersRef.current[item.id]) {
            window.clearTimeout(timersRef.current[item.id]);
            delete timersRef.current[item.id];
          }
        });
        return merged.slice(-MAX_VISIBLE);
      });

      if (typeof duration === "number" && duration > 0) {
        timersRef.current[id] = window.setTimeout(() => {
          removeNotification(id);
        }, duration);
      }

      return id;
    },
    [removeNotification]
  );

  useEffect(
    () => () => {
      Object.values(timersRef.current).forEach((timerId) => {
        window.clearTimeout(timerId);
      });
      timersRef.current = {};
    },
    []
  );

  const value = useMemo(
    () => ({
      notifications,
      addNotification,
      removeNotification,
      clearAll,
    }),
    [notifications, addNotification, removeNotification, clearAll]
  );

  return (
    <NotificationContext.Provider value={value}>
      {children}
    </NotificationContext.Provider>
  );
}

export function useNotificationContext() {
  const context = useContext(NotificationContext);
  if (!context) {
    throw new Error(
      "useNotificationContext must be used within a NotificationProvider"
    );
  }
  return context;
}

export default NotificationContext;
