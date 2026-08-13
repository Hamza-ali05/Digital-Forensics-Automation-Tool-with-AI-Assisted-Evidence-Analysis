import React from "react";
import { Link } from "react-router-dom";
import { Card } from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faArrowDown,
  faArrowRight,
  faArrowUp,
} from "@fortawesome/free-solid-svg-icons";

const COLOUR_MAP = {
  primary: "icon-shape-primary text-primary",
  success: "icon-shape-success text-success",
  warning: "icon-shape-warning text-warning",
  info: "icon-shape-secondary text-info",
  danger: "icon-shape-danger text-danger",
  secondary: "icon-shape-secondary text-secondary",
};

/**
 * Volt-style statistic card with optional trend and navigation link.
 *
 * @param {{
 *   title: string,
 *   value: number|string,
 *   icon: object,
 *   colour?: string,
 *   trend?: number|null,
 *   linkTo?: string,
 *   loading?: boolean,
 * }} props
 */
export default function StatCard({
  title,
  value,
  icon,
  colour = "primary",
  trend = null,
  linkTo,
  loading = false,
}) {
  const colourClass = COLOUR_MAP[colour] || COLOUR_MAP.primary;
  const displayValue = loading ? "…" : value ?? "—";

  let trendNode = null;
  if (trend !== null && trend !== undefined && !Number.isNaN(Number(trend))) {
    const n = Number(trend);
    if (n > 0) {
      trendNode = (
        <span className="text-success small fw-bold">
          <FontAwesomeIcon icon={faArrowUp} className="me-1" />
          {n}%
        </span>
      );
    } else if (n < 0) {
      trendNode = (
        <span className="text-danger small fw-bold">
          <FontAwesomeIcon icon={faArrowDown} className="me-1" />
          {Math.abs(n)}%
        </span>
      );
    } else {
      trendNode = <span className="text-muted small">0%</span>;
    }
  }

  const body = (
    <Card.Body className="d-flex align-items-center justify-content-between">
      <div>
        <h6 className="text-muted mb-1 text-uppercase small fw-bold">{title}</h6>
        <h3 className="mb-0 fw-bold">{displayValue}</h3>
        {trendNode ? <div className="mt-2">{trendNode}</div> : null}
      </div>
      <div className={`icon-shape icon-shape-sm rounded ${colourClass}`}>
        <FontAwesomeIcon icon={icon} />
      </div>
      {linkTo ? (
        <span className="position-absolute bottom-0 end-0 p-2 text-muted small">
          <FontAwesomeIcon icon={faArrowRight} />
        </span>
      ) : null}
    </Card.Body>
  );

  const card = (
    <Card
      border="light"
      className={`shadow-sm h-100 position-relative ${
        linkTo ? "dfat-stat-card-link" : ""
      }`}
      style={linkTo ? { cursor: "pointer" } : undefined}
    >
      {body}
    </Card>
  );

  if (linkTo) {
    return (
      <Link to={linkTo} className="text-decoration-none text-reset d-block h-100">
        {card}
      </Link>
    );
  }

  return card;
}
