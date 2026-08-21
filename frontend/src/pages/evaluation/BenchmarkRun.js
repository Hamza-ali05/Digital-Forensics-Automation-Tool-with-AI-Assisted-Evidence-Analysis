import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Button,
  Card,
  Col,
  Container,
  Form,
  Row,
  Spinner,
} from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faHistory, faPlay } from "@fortawesome/free-solid-svg-icons";

import PageHeader from "components/common/PageHeader";
import ApiErrorDisplay from "components/common/ApiErrorDisplay";
import EmptyState from "components/common/EmptyState";
import SkeletonLoader from "components/common/SkeletonLoader";
import MetricGauge, { scoreToPercent } from "components/forensic/MetricGauge";
import { EVIDENCE_STATUS } from "utils/constants";
import { formatDate, formatDuration } from "utils/formatters";
import {
  evidenceOptionId,
  evidenceOptionLabel,
  loadEvidenceOptions,
} from "utils/artefactLoader";
import { validateRequired } from "utils/validators";
import usePermission from "hooks/usePermission";
import useNotification from "hooks/useNotification";
import evaluationService from "services/evaluation.service";
import { Routes } from "routes";

const PRECISION_THRESHOLDS = { warning: 50, success: 80 };
const TTT_CAP_SECONDS = 300;

function shortId(id) {
  return id ? String(id).slice(0, 8) : "—";
}

function isProcessed(item) {
  return String(item?.status || "").toLowerCase() === EVIDENCE_STATUS.PROCESSED;
}

function sortLatest(results) {
  return [...(results || [])].sort((a, b) => {
    const ta = new Date(a.evaluated_at || 0).getTime();
    const tb = new Date(b.evaluated_at || 0).getTime();
    return tb - ta;
  });
}

function tttGaugeValue(seconds) {
  const n = Number(seconds) || 0;
  return Math.min(100, (n / TTT_CAP_SECONDS) * 100);
}

function coveragePercent(result) {
  const expected = Number(result?.artefacts_expected) || 0;
  const recovered = Number(result?.artefacts_recovered) || 0;
  if (!expected) return recovered ? 100 : 0;
  return (recovered / expected) * 100;
}

function errorRatePercent(result) {
  const expected = Number(result?.artefacts_expected) || 0;
  const fp = Number(result?.false_positives) || 0;
  const fn = Number(result?.false_negatives) || 0;
  const denom = expected || fp + fn;
  if (!denom) return 0;
  return Math.min(100, ((fp + fn) / denom) * 100);
}

function ResultGauges({ result }) {
  if (!result) return null;
  const precisionPct = scoreToPercent(result.precision);
  const precisionGreen = precisionPct > 80;

  return (
    <>
      <p className="small text-muted mb-4">
        {result.dataset_name || "Dataset"} · {formatDate(result.evaluated_at)}
        {result.benchmark_id ? ` · ${shortId(result.benchmark_id)}` : ""}
      </p>
      <Row className="g-3">
        <Col xs={12} sm={6} xl={4}>
          <Card border="light" className="shadow-sm h-100">
            <Card.Body className="text-center">
              <MetricGauge
                value={precisionPct}
                label="Precision"
                thresholds={PRECISION_THRESHOLDS}
              />
              <div
                className={`small fw-bold mt-1 ${
                  precisionGreen ? "text-success" : "text-muted"
                }`}
              >
                {precisionPct.toFixed(1)}%
                {precisionGreen ? " · above 80%" : ""}
              </div>
            </Card.Body>
          </Card>
        </Col>
        <Col xs={12} sm={6} xl={4}>
          <Card border="light" className="shadow-sm h-100">
            <Card.Body className="text-center">
              <MetricGauge value={scoreToPercent(result.recall)} label="Recall" />
            </Card.Body>
          </Card>
        </Col>
        <Col xs={12} sm={6} xl={4}>
          <Card border="light" className="shadow-sm h-100">
            <Card.Body className="text-center">
              <MetricGauge
                value={scoreToPercent(result.f1_score)}
                label="F1 Score"
              />
            </Card.Body>
          </Card>
        </Col>
        <Col xs={12} sm={6} xl={4}>
          <Card border="light" className="shadow-sm h-100">
            <Card.Body className="text-center">
              <MetricGauge
                value={tttGaugeValue(result.time_to_triage_seconds)}
                label="Time to Triage"
                invert
                display={formatDuration(result.time_to_triage_seconds)}
              />
            </Card.Body>
          </Card>
        </Col>
        <Col xs={12} sm={6} xl={4}>
          <Card border="light" className="shadow-sm h-100">
            <Card.Body className="text-center">
              <MetricGauge
                value={coveragePercent(result)}
                label="Artefacts Expected / Recovered"
                display={`${result.artefacts_recovered ?? 0} / ${
                  result.artefacts_expected ?? 0
                }`}
              />
            </Card.Body>
          </Card>
        </Col>
        <Col xs={12} sm={6} xl={4}>
          <Card border="light" className="shadow-sm h-100">
            <Card.Body className="text-center">
              <MetricGauge
                value={errorRatePercent(result)}
                label="False Positives / False Negatives"
                invert
                display={`${result.false_positives ?? 0} / ${
                  result.false_negatives ?? 0
                }`}
              />
            </Card.Body>
          </Card>
        </Col>
      </Row>
    </>
  );
}

