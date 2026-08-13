import React from "react";
import { Card, Container } from "@themesberg/react-bootstrap";

/**
 * Lightweight placeholder for DFAT sections pending Prompt 8 pages.
 */
export default ({ title = "Section", description = "" }) => (
  <Container fluid className="px-0">
    <div className="d-flex justify-content-between flex-wrap flex-md-nowrap align-items-center py-4">
      <div className="d-block mb-4 mb-md-0">
        <h1 className="h2">{title}</h1>
      </div>
    </div>
    <Card border="light" className="shadow-sm">
      <Card.Body>
        <Card.Text className="mb-0 text-muted">
          {description || `${title} content will be implemented in Prompt 8.`}
        </Card.Text>
      </Card.Body>
    </Card>
  </Container>
);
