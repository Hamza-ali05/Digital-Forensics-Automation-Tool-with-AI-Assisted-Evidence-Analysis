import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Container,
  Form,
  Row,
  Spinner,
  Table,
} from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faBroom,
  faInfoCircle,
  faPlay,
  faSyncAlt,
} from "@fortawesome/free-solid-svg-icons";

import PageHeader from "components/common/PageHeader";
import StatusBadge from "components/common/StatusBadge";
import ApiErrorDisplay from "components/common/ApiErrorDisplay";
import EmptyState from "components/common/EmptyState";
import SkeletonLoader from "components/common/SkeletonLoader";
import ConfirmDialog from "components/common/ConfirmDialog";
import ArtefactDetailModal from "components/forensic/ArtefactDetailModal";
import ChatInterface from "components/forensic/ChatInterface";
import ConfidenceMeter from "components/forensic/ConfidenceMeter";
import {
  EVIDENCE_STATUS,
  USER_ROLES,
} from "utils/constants";
import {
  formatArtefactId,
  formatDate,
  formatDateRelative,
  formatPercentage,
} from "utils/formatters";
import {
  evidenceOptionId,
  evidenceOptionLabel,
  loadArtefactsForEvidence,
  loadEvidenceOptions,
} from "utils/artefactLoader";
import useAuth from "hooks/useAuth";
import usePermission from "hooks/usePermission";
import useNotification from "hooks/useNotification";
import useConfirmDialog from "hooks/useConfirmDialog";
import aiService, { isAiHealthy } from "services/ai.service";
import { Routes } from "routes";

const ANALYSIS_TYPE = {
  CLASSIFY: "classify",
  FULL: "full",
};

const HIGH_PLUS = new Set(["critical", "high"]);

