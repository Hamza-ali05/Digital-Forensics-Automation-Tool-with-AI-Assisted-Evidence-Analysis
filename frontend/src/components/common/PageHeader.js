import React from "react";
import { Breadcrumb } from "@themesberg/react-bootstrap";
import { Link } from "react-router-dom";

/**
 * Standard page heading with optional subtitle, breadcrumbs, and actions.
 *
 * @param {{
 *   title: string,
 *   subtitle?: string,
 *   actions?: React.ReactNode,
 *   breadcrumbs?: Array<{ label: string, to?: string }>,
 * }} props
 */
export default function PageHeader({
  title,
  subtitle,
  actions,
  breadcrumbs,
}) {
  return (
    <div className="d-flex justify-content-between flex-wrap flex-md-nowrap align-items-center py-4">
      <div className="d-block mb-4 mb-md-0">
        {Array.isArray(breadcrumbs) && breadcrumbs.length > 0 ? (
          <Breadcrumb
            listProps={{
              className: "breadcrumb-dark breadcrumb-transparent mb-2",
            }}
          >
            {breadcrumbs.map((crumb, index) => {
              const isLast = index === breadcrumbs.length - 1;
              if (isLast || !crumb.to) {
                return (
                  <Breadcrumb.Item key={`${crumb.label}-${index}`} active>
                    {crumb.label}
                  </Breadcrumb.Item>
                );
              }
              return (
                <Breadcrumb.Item
                  key={`${crumb.label}-${index}`}
                  linkAs={Link}
                  linkProps={{ to: crumb.to }}
                >
                  {crumb.label}
                </Breadcrumb.Item>
              );
            })}
          </Breadcrumb>
        ) : null}
        <h4 className="mb-1">{title}</h4>
        {subtitle ? <p className="mb-0 text-muted">{subtitle}</p> : null}
      </div>
      {actions ? (
        <div className="btn-toolbar mb-2 mb-md-0">{actions}</div>
      ) : null}
    </div>
  );
}
