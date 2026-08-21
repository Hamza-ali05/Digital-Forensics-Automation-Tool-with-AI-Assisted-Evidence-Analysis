import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useHistory, useLocation } from "react-router-dom";
import {
  Button,
  Col,
  Container,
  Form,
  Row,
} from "@themesberg/react-bootstrap";

import PageHeader from "components/common/PageHeader";
import ApiErrorDisplay from "components/common/ApiErrorDisplay";
import EmptyState from "components/common/EmptyState";
import SkeletonLoader from "components/common/SkeletonLoader";
import ArtefactDetailModal from "components/forensic/ArtefactDetailModal";
import NarrativeSummary from "components/forensic/NarrativeSummary";
import { formatDate } from "utils/formatters";
import {
  evidenceOptionId,
  evidenceOptionLabel,
  extractArtefacts,
  listCompletedReports,
  loadEvidenceOptions,
} from "utils/artefactLoader";
import reportsService from "services/reports.service";
import { Routes } from "routes";

function shortId(id) {
  return id ? String(id).slice(0, 8) : "—";
}

function downloadText(filename, text) {
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/**
 * Investigative narrative summary viewer with artefact ID linking.
 */
export default function AISummaryViewer() {
  const history = useHistory();
  const location = useLocation();
  const query = useMemo(
    () => new URLSearchParams(location.search || ""),
    [location.search]
  );

  const [reports, setReports] = useState([]);
  const [evidenceOptions, setEvidenceOptions] = useState([]);
  const [evidenceId, setEvidenceId] = useState(query.get("evidence_id") || "");
  const [reportId, setReportId] = useState(query.get("report_id") || "");
  const [narrative, setNarrative] = useState("");
  const [jsonDoc, setJsonDoc] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [detailArtefact, setDetailArtefact] = useState(null);
  const [detailOpen, setDetailOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [reportList, evidence] = await Promise.all([
          listCompletedReports(),
          loadEvidenceOptions(),
        ]);
        if (cancelled) return;
        setReports(reportList);
        setEvidenceOptions(evidence);
      } catch {
        if (!cancelled) {
          setReports([]);
          setEvidenceOptions([]);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const reportsForEvidence = useMemo(() => {
    if (!evidenceId) return reports;
    return reports.filter((item) => String(item.evidenceId) === String(evidenceId));
  }, [reports, evidenceId]);

  const knownReportIds = useMemo(
    () => new Set(reports.map((item) => String(item.reportId))),
    [reports]
  );

  const resolvedReportId = useMemo(() => {
    if (reportId && knownReportIds.has(String(reportId))) return reportId;
    // Drop stale URL/query pointers that no longer exist in the reports API.
    if (reportId && reports.length && !knownReportIds.has(String(reportId))) {
      return reportsForEvidence[0]?.reportId || reports[0]?.reportId || "";
    }
    if (reportId && !reports.length) return reportId;
    if (reportsForEvidence.length) return reportsForEvidence[0].reportId;
    return "";
  }, [reportId, reportsForEvidence, reports, knownReportIds]);

  const loadSummary = useCallback(async (id) => {
    if (!id) {
      setNarrative("");
      setJsonDoc(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [text, json] = await Promise.all([
        reportsService.getNarrative(id),
        reportsService.getJson(id).catch(() => null),
      ]);
      setNarrative(typeof text === "string" ? text : text?.summary_text || "");
      setJsonDoc(json);
    } catch (err) {
      if (err?.response?.status === 404) {
        setError(
          Object.assign(err, {
            message:
              "Report not found. It may have been removed after a database cleanup.",
          })
        );
      } else {
        setError(err);
      }
      setNarrative("");
      setJsonDoc(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const pushQuery = useCallback(
    (nextEvidence, nextReport) => {
      const params = new URLSearchParams();
      if (nextEvidence) params.set("evidence_id", nextEvidence);
      if (nextReport) params.set("report_id", nextReport);
      const qs = params.toString();
      history.replace(
        qs ? `${Routes.AISummary.path}?${qs}` : Routes.AISummary.path
      );
    },
    [history]
  );

  useEffect(() => {
    loadSummary(resolvedReportId).catch(() => {});
  }, [resolvedReportId, loadSummary]);

  // Keep the address bar in sync when a stale report_id was replaced.
  useEffect(() => {
    const urlReport = query.get("report_id") || "";
    if (!urlReport || !resolvedReportId) return;
    if (String(urlReport) === String(resolvedReportId)) return;
    if (!reports.length) return;
    pushQuery(evidenceId, resolvedReportId);
  }, [resolvedReportId, reports.length, query, evidenceId, pushQuery]);

  const artefacts = useMemo(() => extractArtefacts(jsonDoc), [jsonDoc]);
  const artefactById = useMemo(() => {
    const map = new Map();
    artefacts.forEach((item) => {
      if (item?.artefact_id) map.set(item.artefact_id, item);
    });
    return map;
  }, [artefacts]);

  const openArtefact = (id) => {
    const found = artefactById.get(id);
    setDetailArtefact(found || { artefact_id: id, raw_data: {}, metadata: {} });
    setDetailOpen(true);
  };

  return (
    <Container fluid className="px-0">
      <PageHeader
        title="Investigative Summary"
        subtitle="AI-generated narrative for a completed pipeline report"
        actions={
          <Row className="g-2">
            <Col>
              <Form.Select
                value={evidenceId}
                onChange={(event) => {
                  const next = event.target.value;
                  setEvidenceId(next);
                  setReportId("");
                  pushQuery(next, "");
                }}
                aria-label="Evidence selector"
                style={{ minWidth: 220 }}
              >
                <option value="">All evidence…</option>
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
            <Col>
              <Form.Select
                value={resolvedReportId}
                onChange={(event) => {
                  const next = event.target.value;
                  setReportId(next);
                  const match = reports.find((item) => item.reportId === next);
                  if (match?.evidenceId) setEvidenceId(match.evidenceId);
                  pushQuery(match?.evidenceId || evidenceId, next);
                }}
                aria-label="Report selector"
                style={{ minWidth: 220 }}
              >
                <option value="">Select report…</option>
                {reportsForEvidence.map((item) => (
                  <option key={item.reportId} value={item.reportId}>
                    Report {shortId(item.reportId)}
                    {item.completedAt
                      ? ` · ${formatDate(item.completedAt)}`
                      : ""}
                  </option>
                ))}
              </Form.Select>
            </Col>
          </Row>
        }
      />

      {error ? (
        <ApiErrorDisplay
          error={error}
          onRetry={() => loadSummary(resolvedReportId)}
          className="mb-3"
        />
      ) : null}

      {!resolvedReportId ? (
        <EmptyState
          title="No report selected"
          description="Select evidence with a completed pipeline report to view its investigative summary."
        />
      ) : loading ? (
        <SkeletonLoader type="detail" rows={5} />
      ) : (
        <>
          <NarrativeSummary
            narrative={narrative}
            jsonDoc={jsonDoc}
            onArtefactClick={openArtefact}
            showDownload
            reportId={resolvedReportId}
            onDownload={(text, id) =>
              downloadText(`summary-${shortId(id)}.txt`, text)
            }
          />
          {narrative ? (
            <div className="mb-4">
              <Button
                as={Link}
                to={`${Routes.JSONViewer.path}?report_id=${resolvedReportId}`}
                variant="outline-secondary"
              >
                View JSON Report
              </Button>
            </div>
          ) : null}
        </>
      )}

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
    </Container>
  );
}
