import React, { useState } from "react";
import { Card, Col, Collapse, Container, Row } from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faBookOpen,
  faCaretDown,
  faCaretRight,
  faExternalLinkAlt,
  faQuestionCircle,
  faRoute,
  faUserShield,
} from "@fortawesome/free-solid-svg-icons";

import PageHeader from "components/common/PageHeader";
import config from "config";
import { Routes } from "routes";

const WORKFLOW = [
  {
    step: 1,
    title: "Create Case",
    detail:
      "Open Cases → New Case. Capture case name, description, and lead investigator.",
  },
  {
    step: 2,
    title: "Register Evidence",
    detail:
      "From Evidence → Register, upload a disk image or memory dump and link it to the case.",
  },
  {
    step: 3,
    title: "Run Pipeline",
    detail:
      "Launch Pipeline → Run against validated evidence. Monitor progress until reporting completes.",
  },
  {
    step: 4,
    title: "View Reports",
    detail:
      "Open Reports to review narrative, JSON artefacts, custody, integrity, and exports.",
  },
];

const ROLES = [
  {
    role: "Admin",
    description:
      "Full access including user management, system settings, audit logs, and all investigative workflows.",
  },
  {
    role: "Investigator",
    description:
      "Create and manage cases, register evidence, run pipelines, generate reports, and run evaluations.",
  },
  {
    role: "Analyst",
    description:
      "Read cases/evidence, run AI analysis, view reports, and inspect artefacts. Cannot manage users.",
  },
  {
    role: "Viewer",
    description:
      "Read-only access to reports and evaluation results. Cannot create cases or run pipelines.",
  },
];

const FAQS = [
  {
    q: "Where do I start after logging in?",
    a: "Use the dashboard quick actions or follow Create Case → Register Evidence → Run Pipeline → View Reports.",
  },
  {
    q: "Why is my evidence not selectable for a pipeline run?",
    a: "Only validated (or processed) evidence appears in the run form. Validate the evidence item first.",
  },
  {
    q: "Is the AI narrative the evidential record?",
    a: "No. The structured JSON artefact layer is authoritative. AI summaries are advisory and must be verified.",
  },
  {
    q: "How do I contribute to the usability study?",
    a: `Open the public questionnaire at ${Routes.Questionnaire.path} — no login is required.`,
  },
];

function FaqItem({ question, answer, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Card border="light" className="shadow-sm mb-2">
      <Card.Header
        className="d-flex justify-content-between align-items-center"
        style={{ cursor: "pointer" }}
        onClick={() => setOpen((prev) => !prev)}
      >
        <span className="fw-semibold">{question}</span>
        <FontAwesomeIcon icon={open ? faCaretDown : faCaretRight} />
      </Card.Header>
      <Collapse in={open}>
        <div>
          <Card.Body className="small text-muted">{answer}</Card.Body>
        </div>
      </Collapse>
    </Card>
  );
}

/**
 * Static help and getting-started guide for DFAT investigators.
 */
export default function Help() {
  const docsUrl = String(config.apiBaseUrl || "")
    .replace(/\/api\/v1\/?$/, "")
    .replace(/\/$/, "");
  const apiDocs = `${docsUrl || "http://localhost:8000"}/docs`;

  return (
    <Container fluid className="px-0">
      <PageHeader
        title="Help"
        subtitle="Getting started, workflows, roles, and FAQs"
      />

      <Card border="light" className="shadow-sm mb-4">
        <Card.Header className="border-bottom border-light">
          <h5 className="mb-0">
            <FontAwesomeIcon icon={faBookOpen} className="me-2 text-primary" />
            Getting Started
          </h5>
        </Card.Header>
        <Card.Body>
          <p>
            DFAT (Digital Forensics Automation Tool) automates acquisition parsing,
            AI triage, dual-output reporting, and benchmark evaluation for digital
            forensic investigations.
          </p>
          <ol className="mb-0">
            <li>Sign in with your investigator or analyst account.</li>
            <li>Confirm system health on the dashboard.</li>
            <li>Create a case and register evidence with hash verification.</li>
            <li>Run the forensic pipeline and review artefacts and reports.</li>
          </ol>
        </Card.Body>
      </Card>

      <Card border="light" className="shadow-sm mb-4">
        <Card.Header className="border-bottom border-light">
          <h5 className="mb-0">
            <FontAwesomeIcon icon={faRoute} className="me-2 text-primary" />
            Workflow
          </h5>
        </Card.Header>
        <Card.Body>
          <p className="text-muted">
            Create Case → Register Evidence → Run Pipeline → View Reports
          </p>
          <Row className="g-3">
            {WORKFLOW.map((item) => (
              <Col xs={12} md={6} key={item.step}>
                <div className="border rounded p-3 h-100">
                  <div className="small text-muted text-uppercase fw-bold mb-1">
                    Step {item.step}
                  </div>
                  <h6>{item.title}</h6>
                  <p className="small mb-0 text-muted">{item.detail}</p>
                </div>
              </Col>
            ))}
          </Row>
        </Card.Body>
      </Card>

      <Card border="light" className="shadow-sm mb-4">
        <Card.Header className="border-bottom border-light">
          <h5 className="mb-0">
            <FontAwesomeIcon icon={faUserShield} className="me-2 text-primary" />
            Role descriptions
          </h5>
        </Card.Header>
        <Card.Body>
          <Row className="g-3">
            {ROLES.map((item) => (
              <Col xs={12} md={6} key={item.role}>
                <h6>{item.role}</h6>
                <p className="small text-muted">{item.description}</p>
              </Col>
            ))}
          </Row>
        </Card.Body>
      </Card>

      <Card border="light" className="shadow-sm mb-4">
        <Card.Header className="border-bottom border-light">
          <h5 className="mb-0">
            <FontAwesomeIcon
              icon={faQuestionCircle}
              className="me-2 text-primary"
            />
            FAQ
          </h5>
        </Card.Header>
        <Card.Body>
          {FAQS.map((item, index) => (
            <FaqItem
              key={item.q}
              question={item.q}
              answer={item.a}
              defaultOpen={index === 0}
            />
          ))}
        </Card.Body>
      </Card>

      <Card border="light" className="shadow-sm mb-4">
        <Card.Body>
          <h5 className="mb-3">API documentation</h5>
          <p className="small text-muted">
            Interactive OpenAPI docs for the DFAT backend (Swagger UI).
          </p>
          <a href={apiDocs} target="_blank" rel="noopener noreferrer">
            {apiDocs}{" "}
            <FontAwesomeIcon icon={faExternalLinkAlt} className="small" />
          </a>
          <hr />
          <div className="small text-muted">
            {config.appName} v{config.appVersion} · Frontend build for Prompt 8 ·
            Canterbury Christ Church University
          </div>
        </Card.Body>
      </Card>
    </Container>
  );
}
