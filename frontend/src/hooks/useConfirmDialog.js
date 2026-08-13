import { useCallback, useRef, useState } from "react";

const DEFAULT_OPTIONS = {
  title: "Confirm",
  message: "Are you sure you want to continue?",
  confirmLabel: "Confirm",
  cancelLabel: "Cancel",
  variant: "primary",
};

/**
 * Promise-based confirm dialog controller for ``ConfirmDialog``.
 *
 * ``openDialog(options)`` resolves ``true`` on confirm and rejects ``false``
 * on cancel / dismiss.
 *
 * @example
 * const { isOpen, openDialog, confirm, cancel, dialogProps } = useConfirmDialog();
 * await openDialog({ title: "Delete?", variant: "danger" });
 * <ConfirmDialog {...dialogProps} />
 */
export default function useConfirmDialog() {
  const [isOpen, setIsOpen] = useState(false);
  const [options, setOptions] = useState(DEFAULT_OPTIONS);
  const resolverRef = useRef(null);

  const settle = useCallback((accepted) => {
    const pending = resolverRef.current;
    resolverRef.current = null;
    setIsOpen(false);
    if (!pending) {
      return;
    }
    if (accepted) {
      pending.resolve(true);
    } else {
      pending.reject(false);
    }
  }, []);

  const confirm = useCallback(() => {
    settle(true);
  }, [settle]);

  const cancel = useCallback(() => {
    settle(false);
  }, [settle]);

  const openDialog = useCallback((nextOptions = {}) => {
    if (resolverRef.current) {
      resolverRef.current.reject(false);
      resolverRef.current = null;
    }

    setOptions({ ...DEFAULT_OPTIONS, ...nextOptions });
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
      onConfirm: confirm,
      onCancel: cancel,
    },
  };
}
