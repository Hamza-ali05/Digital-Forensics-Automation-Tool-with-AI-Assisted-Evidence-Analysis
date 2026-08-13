import React, { useMemo } from "react";
import { Breadcrumb } from "@themesberg/react-bootstrap";
import { Link, useLocation } from "react-router-dom";

const SEGMENT_LABELS = {
  dashboard: "Dashboard",
  cases: "Cases",
  new: "New",
  evidence: "Evidence",
  integrity: "Integrity Check",
  pipeline: "Pipeline",
  run: "Run",
  artefacts: "Artefacts",
  ai: "AI Analysis",
  reports: "Reports",
  evaluation: "Evaluation",
  benchmark: "Benchmark",
  history: "History",
  performance: "Performance",
  usability: "Usability",
  settings: "Settings",
  users: "User Management",
  profile: "Profile",
  auth: "Auth",
  login: "Login",
  register: "Register",
  questionnaire: "Questionnaire",
};

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const HEX_ID_RE = /^[0-9a-f]{16,}$/i;

function labelForSegment(segment) {
  if (SEGMENT_LABELS[segment]) {
    return SEGMENT_LABELS[segment];
  }
  if (UUID_RE.test(segment) || HEX_ID_RE.test(segment)) {
    return `${segment.slice(0, 8)}…`;
  }
  if (/^\d+$/.test(segment)) {
    return `#${segment}`;
  }
  return segment.charAt(0).toUpperCase() + segment.slice(1);
}

/**
 * Auto breadcrumbs from the current pathname.
 * @param {{ compact?: boolean }} props
 */
export default function Breadcrumbs({ compact = false }) {
  const { pathname } = useLocation();

  const crumbs = useMemo(() => {
    const segments = pathname.split("/").filter(Boolean);
    if (segments.length === 0) {
      return [{ label: "Dashboard", to: "/dashboard", current: true }];
    }

    const items = [{ label: "Home", to: "/dashboard", current: false }];
    let acc = "";
    segments.forEach((segment, index) => {
      acc += `/${segment}`;
      items.push({
        label: labelForSegment(segment),
        to: acc,
        current: index === segments.length - 1,
      });
    });
    return items;
  }, [pathname]);

  if (compact && crumbs.length <= 1) {
    return null;
  }

  return (
    <Breadcrumb
      listProps={{
        className: compact
          ? "breadcrumb-dark breadcrumb-transparent mb-0 py-1"
          : "breadcrumb-dark breadcrumb-transparent mb-3",
      }}
    >
      {crumbs.map((crumb) =>
        crumb.current ? (
          <Breadcrumb.Item key={crumb.to} active>
            {crumb.label}
          </Breadcrumb.Item>
        ) : (
          <Breadcrumb.Item
            key={crumb.to}
            linkAs={Link}
            linkProps={{ to: crumb.to }}
          >
            {crumb.label}
          </Breadcrumb.Item>
        )
      )}
    </Breadcrumb>
  );
}
