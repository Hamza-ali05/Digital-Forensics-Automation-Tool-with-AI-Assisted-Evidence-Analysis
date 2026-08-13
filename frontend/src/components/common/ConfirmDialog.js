import React from "react";
import { Button, Modal } from "@themesberg/react-bootstrap";

/**
 * Confirm / cancel modal for destructive and general actions.
 *
 * @param {{
 *   show: boolean,
 *   title?: string,
 *   message?: string,
 *   confirmLabel?: string,
 *   cancelLabel?: string,
 *   variant?: "danger"|"warning"|"primary",
 *   onConfirm?: () => void,
 *   onCancel?: () => void,
 * }} props
 */
export default function ConfirmDialog({
  show = false,
  title = "Confirm",
  message = "Are you sure you want to continue?",
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  variant = "primary",
  onConfirm,
  onCancel,
}) {
  return (
    <Modal show={show} onHide={onCancel} centered>
      <Modal.Header closeButton>
        <Modal.Title>{title}</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        <p className="mb-0">{message}</p>
      </Modal.Body>
      <Modal.Footer>
        <Button variant="link" className="text-gray-600" onClick={onCancel}>
          {cancelLabel}
        </Button>
        <Button variant={variant} onClick={onConfirm}>
          {confirmLabel}
        </Button>
      </Modal.Footer>
    </Modal>
  );
}
