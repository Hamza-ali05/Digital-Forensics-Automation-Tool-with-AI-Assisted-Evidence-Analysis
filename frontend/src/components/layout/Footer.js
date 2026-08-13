import React from "react";
import { Col, Row } from "@themesberg/react-bootstrap";

import config from "config";

/**
 * Application footer with version, affiliation, and API health link.
 */
export default function Footer() {
  const year = new Date().getFullYear();
  const healthUrl = `${config.apiBaseUrl.replace(/\/$/, "")}/health`;

  return (
    <footer className="footer section py-4 mt-4 border-top">
      <Row className="align-items-center">
        <Col xs={12} xl={8} className="mb-2 mb-xl-0">
          <p className="mb-0 text-center text-xl-start text-muted">
            {config.appName} v{config.appVersion} — Canterbury Christ Church
            University — {year}
          </p>
        </Col>
        <Col xs={12} xl={4}>
          <p className="mb-0 text-center text-xl-end">
            <a
              href={healthUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-muted"
            >
              System status
            </a>
          </p>
        </Col>
      </Row>
    </footer>
  );
}
