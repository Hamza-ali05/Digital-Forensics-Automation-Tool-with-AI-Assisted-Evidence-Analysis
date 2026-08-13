import React, { useEffect, useMemo, useState } from "react";
import { useHistory, useLocation } from "react-router-dom";
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
import {
  faCheckCircle,
  faPlay,
  faTimes,
  faTimesCircle,
} from "@fortawesome/free-solid-svg-icons";

import PageHeader from "components/common/PageHeader";
import { EVIDENCE_STATUS, PIPELINE_MODE } from "utils/constants";
import { formatCaseId, formatBytes } from "utils/formatters";
import { validateRequired } from "utils/validators";
import useNotification from "hooks/useNotification";
import pipelineService from "services/pipeline.service";
import evidenceService from "services/evidence.service";
import casesService from "services/cases.service";
import aiService, { isAiHealthy } from "services/ai.service";
import { Routes } from "routes";

/**
 * Submit a new forensic pipeline job against validated evidence.
 */
export default function PipelineRun() {
  const history = useHistory();
  const location = useLocation();
  const { success, error: notifyError, warning } = useNotification();

  const query = useMemo(() => new URLSearchParams(location.search), [
    location.search,
  ]);
  const preEvidence = query.get("evidenceId") || "";
  const preCase = query.get("caseId") || "";

  const [evidenceItems, setEvidenceItems] = useState([]);
  const [cases, setCases] = useState([]);
  const [loadingLists, setLoadingLists] = useState(true);
  const [evidenceId, setEvidenceId] = useState(preEvidence);
  const [caseId, setCaseId] = useState(preCase);
  const [mode, setMode] = useState(PIPELINE_MODE.FULL);
  const [useFallback, setUseFallback] = useState(false);
  const [aiHealth, setAiHealth] = useState(null);
  const [aiChecking, setAiChecking] = useState(true);
  const [fieldErrors, setFieldErrors] = useState({});
  const [formError, setFormError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoadingLists(true);
      try {
        const [inventory, caseList] = await Promise.all([
          evidenceService.getInventory(),
          casesService.list().catch(() => ({ cases: [] })),
        ]);
        if (cancelled) return;
        const items = Array.isArray(inventory?.items) ? inventory.items : [];
        const validated = items.filter(
          (item) =>
            String(item.status || "").toLowerCase() === EVIDENCE_STATUS.VALIDATED ||
            String(item.status || "").toLowerCase() === EVIDENCE_STATUS.PROCESSED
        );
        // Prefer validated; if none, still show validated+processed; allow validated primarily
        const preferred = items.filter(
          (item) =>
            String(item.status || "").toLowerCase() === EVIDENCE_STATUS.VALIDATED
        );
        setEvidenceItems(preferred.length ? preferred : validated);
        setCases(Array.isArray(caseList?.cases) ? caseList.cases : []);
      } catch {
        if (!cancelled) {
          setEvidenceItems([]);
          setCases([]);
        }
      } finally {
        if (!cancelled) setLoadingLists(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setAiChecking(true);
      try {
        const health = await aiService.getHealth();
        if (!cancelled) setAiHealth(health);
      } catch {
        if (!cancelled) setAiHealth({ is_healthy: false });
      } finally {
        if (!cancelled) setAiChecking(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const selectedEvidence = useMemo(
    () => evidenceItems.find((item) => item.evidence_id === evidenceId) || null,
    [evidenceItems, evidenceId]
  );

  useEffect(() => {
    if (selectedEvidence?.case_id) {
      setCaseId(selectedEvidence.case_id);
    }
  }, [selectedEvidence]);

  const aiOk = isAiHealthy(aiHealth);

  const validate = () => {
    const next = {};
    const evErr = validateRequired(evidenceId, "Evidence");
    const caseErr = validateRequired(caseId, "Case");
    if (evErr) next.evidenceId = evErr;
    if (caseErr) next.caseId = caseErr;
    if (!mode) next.mode = "Mode is required";
    setFieldErrors(next);
    return Object.keys(next).length === 0;
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setFormError(null);
    if (!validate()) return;

    if (!aiOk && !useFallback && mode !== PIPELINE_MODE.PARSE_ONLY) {
      warning(
        "AI engine unavailable",
        "Enable Use Fallback Analyzer or choose Parse Only when the LLM is offline."
      );
    }

    setSubmitting(true);
    try {
      const job = await pipelineService.run({
        evidence_id: evidenceId,
        case_id: caseId,
        mode,
        use_fallback: useFallback,
      });
      const jobId = job?.job_id;
      success("Pipeline started", `Job ${String(jobId || "").slice(0, 8)} queued.`);
      if (jobId) {
        history.push(Routes.PipelineDetail.path.replace(":jobId", jobId));
      } else {
        history.push(Routes.Pipeline.path);
      }
    } catch (err) {
      const message = err?.message || "Unable to start the pipeline.";
      setFormError(message);
      notifyError("Start failed", message);
    } finally {
      setSubmitting(false);
    }
  };

  const caseLabel = (id) => {
    const found = cases.find((c) => c.case_id === id);
    if (found) return `${found.case_name} (${found.status})`;
    if (selectedEvidence?.case_name) {
      return `${selectedEvidence.case_name} (${formatCaseId(id)})`;
    }
    return formatCaseId(id);
  };

  return (
    <Container fluid className="px-0">
      <PageHeader
        title="Run Pipeline"
        subtitle="Start forensic analysis against validated evidence"
        breadcrumbs={[
          { label: "Home", to: Routes.Dashboard.path },
          { label: "Pipeline", to: Routes.Pipeline.path },
          { label: "Run" },
        ]}
      />

      <Row className="justify-content-center">
        <Col xs={12} lg={8} xl={6}>
          <Card border="light" className="shadow-sm mb-3">
            <Card.Body className="d-flex align-items-center justify-content-between flex-wrap gap-2">
              <div>
                <div className="fw-bold">AI Engine Status</div>
                <div className="small text-muted">
                  {aiChecking
                    ? "Checking local LLM…"
                    : aiHealth?.model_name
                      ? `Model: ${aiHealth.model_name}`
                      : "Local Ollama endpoint"}
                </div>
              </div>
              <div className="d-flex align-items-center">
                {aiChecking ? (
                  <Spinner animation="border" size="sm" />
                ) : aiOk ? (
                  <span className="text-success fw-bold">
                    <FontAwesomeIcon icon={faCheckCircle} className="me-2" />
                    Healthy
                  </span>
                ) : (
                  <span className="text-danger fw-bold">
                    <FontAwesomeIcon icon={faTimesCircle} className="me-2" />
                    Unavailable
                  </span>
                )}
              </div>
            </Card.Body>
          </Card>

          <Card border="light" className="shadow-sm">
            <Card.Body>
              {formError ? <Alert variant="danger">{formError}</Alert> : null}
              {!aiOk && !aiChecking ? (
                <Alert variant="warning">
                  The local AI engine is unavailable. Use the fallback analyzer
                  or Parse Only mode to continue without the LLM.
                </Alert>
              ) : null}

              <Form onSubmit={handleSubmit} noValidate>
                <Form.Group className="mb-3" controlId="pipelineEvidence">
                  <Form.Label>
                    Evidence <span className="text-danger">*</span>
                  </Form.Label>
                  <Form.Select
                    value={evidenceId}
                    onChange={(e) => setEvidenceId(e.target.value)}
                    isInvalid={Boolean(fieldErrors.evidenceId)}
                    disabled={submitting || loadingLists}
                    required
                  >
                    <option value="">
                      {loadingLists
                        ? "Loading validated evidence…"
                        : evidenceItems.length
                          ? "Select validated evidence…"
                          : "No validated evidence available"}
                    </option>
                    {evidenceItems.map((item) => (
                      <option key={item.evidence_id} value={item.evidence_id}>
                        {item.file_name} — {item.status} (
                        {formatBytes(item.file_size_bytes)})
                      </option>
                    ))}
                  </Form.Select>
                  <Form.Control.Feedback type="invalid">
                    {fieldErrors.evidenceId}
                  </Form.Control.Feedback>
                  <Form.Text muted>
                    Only evidence in <strong>validated</strong> status can be
                    analysed.
                  </Form.Text>
                </Form.Group>

                <Form.Group className="mb-3" controlId="pipelineCase">
                  <Form.Label>
                    Case <span className="text-danger">*</span>
                  </Form.Label>
                  <Form.Control
                    type="text"
                    value={caseId ? caseLabel(caseId) : ""}
                    readOnly
                    isInvalid={Boolean(fieldErrors.caseId)}
                    placeholder="Auto-filled from evidence"
                  />
                  <Form.Control.Feedback type="invalid">
                    {fieldErrors.caseId}
                  </Form.Control.Feedback>
                  <Form.Text muted>
                    Case is taken from the selected evidence registration.
                  </Form.Text>
                </Form.Group>

                <Form.Group className="mb-3">
                  <Form.Label>
                    Mode <span className="text-danger">*</span>
                  </Form.Label>
                  <div>
                    <Form.Check
                      type="radio"
                      id="mode-full"
                      name="pipelineMode"
                      label="Full Analysis"
                      checked={mode === PIPELINE_MODE.FULL}
                      onChange={() => setMode(PIPELINE_MODE.FULL)}
                      disabled={submitting}
                    />
                    <Form.Check
                      type="radio"
                      id="mode-parse"
                      name="pipelineMode"
                      label="Parse Only"
                      checked={mode === PIPELINE_MODE.PARSE_ONLY}
                      onChange={() => setMode(PIPELINE_MODE.PARSE_ONLY)}
                      disabled={submitting}
                    />
                    <Form.Check
                      type="radio"
                      id="mode-triage"
                      name="pipelineMode"
                      label="Triage Only"
                      checked={mode === PIPELINE_MODE.TRIAGE_ONLY}
                      onChange={() => setMode(PIPELINE_MODE.TRIAGE_ONLY)}
                      disabled={submitting}
                    />
                  </div>
                </Form.Group>

                <Form.Group className="mb-4">
                  <Form.Check
                    type="checkbox"
                    id="use-fallback"
                    label="Use Fallback Analyzer"
                    checked={useFallback}
                    onChange={(e) => setUseFallback(e.target.checked)}
                    disabled={submitting}
                  />
                  <Form.Text muted>
                    Use rule-based triage instead of LLM
                  </Form.Text>
                </Form.Group>

                <div className="d-flex justify-content-end gap-2">
                  <Button
                    type="button"
                    variant="outline-secondary"
                    disabled={submitting}
                    onClick={() => history.push(Routes.Pipeline.path)}
                  >
                    <FontAwesomeIcon icon={faTimes} className="me-2" />
                    Cancel
                  </Button>
                  <Button
                    type="submit"
                    variant="primary"
                    disabled={submitting || loadingLists || !evidenceItems.length}
                  >
                    {submitting ? (
                      <>
                        <Spinner animation="border" size="sm" className="me-2" />
                        Starting…
                      </>
                    ) : (
                      <>
                        <FontAwesomeIcon icon={faPlay} className="me-2" />
                        Start Pipeline
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
