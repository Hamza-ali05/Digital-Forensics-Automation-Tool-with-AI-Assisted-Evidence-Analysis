import React from "react";
import { Toast } from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faCheckCircle,
  faExclamationCircle,
  faExclamationTriangle,
  faInfoCircle,
} from "@fortawesome/free-solid-svg-icons";

import { useNotificationContext } from "contexts/NotificationContext";

const TYPE_META = {
  success: { variant: "success", icon: faCheckCircle },
  error: { variant: "danger", icon: faExclamationCircle },
  warning: { variant: "warning", icon: faExclamationTriangle },
  info: { variant: "info", icon: faInfoCircle },
};

function formatTimestamp(value) {
  if (!value) return "";
  try {
    return new Date(value).toLocaleTimeString();
  } catch {
    return "";
  }
}

/**
 * Stacked Bootstrap toasts bound to NotificationContext (max 5).
 */
export default function ToastContainer() {
  const { notifications, removeNotification } = useNotificationContext();
  const visible = notifications.slice(-5);

  if (!visible.length) {
    return null;
  }

  return (
    <div
      className="dfat-toast-container position-fixed top-0 end-0 p-3"
      style={{ zIndex: 1090, maxWidth: "min(380px, calc(100vw - 1rem))" }}
      aria-live="polite"
      aria-relevant="additions text"
    >
      {visible.map((item) => {
        const meta = TYPE_META[item.type] || TYPE_META.info;
        return (
          <Toast
            key={item.id}
            className={`mb-2 border-${meta.variant} shadow-sm dfat-toast dfat-toast-${item.type}`}
            show
            autohide={false}
            onClose={() => removeNotification(item.id)}
          >
            <Toast.Header
              closeButton={item.dismissible !== false}
              className={`text-${meta.variant}`}
            >
              <FontAwesomeIcon icon={meta.icon} className="me-2" />
              <strong className="me-auto">{item.title || item.type}</strong>
              <small className="text-muted">{formatTimestamp(item.createdAt)}</small>
            </Toast.Header>
            {item.message ? (
              <Toast.Body className="small">{item.message}</Toast.Body>
            ) : null}
          </Toast>
        );
      })}
    </div>
  );
}
