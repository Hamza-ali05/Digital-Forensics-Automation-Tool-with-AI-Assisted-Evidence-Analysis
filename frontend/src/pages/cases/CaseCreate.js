import React, { useState } from "react";
import { useHistory } from "react-router-dom";
import {
  Alert,
  Button,
  Card,
  Col,
  Container,
  Form,
  Row,
  Spinner,
} from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faSave, faTimes } from "@fortawesome/free-solid-svg-icons";

import PageHeader from "components/common/PageHeader";
import { validateRequired } from "utils/validators";
import useNotification from "hooks/useNotification";
import casesService from "services/cases.service";
import { Routes } from "routes";

/**
 * Create a new investigation case.
 */
export default function CaseCreate() {
  const history = useHistory();
  const { success, error: notifyError } = useNotification();

  const [caseName, setCaseName] = useState("");
  const [description, setDescription] = useState("");
  const [tagsInput, setTagsInput] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [formError, setFormError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const parseTags = (value) =>
    String(value || "")
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean);

  const validate = () => {
    const next = {};
    const required = validateRequired(caseName, "Case name");
    if (required) {
      next.caseName = required;
    } else if (caseName.trim().length < 3) {
      next.caseName = "Case name must be at least 3 characters";
    } else if (caseName.trim().length > 255) {
      next.caseName = "Case name must be at most 255 characters";
    }
    setFieldErrors(next);
    return Object.keys(next).length === 0;
  };

  const buildDescription = () => {
    const desc = description.trim();
    const tags = parseTags(tagsInput);
    // Backend create schema accepts name + description only; persist tags inline.
    if (!tags.length) return desc || null;
    const tagLine = `Tags: ${tags.join(", ")}`;
    return desc ? `${desc}\n\n${tagLine}` : tagLine;
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setFormError(null);
    if (!validate()) return;

    setSubmitting(true);
    try {
      const created = await casesService.create({
        case_name: caseName.trim(),
        description: buildDescription(),
      });
      const newId = created?.case_id;
      success("Case created", `Case "${caseName.trim()}" was created.`);
      if (newId) {
        history.push(Routes.CaseDetail.path.replace(":id", newId));
      } else {
        history.push(Routes.Cases.path);
      }
    } catch (err) {
      const message =
        err?.message || "Unable to create the case. Please try again.";
      setFormError(message);
      if (err?.details && typeof err.details === "object") {
        const mapped = {};
        if (err.details.case_name) mapped.caseName = String(err.details.case_name);
        if (err.details.description) {
          mapped.description = String(err.details.description);
        }
        if (Object.keys(mapped).length) setFieldErrors(mapped);
      }
      notifyError("Create failed", message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Container fluid className="px-0">
      <PageHeader
        title="New Case"
        subtitle="Open a new investigation case"
      />

      <Row className="justify-content-center">
        <Col xs={12} lg={8} xl={6}>
          <Card border="light" className="shadow-sm">
            <Card.Body>
              {formError ? (
                <Alert variant="danger" className="mb-3">
                  {formError}
                </Alert>
              ) : null}

              <Form onSubmit={handleSubmit} noValidate>
                <Form.Group className="mb-3" controlId="caseName">
                  <Form.Label>
                    Case Name <span className="text-danger">*</span>
                  </Form.Label>
                  <Form.Control
                    type="text"
                    value={caseName}
                    onChange={(e) => setCaseName(e.target.value)}
                    isInvalid={Boolean(fieldErrors.caseName)}
                    placeholder="e.g. Insider threat — workstation 14"
                    disabled={submitting}
                    autoFocus
                  />
                  <Form.Control.Feedback type="invalid">
                    {fieldErrors.caseName}
                  </Form.Control.Feedback>
                  <Form.Text muted>Minimum 3 characters.</Form.Text>
                </Form.Group>

                <Form.Group className="mb-3" controlId="caseDescription">
                  <Form.Label>Description</Form.Label>
                  <Form.Control
                    as="textarea"
                    rows={4}
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    isInvalid={Boolean(fieldErrors.description)}
                    placeholder="Optional case background and scope"
                    disabled={submitting}
                  />
                  <Form.Control.Feedback type="invalid">
                    {fieldErrors.description}
                  </Form.Control.Feedback>
                </Form.Group>

                <Form.Group className="mb-4" controlId="caseTags">
                  <Form.Label>Tags</Form.Label>
                  <Form.Control
                    type="text"
                    value={tagsInput}
                    onChange={(e) => setTagsInput(e.target.value)}
                    placeholder="malware, memory, insider (comma-separated)"
                    disabled={submitting}
                  />
                  <Form.Text muted>
                    Optional. Comma-separated labels stored with the description.
                  </Form.Text>
                </Form.Group>

                <div className="d-flex justify-content-end gap-2">
                  <Button
                    type="button"
                    variant="outline-secondary"
                    disabled={submitting}
                    onClick={() => history.push(Routes.Cases.path)}
                  >
                    <FontAwesomeIcon icon={faTimes} className="me-2" />
                    Cancel
                  </Button>
                  <Button type="submit" variant="primary" disabled={submitting}>
                    {submitting ? (
                      <>
                        <Spinner
                          animation="border"
                          size="sm"
                          className="me-2"
                        />
                        Creating…
                      </>
                    ) : (
                      <>
                        <FontAwesomeIcon icon={faSave} className="me-2" />
                        Create Case
                      </>
                    )}
                  </Button>
                </div>
              </Form>
            </Card.Body>
          </Card>
        </Col>
      </Row>
    </Container>
  );
}
