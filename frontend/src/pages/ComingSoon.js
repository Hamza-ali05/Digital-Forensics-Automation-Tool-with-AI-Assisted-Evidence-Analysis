import React from "react";

/**
 * Minimal Prompt 8 placeholder used by forensic page stubs.
 */
export default function ComingSoon({ title }) {
  return (
    <div className="p-4">
      <h1 className="h4 mb-2">{title || "Page"}</h1>
      <div>Page coming in Prompt 8</div>
    </div>
  );
}
