import React from "react";
import { Link } from "react-router-dom";
import { Button, Card, Col, Container, Row } from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faChartLine,
  faClipboardList,
  faHistory,
  faTachometerAlt,
} from "@fortawesome/free-solid-svg-icons";

import PageHeader from "components/common/PageHeader";
import { Routes } from "routes";

/**
 * Evaluation hub — benchmark comparison and usability analysis.
 */
export default function EvaluationDashboard() {
  return (
    <Container fluid className="px-0">
      <PageHeader
        title="Evaluation"
        subtitle="Benchmark DFRWS/CFReDS comparisons and review usability studies"
        breadcrumbs={[
          { label: "Home", to: Routes.Dashboard.path },
          { label: "Evaluation" },
        ]}
      />
      <Row className="g-3">
        <Col xs={12} md={6} lg={4}>
          <Card border="light" className="shadow-sm h-100">
            <Card.Body>
              <h5>
                <FontAwesomeIcon icon={faChartLine} className="me-2 text-primary" />
                Benchmark Evaluation
              </h5>
              <p className="small text-muted">
                Run precision, recall, and F1 comparisons against local ground-truth
                datasets.
              </p>
              <Button as={Link} to={Routes.EvaluationBenchmark.path} variant="primary">
                Run benchmark
              </Button>
            </Card.Body>
          </Card>
        </Col>
        <Col xs={12} md={6} lg={4}>
          <Card border="light" className="shadow-sm h-100">
            <Card.Body>
              <h5>
                <FontAwesomeIcon icon={faHistory} className="me-2 text-primary" />
                Benchmark History
              </h5>
              <p className="small text-muted">
                Review past runs, P/R/F1 trends, and false-positive / false-negative
                detail.
              </p>
              <Button
                as={Link}
                to={Routes.EvaluationBenchmarkHistory.path}
                variant="outline-primary"
              >
                View history
              </Button>
            </Card.Body>
          </Card>
        </Col>
        <Col xs={12} md={6} lg={4}>
          <Card border="light" className="shadow-sm h-100">
            <Card.Body>
              <h5>
                <FontAwesomeIcon
                  icon={faTachometerAlt}
                  className="me-2 text-primary"
                />
                Performance Analytics
              </h5>
              <p className="small text-muted">
                Time-to-triage statistics, speedup vs a manual baseline, and
                pipeline stage bottlenecks.
              </p>
              <Button
                as={Link}
                to={Routes.EvaluationPerformance.path}
                variant="outline-primary"
              >
                Open analytics
              </Button>
            </Card.Body>
          </Card>
        </Col>
        <Col xs={12} md={6} lg={4}>
          <Card border="light" className="shadow-sm h-100">
            <Card.Body>
              <h5>
                <FontAwesomeIcon
                  icon={faClipboardList}
                  className="me-2 text-primary"
                />
                Usability
              </h5>
              <p className="small text-muted">
                Questionnaire results and ethics-locked response analysis.
              </p>
              <Button
                as={Link}
                to={Routes.EvaluationUsability.path}
                variant="outline-secondary"
              >
                Open usability
              </Button>
            </Card.Body>
          </Card>
        </Col>
      </Row>
    </Container>
  );
}
