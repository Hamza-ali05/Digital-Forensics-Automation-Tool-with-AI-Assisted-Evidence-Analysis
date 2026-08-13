import React from "react";
import { Col, Row, Card, Container } from "@themesberg/react-bootstrap";

import config from "config";
import { APP_CONFIG } from "config/app.config";

/**
 * Temporary dashboard shell until Prompt 8 forensic pages land.
 */
export default () => (
  <Container fluid className="px-0">
    <div className="d-flex justify-content-between flex-wrap flex-md-nowrap align-items-center py-4">
      <div className="d-block mb-4 mb-md-0">
        <h1 className="h2">Dashboard</h1>
        <p className="mb-0 text-muted">
          {APP_CONFIG.name} v{APP_CONFIG.version} — Digital Forensics Automation Tool
        </p>
      </div>
    </div>

    <Row className="justify-content-md-center">
      <Col xs={12} className="mb-4">
        <Card border="light" className="shadow-sm">
          <Card.Body>
            <Card.Title>Welcome</Card.Title>
            <Card.Text>
              Demo content has been removed. Use the sidebar to navigate DFAT
              sections. Forensic pages and live API integration arrive in
              Prompt 8.
            </Card.Text>
            {config.debug ? (
              <Card.Text className="small text-muted mb-0">
                API base: {config.apiBaseUrl}
              </Card.Text>
            ) : null}
          </Card.Body>
        </Card>
      </Col>
    </Row>
  </Container>
);
