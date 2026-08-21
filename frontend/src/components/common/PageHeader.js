import React from "react";

import usePageTitle from "hooks/usePageTitle";

/**
 * Standard page heading with optional subtitle and actions.
 *
 * @param {{
 *   title: string,
 *   subtitle?: string,
 *   actions?: React.ReactNode,
 * }} props
 */
export default function PageHeader({ title, subtitle, actions }) {
  usePageTitle(title);

  return (
    <div className="d-flex justify-content-between flex-wrap flex-md-nowrap align-items-center py-4">
      <div className="d-block mb-4 mb-md-0">
        <h1 className="h4 mb-1">{title}</h1>
        {subtitle ? <p className="mb-0 text-muted">{subtitle}</p> : null}
      </div>
      {actions ? (
        <div className="btn-toolbar mb-2 mb-md-0">{actions}</div>
      ) : null}
    </div>
  );
}
