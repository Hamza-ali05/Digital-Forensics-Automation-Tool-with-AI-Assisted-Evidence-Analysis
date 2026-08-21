import React, { useEffect, useMemo, useState } from "react";
import { useHistory, useLocation } from "react-router-dom";
import {
  Alert,
  Button,
  Card,
  Col,
  Container,
  Form,
  ListGroup,
  Row,
  Spinner,
} from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faSave, faTimes } from "@fortawesome/free-solid-svg-icons";

import PageHeader from "components/common/PageHeader";
import { CASE_STATUS, EVIDENCE_TYPE } from "utils/constants";
import { validateRequired } from "utils/validators";
import useNotification from "hooks/useNotification";
import casesService from "services/cases.service";
import evidenceService from "services/evidence.service";
import { Routes } from "routes";

const ELIGIBLE_STATUSES = new Set([CASE_STATUS.OPEN, CASE_STATUS.ACTIVE]);

/**
 * Register a pre-placed forensic image on the server filesystem.
 */
export default function EvidenceRegister() {
  const history = useHistory();
  const location = useLocation();
  const { success, error: notifyError, warning } = useNotification();

  const preselectedCase = useMemo(() => {
    const params = new URLSearchParams(location.search);
    return params.get("caseId") || "";
  }, [location.search]);

  const [cases, setCases] = useState([]);
  const [casesLoading, setCasesLoading] = useState(true);
  const [caseId, setCaseId] = useState(preselectedCase);
  const [filePath, setFilePath] = useState("");
  const [evidenceType, setEvidenceType] = useState(EVIDENCE_TYPE.DISK_IMAGE);
  const [description, setDescription] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [formError, setFormError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [validationResult, setValidationResult] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setCasesLoading(true);
      try {
        const [openResult, activeResult] = await Promise.all([
          casesService.list({ status: CASE_STATUS.OPEN }),
          casesService.list({ status: CASE_STATUS.ACTIVE }),
        ]);
        const merged = [
          ...(openResult?.cases || []),
          ...(activeResult?.cases || []),
        ];
        const seen = new Set();
        const unique = merged.filter((c) => {
          if (seen.has(c.case_id)) return false;
          seen.add(c.case_id);
          return ELIGIBLE_STATUSES.has(String(c.status || "").toLowerCase());
        });
        if (!cancelled) setCases(unique);
      } catch {
        if (!cancelled) setCases([]);
      } finally {
        if (!cancelled) setCasesLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const validate = () => {
    const next = {};
    const caseErr = validateRequired(caseId, "Case");
    const pathErr = validateRequired(filePath, "File path");
    if (caseErr) next.caseId = caseErr;
    if (pathErr) next.filePath = pathErr;
    if (!evidenceType) next.evidenceType = "Evidence type is required";
    setFieldErrors(next);
    return Object.keys(next).length === 0;
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setFormError(null);
    setValidationResult(null);
    if (!validate()) return;

    setSubmitting(true);
    try {
      const result = await evidenceService.register({
        file_path: filePath.trim(),
        case_id: caseId,
        evidence_type: evidenceType,
        description: description.trim() || null,
      });
      setValidationResult(result);

      const newId = result?.evidence_id;
      if (result?.validation_passed) {
        success(
          "Evidence registered",
          "Registration succeeded and automatic validation passed."
        );
      } else {
        warning(
          "Registered with validation issues",
          (result?.validation_failures || []).join("; ") ||
            "Evidence was registered but validation did not pass."
        );
      }

      if (newId) {
        window.setTimeout(() => {
          history.push(Routes.EvidenceDetail.path.replace(":id", newId));
        }, 1200);
      }
    } catch (err) {
      const message =
        err?.message || "Unable to register evidence. Check the server path.";
      setFormError(message);
      notifyError("Registration failed", message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Container fluid className="px-0">
      <PageHeader
        title="Register Evidence"
        subtitle="Associate a pre-placed forensic image with an investigation case"
      />

      <Row className="justify-content-center">
        <Col xs={12} lg={8} xl={6}>
          <Card border="light" className="shadow-sm">
            <Card.Body>
              {formError ? (
                <Alert variant="danger">{formError}</Alert>
              ) : null}

              {validationResult ? (
                <Alert
                  variant={
                    validationResult.validation_passed ? "success" : "warning"
                  }
                >
                  <div className="fw-bold mb-1">
                    {validationResult.validation_passed
                      ? "Validation passed"
                      : "Validation did not pass"}
                  </div>
                  {validationResult.evidence_id ? (
                    <div className="small mb-1">
                      Evidence ID: <code>{validationResult.evidence_id}</code>
                    </div>
                  ) : null}
                  {(validationResult.validation_failures || []).length > 0 ? (
                    <ListGroup variant="flush" className="mt-2">
                      {validationResult.validation_failures.map((item, i) => (
                        <ListGroup.Item key={i} className="px-0 py-1 small">
                          {item}
                        </ListGroup.Item>
                      ))}
                    </ListGroup>
                  ) : (
                    <div className="small">
                      Redirecting to the evidence detail page…
                    </div>
                  )}
                </Alert>
              ) : null}

              <Form onSubmit={handleSubmit} noValidate>
                <Form.Group className="mb-3" controlId="evidenceCase">
                  <Form.Label>
                    Case <span className="text-danger">*</span>
                  </Form.Label>
                  <Form.Select
                    value={caseId}
                    onChange={(e) => setCaseId(e.target.value)}
                    isInvalid={Boolean(fieldErrors.caseId)}
                    disabled={submitting || casesLoading}
                    required
                  >
                    <option value="">
                      {casesLoading
                        ? "Loading cases…"
                        : "Select an open or active case…"}
                    </option>
                    {cases.map((c) => (
                      <option key={c.case_id} value={c.case_id}>
                        {c.case_name} — {c.status}
                      </option>
                    ))}
                  </Form.Select>
                  <Form.Control.Feedback type="invalid">
                    {fieldErrors.caseId}
                  </Form.Control.Feedback>
                  <Form.Text muted>
                    Only open and active cases can receive new evidence.
                  </Form.Text>
                </Form.Group>

                <Form.Group className="mb-3" controlId="evidencePath">
                  <Form.Label>
                    File path <span className="text-danger">*</span>
                  </Form.Label>
                  <Form.Control
                    type="text"
                    value={filePath}
                    onChange={(e) => setFilePath(e.target.value)}
                    isInvalid={Boolean(fieldErrors.filePath)}
                    placeholder="D:\evidence\case-14\disk.E01"
                    disabled={submitting}
                    autoComplete="off"
                  />
                  <Form.Control.Feedback type="invalid">
                    {fieldErrors.filePath}
                  </Form.Control.Feedback>
                  <Form.Text muted>
                    Enter the path to the forensic image on the server filesystem.
                    Files are not uploaded from the browser.
                  </Form.Text>
                </Form.Group>

                <Form.Group className="mb-3">
                  <Form.Label>
                    Evidence type <span className="text-danger">*</span>
                  </Form.Label>
                  <div>
                    <Form.Check
                      inline
                      type="radio"
                      id="type-disk"
                      name="evidenceType"
                      label="Disk Image"
                      value={EVIDENCE_TYPE.DISK_IMAGE}
                      checked={evidenceType === EVIDENCE_TYPE.DISK_IMAGE}
                      onChange={() => setEvidenceType(EVIDENCE_TYPE.DISK_IMAGE)}
                      disabled={submitting}
                    />
                    <Form.Check
                      inline
                      type="radio"
                      id="type-memory"
                      name="evidenceType"
                      label="Memory Dump"
                      value={EVIDENCE_TYPE.MEMORY_DUMP}
                      checked={evidenceType === EVIDENCE_TYPE.MEMORY_DUMP}
                      onChange={() => setEvidenceType(EVIDENCE_TYPE.MEMORY_DUMP)}
                      disabled={submitting}
                    />
                  </div>
                  {fieldErrors.evidenceType ? (
                    <div className="invalid-feedback d-block">
                      {fieldErrors.evidenceType}
                    </div>
                  ) : null}
                </Form.Group>

                <Form.Group className="mb-4" controlId="evidenceDescription">
                  <Form.Label>Description</Form.Label>
                  <Form.Control
                    as="textarea"
                    rows={3}
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Optional acquisition notes"
                    disabled={submitting}
                  />
                </Form.Group>

                <div className="d-flex justify-content-end gap-2">
                  <Button
                    type="button"
                    variant="outline-secondary"
                    disabled={submitting}
                    onClick={() => history.push(Routes.Evidence.path)}
                  >
                    <FontAwesomeIcon icon={faTimes} className="me-2" />
                    Cancel
                  </Button>
                  <Button type="submit" variant="primary" disabled={submitting}>
                    {submitting ? (
                      <>
                        <Spinner animation="border" size="sm" className="me-2" />
                        Registering…
                      </>
                    ) : (
                      <>
                        <FontAwesomeIcon icon={faSave} className="me-2" />
                        Register Evidence
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
