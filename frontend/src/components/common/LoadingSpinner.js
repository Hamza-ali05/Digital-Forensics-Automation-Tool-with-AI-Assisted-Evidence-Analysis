import React from "react";
import { Spinner } from "@themesberg/react-bootstrap";

const SIZE_MAP = {
  sm: { spinner: "sm", fontSize: "0.875rem" },
  md: { spinner: undefined, fontSize: "1rem" },
  lg: { spinner: undefined, fontSize: "1.125rem", style: { width: "3rem", height: "3rem" } },
};

/**
 * Centred spinner with optional text.
 * Supports legacy ``show`` (Volt preloader) and Prompt 7.11 ``size`` / ``fullPage``.
 *
 * @param {{
 *   size?: "sm"|"md"|"lg",
 *   text?: string,
 *   fullPage?: boolean,
 *   show?: boolean,
 * }} props
 */
export default function LoadingSpinner({
  size = "md",
  text,
  fullPage = true,
  show = true,
}) {
  if (!show) {
    return null;
  }

  const sizeCfg = SIZE_MAP[size] || SIZE_MAP.md;
  const spinner = (
    <div className="d-flex flex-column align-items-center justify-content-center p-3">
      <Spinner
        animation="border"
        role="status"
        variant="primary"
        size={sizeCfg.spinner}
        style={sizeCfg.style}
      >
        <span className="visually-hidden">Loading…</span>
      </Spinner>
      {text ? (
        <span className="mt-2 text-muted" style={{ fontSize: sizeCfg.fontSize }}>
          {text}
        </span>
      ) : null}
    </div>
  );

  if (fullPage) {
    return (
      <div
        className="preloader bg-soft flex-column justify-content-center align-items-center show"
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 9999,
          display: "flex",
        }}
        aria-busy="true"
      >
        {spinner}
      </div>
    );
  }

  return spinner;
}