/**
 * Run DFRWS / CFReDS benchmark comparison and view the latest metrics.
 */
export default function BenchmarkRun() {
  const { canCreate } = usePermission("evaluation");
  const { success, error: notifyError } = useNotification();

  const [evidenceItems, setEvidenceItems] = useState([]);
  const [datasets, setDatasets] = useState({ dfrws: [], cfreds: [] });
  const [loadingLists, setLoadingLists] = useState(true);
  const [listError, setListError] = useState(null);

  const [evidenceId, setEvidenceId] = useState("");
  const [datasetSource, setDatasetSource] = useState("dfrws");
  const [datasetName, setDatasetName] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);

  const [latest, setLatest] = useState(null);
  const [loadingLatest, setLoadingLatest] = useState(true);

  const datasetOptions = useMemo(() => {
    const key = datasetSource === "cfreds" ? "cfreds" : "dfrws";
    return datasets[key] || [];
  }, [datasets, datasetSource]);

  const loadLists = useCallback(async () => {
    setLoadingLists(true);
    setListError(null);
    try {
      const [evidence, datasetPayload] = await Promise.all([
        loadEvidenceOptions(),
        evaluationService.getDatasets(),
      ]);
      setEvidenceItems((evidence || []).filter(isProcessed));
      setDatasets({
        dfrws: datasetPayload?.dfrws || [],
        cfreds: datasetPayload?.cfreds || [],
      });
    } catch (err) {
      setListError(err);
      setEvidenceItems([]);
    } finally {
      setLoadingLists(false);
    }
  }, []);

  const loadLatest = useCallback(async () => {
    setLoadingLatest(true);
    try {
      const results = await evaluationService.getResults();
      setLatest(sortLatest(results)[0] || null);
    } catch {
      setLatest(null);
    } finally {
      setLoadingLatest(false);
    }
  }, []);

  useEffect(() => {
    loadLists().catch(() => {});
    loadLatest().catch(() => {});
  }, [loadLists, loadLatest]);

  useEffect(() => {
    if (!datasetOptions.includes(datasetName)) {
      setDatasetName(datasetOptions[0] || "");
    }
  }, [datasetOptions, datasetName]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    const errors = {
      evidenceId: validateRequired(evidenceId, "Evidence"),
      datasetName: validateRequired(datasetName, "Dataset name"),
    };
    setFieldErrors(errors);
    if (errors.evidenceId || errors.datasetName) return;

    setSubmitting(true);
    setFormError(null);
    try {
      const result = await evaluationService.runBenchmark({
        evidence_id: evidenceId,
        ground_truth_dataset: datasetName,
        dataset_source: datasetSource,
        dataset_name: datasetName,
      });
      setLatest(result);
      success(
        "Benchmark complete",
        `${datasetName} scored F1 ${scoreToPercent(result.f1_score).toFixed(1)}%.`
      );
    } catch (err) {
      setFormError(err);
      notifyError(
        "Benchmark failed",
        err?.message || "Could not run the benchmark comparison."
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Container fluid className="px-0">
      <PageHeader
        title="Benchmark Evaluation"
        subtitle="Compare recovered artefacts against local DFRWS or CFReDS ground truth"
        actions={
          <Button
            as={Link}
            to={Routes.EvaluationBenchmarkHistory.path}
            variant="outline-secondary"
          >
            <FontAwesomeIcon icon={faHistory} className="me-2" />
            Benchmark History
          </Button>
        }
      />

      {listError ? (
        <ApiErrorDisplay error={listError} onRetry={loadLists} className="mb-3" />
      ) : null}

      <Card border="light" className="shadow-sm mb-4">
        <Card.Header className="border-bottom border-light">
          <h5 className="mb-0">Run Benchmark</h5>
        </Card.Header>
        <Card.Body>
          {loadingLists ? (
            <SkeletonLoader type="card" rows={2} />
          ) : (
            <Form onSubmit={handleSubmit}>
              {formError ? (
                <ApiErrorDisplay error={formError} className="mb-3" />
              ) : null}
              <Row className="g-3">
                <Col xs={12} md={6}>
                  <Form.Group>
                    <Form.Label>Evidence</Form.Label>
                    <Form.Select
                      value={evidenceId}
                      onChange={(event) => setEvidenceId(event.target.value)}
                      isInvalid={Boolean(fieldErrors.evidenceId)}
                      aria-label="Evidence selector"
                    >
                      <option value="">Select processed evidence…</option>
                      {evidenceItems.map((item) => {
                        const id = evidenceOptionId(item);
                        return (
                          <option key={id} value={id}>
                            {evidenceOptionLabel(item)}
                          </option>
                        );
                      })}
                    </Form.Select>
                    <Form.Control.Feedback type="invalid">
                      {fieldErrors.evidenceId}
                    </Form.Control.Feedback>
                    {!evidenceItems.length ? (
                      <Form.Text className="text-muted">
                        Only evidence in PROCESSED status can be benchmarked.
                      </Form.Text>
                    ) : null}
                  </Form.Group>
                </Col>
                <Col xs={12} md={6}>
                  <Form.Group>
                    <Form.Label>Dataset source</Form.Label>
                    <div>
                      <Form.Check
                        inline
                        type="radio"
                        id="source-dfrws"
                        name="datasetSource"
                        label="DFRWS"
                        checked={datasetSource === "dfrws"}
                        onChange={() => setDatasetSource("dfrws")}
                      />
                      <Form.Check
                        inline
                        type="radio"
                        id="source-cfreds"
                        name="datasetSource"
                        label="CFReDS"
                        checked={datasetSource === "cfreds"}
                        onChange={() => setDatasetSource("cfreds")}
                      />
                    </div>
                  </Form.Group>
                  <Form.Group className="mt-3">
                    <Form.Label>Dataset name</Form.Label>
                    <Form.Select
                      value={datasetName}
                      onChange={(event) => setDatasetName(event.target.value)}
                      isInvalid={Boolean(fieldErrors.datasetName)}
                      aria-label="Dataset name"
                    >
                      <option value="">Select dataset…</option>
                      {datasetOptions.map((name) => (
                        <option key={name} value={name}>
                          {name}
                        </option>
                      ))}
                    </Form.Select>
                    <Form.Control.Feedback type="invalid">
                      {fieldErrors.datasetName}
                    </Form.Control.Feedback>
                  </Form.Group>
                </Col>
              </Row>
              <div className="mt-4">
                <Button
                  type="submit"
                  variant="primary"
                  disabled={submitting || !canCreate}
                >
                  {submitting ? (
                    <Spinner animation="border" size="sm" className="me-2" />
                  ) : (
                    <FontAwesomeIcon icon={faPlay} className="me-2" />
                  )}
                  Run Benchmark
                </Button>
                {!canCreate ? (
                  <span className="small text-muted ms-3">
                    Your role cannot create evaluation runs.
                  </span>
                ) : null}
              </div>
            </Form>
          )}
        </Card.Body>
      </Card>

      <Card border="light" className="shadow-sm mb-4">
        <Card.Header className="border-bottom border-light">
          <h5 className="mb-0">Latest Result</h5>
        </Card.Header>
        <Card.Body>
          {loadingLatest && !latest ? (
            <SkeletonLoader type="card" rows={2} />
          ) : latest ? (
            <ResultGauges result={latest} />
          ) : (
            <EmptyState
              title="No benchmark results yet"
              description="Run a DFRWS or CFReDS comparison to populate precision, recall, and F1."
            />
          )}
        </Card.Body>
      </Card>
    </Container>
  );
}
