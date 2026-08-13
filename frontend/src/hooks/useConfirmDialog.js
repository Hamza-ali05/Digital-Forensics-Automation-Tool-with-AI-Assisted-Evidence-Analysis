import { useCallback, useRef, useState } from "react";

const DEFAULT_OPTIONS = {
  title: "Confirm",
  message: "Are you sure you want to continue?",
  confirmLabel: "Confirm",
  cancelLabel: "Cancel",
  variant: "primary",
  requireReason: false,
  reason: "",
  reasonLabel: "Reason",
  reasonError: null,
};

/**
 * Promise-based confirm dialog controller for ``ConfirmDialog``.
 *
 * Resolves ``true`` on confirm (no reason), the reason string when
 * ``requireReason`` is set, and rejects ``false`` on cancel / dismiss.
 */
export default function useConfirmDialog() {
  const [isOpen, setIsOpen] = useState(false);
  const [options, setOptions] = useState(DEFAULT_OPTIONS);
  const resolverRef = useRef(null);
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const settle = useCallback((accepted, payload) => {
    const pending = resolverRef.current;
    resolverRef.current = null;
    setIsOpen(false);
    setOptions(DEFAULT_OPTIONS);
    if (!pending) {
      return;
    }
    if (accepted) {
      pending.resolve(payload);
    } else {
      pending.reject(false);
    }
  }, []);

  const confirm = useCallback(() => {
    const opts = optionsRef.current;
    if (opts.requireReason) {
      const reason = String(opts.reason || "").trim();
      if (!reason) {
        setOptions((prev) => ({
          ...prev,
          reasonError: "A reason is required",
        }));
        return;
      }
      settle(true, reason);
      return;
    }
    settle(true, true);
  }, [settle]);

  const cancel = useCallback(() => {
    settle(false);
  }, [settle]);

  const setReason = useCallback((reason) => {
    setOptions((prev) => ({
      ...prev,
      reason,
      reasonError: null,
    }));
  }, []);

  const openDialog = useCallback((nextOptions = {}) => {
    if (resolverRef.current) {
      resolverRef.current.reject(false);
      resolverRef.current = null;
    }

    setOptions({
      ...DEFAULT_OPTIONS,
      ...nextOptions,
      reason: "",
      reasonError: null,
    });
    setIsOpen(true);

    return new Promise((resolve, reject) => {
      resolverRef.current = { resolve, reject };
    });
  }, []);

  return {
    isOpen,
    confirm,
    cancel,
    openDialog,
    options,
    dialogProps: {
      show: isOpen,
      title: options.title,
      message: options.message,
      confirmLabel: options.confirmLabel,
      cancelLabel: options.cancelLabel,
      variant: options.variant,
      requireReason: options.requireReason,
      reason: options.reason,
      reasonLabel: options.reasonLabel,
      reasonError: options.reasonError,
      onReasonChange: setReason,
      onConfirm: confirm,
      onCancel: cancel,
    },
  };
}
