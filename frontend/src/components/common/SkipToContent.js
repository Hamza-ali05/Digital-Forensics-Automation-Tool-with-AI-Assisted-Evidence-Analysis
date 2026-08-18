import React from "react";

/**
 * First-focus skip link so keyboard users bypass repeated chrome.
 */
export default function SkipToContent({ targetId = "main-content" }) {
  return (
    <a className="skip-link" href={`#${targetId}`}>
      Skip to main content
    </a>
  );
}
