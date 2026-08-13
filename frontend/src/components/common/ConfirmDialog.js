import React from "react";
import { Button, Form, Modal } from "@themesberg/react-bootstrap";

/**
 * Confirm / cancel modal for destructive and general actions.
 * Optional ``requireReason`` shows a textarea that must be filled to confirm.
 */
export default function ConfirmDialog({
  show = false,
  title = "Confirm",
  message = "Are you sure you want to continue?",
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  variant = "primary",
  requireReason = false,
  reason = "",
  reasonLabel = "Reason",
  reasonError = null,
  onReasonChange,
  onConfirm,
  onCancel,
}) {
  return (
    <Modal show={show} onHide={onCancel} centered>
      <Modal.Header closeButton>
        <Modal.Title>{title}</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        <p className={requireReason ? "mb-3" : "mb-0"}>{message}</p>
        {requireReason ? (
          <Form.Group controlId="confirm-reason">
            <Form.Label>
              {reasonLabel} <span className="text-danger">*</span>
            </Form.Label>
            <Form.Control
              as="textarea"
              rows={3}
              value={reason}
              onChange={(e) => onReasonChange && onReasonChange(e.target.value)}
              isInvalid={Boolean(reasonError)}
              placeholder="Enter a reason…"
            />
            <Form.Control.Feedback type="invalid">
              {reasonError}
            </Form.Control.Feedback>
          </Form.Group>
        ) : null}
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