function humanise(value) {
  return String(value || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function buildSuggestions(artefacts) {
  if (!artefacts.length) {
    return [
      "What artefacts were recovered from this evidence?",
      "Are there any CRITICAL findings requiring immediate attention?",
      "What follow-up acquisition steps are recommended?",
    ];
  }

  const highPlus = artefacts.filter((item) =>
    HIGH_PLUS.has(String(item.suspicion_level || "").toLowerCase())
  );
  const focus = (highPlus.length ? highPlus : artefacts).slice(0, 3);
  const suggestions = focus.map((item) => {
    const id = formatArtefactId(item.artefact_id);
    return `What is the forensic significance of artefact ${id} (${humanise(
      item.category
    )}, ${humanise(item.suspicion_level)})?`;
  });

  const categories = [
    ...new Set(artefacts.map((item) => item.category).filter(Boolean)),
  ];
  if (categories.length) {
    suggestions.push(
      `How do the ${categories.slice(0, 3).map(humanise).join(", ")} artefacts relate temporally?`
    );
  }
  suggestions.push(
    "Which HIGH or CRITICAL artefacts suggest persistence or lateral movement?"
  );

  const unique = [];
  suggestions.forEach((question) => {
    if (!unique.includes(question)) unique.push(question);
  });
  return unique.slice(0, 5);
}

function HealthDot({ ok }) {
  const colour = ok ? "#198754" : "#dc3545";
  return (
    <span
      aria-hidden
      className="d-inline-block rounded-circle me-2"
      style={{
        width: 12,
        height: 12,
        backgroundColor: colour,
        boxShadow: `0 0 0 3px ${colour}22`,
      }}
    />
  );
}

/**
 * AI-assisted evidence analysis: health, classify/summarise, and investigator Q&A.
 */
export default function AIAnalysis() {
  const location = useLocation();
  const { role } = useAuth();
  const { canCreate } = usePermission("analysis");
  const isAdmin = role === USER_ROLES.ADMIN;
  const { success, error: notifyError } = useNotification();
  const { dialogProps, openDialog } = useConfirmDialog();

  const queryEvidenceId = useMemo(() => {
    const params = new URLSearchParams(location.search || "");
    return params.get("evidence_id") || params.get("evidence") || "";
  }, [location.search]);

  const [health, setHealth] = useState(null);
  const [cacheStats, setCacheStats] = useState(null);
  const [healthLoading, setHealthLoading] = useState(true);
  const [healthError, setHealthError] = useState(null);
  const [clearingCache, setClearingCache] = useState(false);

  const [evidenceOptions, setEvidenceOptions] = useState([]);
  const [evidenceId, setEvidenceId] = useState(queryEvidenceId);
  const [artefacts, setArtefacts] = useState([]);
  const [analysisType, setAnalysisType] = useState(ANALYSIS_TYPE.CLASSIFY);
  const [useFallback, setUseFallback] = useState(false);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState(null);
  const [classifyResult, setClassifyResult] = useState(null);
  const [summaryResult, setSummaryResult] = useState(null);

  const [messages, setMessages] = useState([]);
  const [askLoading, setAskLoading] = useState(false);

  const [detailArtefact, setDetailArtefact] = useState(null);
  const [detailOpen, setDetailOpen] = useState(false);

  useEffect(() => {
    if (queryEvidenceId) setEvidenceId(queryEvidenceId);
  }, [queryEvidenceId]);

  const refreshHealth = useCallback(async () => {
    setHealthLoading(true);
    setHealthError(null);
    try {
      const status = await aiService.getHealth();
      setHealth(status);
      if (isAdmin) {
        try {
          const stats = await aiService.getCacheStats();
          setCacheStats(stats);
        } catch {
          setCacheStats(null);
        }
      } else {
        setCacheStats(null);
      }
    } catch (err) {
      setHealth({ is_healthy: false });
      setHealthError(err);
    } finally {
      setHealthLoading(false);
    }
  }, [isAdmin]);

  useEffect(() => {
    refreshHealth().catch(() => {});
  }, [refreshHealth]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const options = await loadEvidenceOptions();
        if (cancelled) return;
        const processed = options.filter(
          (item) =>
            String(item.status || "").toLowerCase() === EVIDENCE_STATUS.PROCESSED
        );
        setEvidenceOptions(processed.length ? processed : options);
      } catch {
        if (!cancelled) setEvidenceOptions([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setArtefacts([]);
    setMessages([]);
    setClassifyResult(null);
    setSummaryResult(null);
    if (!evidenceId) return undefined;
    (async () => {
      try {
        const { artefacts: rows } = await loadArtefactsForEvidence(evidenceId);
        if (!cancelled) setArtefacts(rows);
      } catch {
        if (!cancelled) setArtefacts([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [evidenceId]);

  const aiOk = isAiHealthy(health);
  const suggestions = useMemo(() => buildSuggestions(artefacts), [artefacts]);
  const artefactById = useMemo(() => {
    const map = new Map();
    artefacts.forEach((item) => {
      if (item?.artefact_id) map.set(item.artefact_id, item);
    });
    return map;
  }, [artefacts]);

  const hitRate = cacheStats
    ? Number(cacheStats.hit_rate) <= 1
      ? Number(cacheStats.hit_rate) * 100
      : Number(cacheStats.hit_rate)
    : null;

  const handleClearCache = async () => {
    try {
      await openDialog({
        title: "Clear AI cache",
        message:
          "This removes cached LLM responses. Subsequent analysis will re-query the local model.",
        confirmLabel: "Clear cache",
        variant: "danger",
      });
    } catch {
      return;
    }
    setClearingCache(true);
    try {
      const result = await aiService.clearCache();
      success(
        "Cache cleared",
        `${result?.cleared_entries ?? 0} cached entries were removed.`
      );
      await refreshHealth();
    } catch (err) {
      notifyError(
        "Clear cache failed",
        err?.response?.data?.detail || err?.message || "Unable to clear cache."
      );
    } finally {
      setClearingCache(false);
    }
  };

  const handleRunAnalysis = async (event) => {
    event.preventDefault();
    if (!evidenceId || !canCreate) return;
    setRunning(true);
    setRunError(null);
    setClassifyResult(null);
    setSummaryResult(null);
    const payload = { evidence_id: evidenceId, use_fallback: useFallback };
    try {
      const classified = await aiService.classify(payload);
      setClassifyResult(classified);
      if (analysisType === ANALYSIS_TYPE.FULL) {
        const summarised = await aiService.summarize(payload);
        setSummaryResult(summarised?.summary || summarised);
      }
      success(
        "Analysis complete",
        analysisType === ANALYSIS_TYPE.FULL
          ? "Classification and summary are ready."
          : "Classification results are ready."
      );
    } catch (err) {
      setRunError(err);
      notifyError(
        "AI analysis failed",
        err?.response?.data?.detail || err?.message || "Unable to run analysis."
      );
    } finally {
      setRunning(false);
    }
  };

  const handleAsk = async (question) => {
    if (!evidenceId || !canCreate) return;
    const history = messages.map((item) => ({
      role: item.role,
      content: item.content || item.text || "",
    }));
    setMessages((prev) => [
      ...prev,
      { role: "user", content: question, id: `user-${Date.now()}` },
    ]);
    setAskLoading(true);
    try {
      const result = await aiService.ask({
        evidence_id: evidenceId,
        question,
        conversation_history: history.length ? history : undefined,
      });
      const qa = result?.response || result;
      setMessages((prev) => [
        ...prev,
        {
          id: `ai-${Date.now()}`,
          role: "assistant",
          content: qa.answer || qa.text || "",
          confidence: qa.confidence,
          referenced_artefact_ids: qa.referenced_artefact_ids || [],
          hallucination_check: qa.hallucination_check,
        },
      ]);
    } catch (err) {
      notifyError(
        "Q&A failed",
        err?.response?.data?.detail || err?.message || "Unable to answer."
      );
      setMessages((prev) => [
        ...prev,
        {
          id: `ai-err-${Date.now()}`,
          role: "assistant",
          content:
            "The local LLM could not answer this question. Verify the AI engine is available, or consult the structured artefact layer.",
          confidence: 0,
          referenced_artefact_ids: [],
          hallucination_check: { risk_level: "high" },
        },
      ]);
    } finally {
      setAskLoading(false);
    }
  };

  const openArtefact = (artefactId) => {
    const found = artefactById.get(artefactId);
    if (found) {
      setDetailArtefact(found);
      setDetailOpen(true);
    }
  };

  const classifications = classifyResult?.classifications || [];
  const overallConfidence =
    classifyResult?.confidence != null
      ? classifyResult.confidence
      : summaryResult?.confidence_score;

  return (
    <Container fluid className="px-0">
      <PageHeader
        title="AI-Assisted Evidence Analysis"
        subtitle="Local LLaMA-3 classification, summarisation, and investigator Q&A"
        breadcrumbs={[
          { label: "Home", to: Routes.Dashboard.path },
          { label: "AI Analysis" },
        ]}
        actions={
          <div className="d-flex align-items-center">
            {healthLoading ? (
              <Spinner animation="border" size="sm" className="me-2" />
            ) : (
              <HealthDot ok={aiOk} />
            )}
            <span className="small fw-bold">
              {healthLoading
                ? "Checking AI…"
                : aiOk
                  ? "AI engine available"
                  : "AI engine unavailable"}
            </span>
          </div>
        }
      />

      <Alert variant="info" className="mb-4">
        <FontAwesomeIcon icon={faInfoCircle} className="me-2" />
        AI-generated analysis uses base LLaMA-3 and should be verified against
        the structured JSON artefact data. Confidence scores indicate the
        reliability of AI outputs.
      </Alert>

      {/* Section 1 — AI Engine Status */}
      <Card border="light" className="shadow-sm mb-4">
        <Card.Header className="border-bottom border-light d-flex justify-content-between align-items-center">
          <h5 className="mb-0">AI Engine Status</h5>
          <div className="d-flex gap-2">
            <Button
              size="sm"
              variant="outline-primary"
              onClick={() => refreshHealth()}
              disabled={healthLoading}
            >
              {healthLoading ? (
                <Spinner animation="border" size="sm" className="me-1" />
              ) : (
                <FontAwesomeIcon icon={faSyncAlt} className="me-1" />
              )}
              Refresh
            </Button>
            {isAdmin ? (
              <Button
                size="sm"
                variant="outline-danger"
                onClick={handleClearCache}
                disabled={clearingCache}
              >
                {clearingCache ? (
                  <Spinner animation="border" size="sm" className="me-1" />
                ) : (
                  <FontAwesomeIcon icon={faBroom} className="me-1" />
                )}
                Clear Cache
              </Button>
            ) : null}
          </div>
        </Card.Header>
        <Card.Body>
          {healthError ? (
            <ApiErrorDisplay
              error={healthError}
              onRetry={() => refreshHealth()}
              className="mb-3"
            />
          ) : null}
          {healthLoading && !health ? (
            <SkeletonLoader type="card" rows={1} />
          ) : (
            <Row className="g-3">
              <Col xs={12} md={4}>
                <div className="small text-muted text-uppercase fw-bold">
                  Model
                </div>
                <div className="fw-bold">
                  {health?.model_name || health?.model || "—"}
                </div>
                <div className="small text-muted">
                  {health?.model_loaded ? "Loaded" : "Not loaded"}
                </div>
              </Col>
              <Col xs={12} md={4}>
                <div className="small text-muted text-uppercase fw-bold">
                  Availability
                </div>
                <div className="d-flex align-items-center">
                  <HealthDot ok={aiOk} />
                  <span className={aiOk ? "text-success" : "text-danger"}>
                    {aiOk ? "Available" : "Unavailable"}
                  </span>
                </div>
                <div className="small text-muted">
                  Response time:{" "}
                  {health?.response_time_ms != null
                    ? `${Number(health.response_time_ms).toFixed(0)} ms`
                    : "—"}
                </div>
              </Col>
              <Col xs={12} md={4}>
                <div className="small text-muted text-uppercase fw-bold">
                  Cache
                </div>
                {isAdmin && cacheStats ? (
                  <>
                    <div>
                      Hits {cacheStats.total_hits ?? 0} · Misses{" "}
                      {cacheStats.total_misses ?? 0}
                    </div>
                    <div className="small text-muted">
                      Hit rate{" "}
                      {hitRate != null ? formatPercentage(hitRate, 1) : "—"}
                      {cacheStats.current_size != null
                        ? ` · ${cacheStats.current_size}/${cacheStats.max_size || "?"} entries`
                        : ""}
                    </div>
                  </>
                ) : (
                  <div className="small text-muted">
                    {isAdmin
                      ? "Cache statistics unavailable."
                      : "Cache statistics are visible to administrators."}
                  </div>
                )}
              </Col>
              <Col xs={12}>
                <div className="small text-muted">
                  Last checked:{" "}
                  {health?.checked_at
                    ? `${formatDate(health.checked_at)} (${formatDateRelative(
                        health.checked_at
                      )})`
                    : "—"}
                </div>
                {health?.error ? (
                  <Alert variant="warning" className="mt-2 mb-0 py-2">
                    {health.error}
                  </Alert>
                ) : null}
              </Col>
            </Row>
          )}
        </Card.Body>
      </Card>

      {/* Section 2 — Run AI Analysis */}
      <Card border="light" className="shadow-sm mb-4">
        <Card.Header className="border-bottom border-light">
          <h5 className="mb-0">Run AI Analysis</h5>
        </Card.Header>
        <Card.Body>
          <Form onSubmit={handleRunAnalysis}>
            <Row className="g-3">
              <Col xs={12} md={5}>
                <Form.Label>Evidence</Form.Label>
                <Form.Select
                  value={evidenceId}
                  onChange={(event) => setEvidenceId(event.target.value)}
                  aria-label="Evidence selector"
                >
                  <option value="">Select processed evidence…</option>
                  {evidenceOptions.map((item) => {
                    const eid = evidenceOptionId(item);
                    return (
                      <option key={eid} value={eid}>
                        {evidenceOptionLabel(item)}
                      </option>
                    );
                  })}
                </Form.Select>
              </Col>
              <Col xs={12} md={4}>
                <Form.Label>Analysis type</Form.Label>
                <Form.Select
                  value={analysisType}
                  onChange={(event) => setAnalysisType(event.target.value)}
                >
                  <option value={ANALYSIS_TYPE.CLASSIFY}>Classification</option>
                  <option value={ANALYSIS_TYPE.FULL}>
                    Full Analysis (classify + summarize)
                  </option>
                </Form.Select>
              </Col>
              <Col xs={12} md={3} className="d-flex align-items-end">
                <Form.Check
                  type="checkbox"
                  id="use-fallback"
                  label="Use fallback"
                  checked={useFallback}
                  onChange={(event) => setUseFallback(event.target.checked)}
                />
              </Col>
            </Row>
            <div className="mt-3">
              <Button
                type="submit"
                variant="primary"
                disabled={!evidenceId || running || !canCreate}
              >
                {running ? (
                  <Spinner animation="border" size="sm" className="me-2" />
                ) : (
                  <FontAwesomeIcon icon={faPlay} className="me-2" />
                )}
                Run Analysis
              </Button>
              {!canCreate ? (
                <span className="small text-muted ms-2">
                  Analysis create permission is required.
                </span>
              ) : null}
            </div>
          </Form>

          {runError ? (
            <ApiErrorDisplay error={runError} className="mt-3" />
          ) : null}

          {running ? (
            <div className="mt-3">
              <SkeletonLoader type="table" rows={4} />
            </div>
          ) : null}

          {classifyResult || summaryResult ? (
            <div className="mt-4">
              <div className="d-flex flex-wrap align-items-center gap-3 mb-3">
                <h6 className="mb-0">Results</h6>
                {classifyResult?.model_used ? (
                  <Badge bg="light" text="dark">
                    Model: {classifyResult.model_used}
                  </Badge>
                ) : null}
                {overallConfidence != null ? (
                  <div style={{ minWidth: 180 }}>
                    <ConfidenceMeter score={overallConfidence} />
                  </div>
                ) : null}
              </div>

              {summaryResult ? (
                <Card border="light" className="mb-3 bg-light">
                  <Card.Body>
                    <h6>Investigative summary</h6>
                    <p className="mb-2">
                      {summaryResult.executive_summary ||
                        summaryResult.full_text ||
                        "—"}
                    </p>
                    {(summaryResult.key_findings || []).length ? (
                      <>
                        <div className="small text-muted text-uppercase fw-bold">
                          Key findings
                        </div>
                        <ul className="small mb-2">
                          {summaryResult.key_findings.map((finding) => (
                            <li key={finding}>{finding}</li>
                          ))}
                        </ul>
                      </>
                    ) : null}
                    {(summaryResult.iocs_identified || []).length ? (
                      <div className="d-flex flex-wrap gap-1 mb-2">
                        {summaryResult.iocs_identified.map((ioc) => (
                          <Badge key={ioc} bg="danger">
                            {ioc}
                          </Badge>
                        ))}
                      </div>
                    ) : null}
                    {summaryResult.confidence_score != null ? (
                      <ConfidenceMeter
                        score={summaryResult.confidence_score}
                        className="mt-2"
                      />
                    ) : null}
                  </Card.Body>
                </Card>
              ) : null}

              {classifications.length ? (
                <Table responsive hover className="align-middle">
                  <thead className="thead-light">
                    <tr>
                      <th>Artefact</th>
                      <th>Suspicion</th>
                      <th>Confidence</th>
                      <th>Reasoning</th>
                      <th>IOCs</th>
                    </tr>
                  </thead>
                  <tbody>
                    {classifications.map((row) => (
                      <tr key={row.artefact_id}>
                        <td>
                          <Button
                            variant="link"
                            size="sm"
                            className="p-0"
                            onClick={() => openArtefact(row.artefact_id)}
                          >
                            {formatArtefactId(row.artefact_id)}
                          </Button>
                        </td>
                        <td>
                          <StatusBadge
                            status={row.suspicion_level}
                            type="suspicion"
                          />
                        </td>
                        <td style={{ minWidth: 120 }}>
                          <ConfidenceMeter
                            score={row.confidence}
                            showLabel={false}
                          />
                          <span className="small text-muted">
                            {Math.round((Number(row.confidence) || 0) * 100)}%
                          </span>
                        </td>
                        <td className="small">{row.reasoning || "—"}</td>
                        <td>
                          {(row.ioc_indicators || []).length
                            ? row.ioc_indicators.map((ioc) => (
                                <Badge
                                  key={ioc}
                                  bg="light"
                                  text="dark"
                                  className="me-1"
                                >
                                  {ioc}
                                </Badge>
                              ))
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              ) : classifyResult ? (
                <EmptyState
                  title="No classifications returned"
                  description="The AI engine completed but produced no artefact classifications."
                />
              ) : null}
            </div>
          ) : null}
        </Card.Body>
      </Card>

      {/* Section 3 — Investigator Q&A */}
      <Card border="light" className="shadow-sm mb-4">
        <Card.Header className="border-bottom border-light d-flex justify-content-between align-items-center">
          <h5 className="mb-0">Investigator Q&amp;A</h5>
          {evidenceId ? (
            <Button
              as={Link}
              to={Routes.Artefacts.path.replace(":id", evidenceId)}
              size="sm"
              variant="outline-primary"
            >
              Open explorer
            </Button>
          ) : null}
        </Card.Header>
        <Card.Body>
          {!evidenceId ? (
            <EmptyState
              title="Select evidence to start Q&A"
              description="Choose processed evidence above, then ask grounded questions about its artefacts."
            />
          ) : (
            <ChatInterface
              messages={messages}
              onSend={handleAsk}
              loading={askLoading}
              suggestions={suggestions}
              disabled={!canCreate}
              onArtefactClick={openArtefact}
            />
          )}
        </Card.Body>
      </Card>

      <ArtefactDetailModal
        show={detailOpen}
        onHide={() => setDetailOpen(false)}
        artefact={detailArtefact}
        evidenceId={evidenceId}
        onSelectArtefact={(id) => {
          const found = artefactById.get(id);
          if (found) setDetailArtefact(found);
        }}
      />
      <ConfirmDialog {...dialogProps} />
    </Container>
  );
}
