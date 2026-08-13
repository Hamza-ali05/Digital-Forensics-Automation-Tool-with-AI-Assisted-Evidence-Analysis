import React from "react";
import { Button, Card } from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faInbox } from "@fortawesome/free-solid-svg-icons";

/**
 * Centred empty-state message with optional action.
 *
 * @param {{
 *   icon?: object|React.ElementType,
 *   title?: string,
 *   description?: string,
 *   actionLabel?: string,
 *   onAction?: () => void,
 * }} props
 */
export default function EmptyState({
  icon = faInbox,
  title = "Nothing here yet",
  description = "There are no items to display.",
  actionLabel,
  onAction,
}) {
  const IconComponent =
    typeof icon === "function" || (icon && icon.render)
      ? icon
      : null;

  return (
    <Card border="0" className="shadow-none bg-transparent">
      <Card.Body className="text-center py-5">
        <div className="mb-3 text-muted">
          {IconComponent ? (
            <IconComponent />
          ) : (
            <FontAwesomeIcon icon={icon || faInbox} size="3x" />
          )}
        </div>
        {title ? <h5 className="mb-2">{title}</h5> : null}
        {description ? (
          <p className="text-muted mb-3 mx-auto" style={{ maxWidth: 420 }}>
            {description}
          </p>
        ) : null}
        {actionLabel && typeof onAction === "function" ? (
          <Button variant="primary" onClick={onAction}>
            {actionLabel}
          </Button>
        ) : null}
      </Card.Body>
    </Card>
  );
}
