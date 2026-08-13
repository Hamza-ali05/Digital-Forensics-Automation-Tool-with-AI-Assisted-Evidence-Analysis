import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useHistory, useLocation } from "react-router-dom";
import {
  Badge,
  Button,
  Card,
  Col,
  Collapse,
  Container,
  Row,
  Table,
} from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faCaretDown,
  faCaretRight,
  faEye,
  faPlay,
} from "@fortawesome/free-solid-svg-icons";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Legend,
  Tooltip,
} from "chart.js";
import { Line } from "react-chartjs-2";

import PageHeader from "components/common/PageHeader";
import DataTable from "components/common/DataTable";
import ApiErrorDisplay from "components/common/ApiErrorDisplay";
import EmptyState from "components/common/EmptyState";
import SkeletonLoader from "components/common/SkeletonLoader";
import MetricGauge, { scoreToPercent } from "components/forensic/MetricGauge";
import { formatDate, formatDuration, formatPercentage } from "utils/formatters";
import evaluationService from "services/evaluation.service";
import { Routes } from "routes";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Legend,
  Tooltip
);

function shortId(id) {
  return id ? String(id).slice(0, 8) : "—";
}

function humanise(value) {
  return String(value || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function resultId(row) {
  return row?.benchmark_id || row?.id || "";
}

function sortByDate(results) {
  return [...(results || [])].sort((a, b) => {
    const ta = new Date(a.evaluated_at || 0).getTime();
    const tb = new Date(b.evaluated_at || 0).getTime();
    return ta - tb;
  });
}

function asIdentifierList(value) {
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (item == null) return "";
        if (typeof item === "string") return item;
        return (
          item.identifier ||
          item.artefact_id ||
          item.id ||
          item.path ||
          JSON.stringify(item)
        );
      })
      .filter(Boolean);
  }
  if (typeof value === "string" && value.trim()) return [value.trim()];
  return [];
}

function extractIdentifierLists(result) {
  if (!result) return { fp: [], fn: [] };
  return {
    fp: asIdentifierList(
      result.false_positive_ids ||
        result.false_positives_list ||
        result.false_positive_artefacts ||
        (Array.isArray(result.false_positives)
          ? result.false_positives
          : null)
    ),
    fn: asIdentifierList(
      result.false_negative_ids ||
        result.false_negatives_list ||
        result.false_negative_artefacts ||
        (Array.isArray(result.false_negatives)
          ? result.false_negatives
          : null)
    ),
  };
}

function extractPerCategory(result) {
  const raw =
    result?.per_category ||
    result?.category_breakdown ||
    result?.metrics_by_category ||
    null;
  if (!raw || typeof raw !== "object") return [];
  return Object.entries(raw).map(([category, metrics]) => {
    const row = metrics && typeof metrics === "object" ? metrics : {};
    return {
      category,
      precision: row.precision,
      recall: row.recall,
      f1: row.f1_score != null ? row.f1_score : row.f1,
    };
  });
}

function ExpandableList({ title, count, items, emptyHint }) {
  const [open, setOpen] = useState(false);
  return (
    <Card border="light" className="shadow-sm mb-3">
      <Card.Header
        className="d-flex justify-content-between align-items-center"
        style={{ cursor: "pointer" }}
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
      >
        <h6 className="mb-0">
          {title}{" "}
          <Badge bg="light" text="dark" className="border ms-1">
            {count}
          </Badge>
        </h6>
        <FontAwesomeIcon icon={open ? faCaretDown : faCaretRight} />
      </Card.Header>
      <Collapse in={open}>
        <div>
          <Card.Body>
            {items.length ? (
              <ul className="small mb-0">
                {items.map((item) => (
                  <li key={item}>
                    <code>{item}</code>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="small text-muted mb-0">{emptyHint}</p>
            )}
          </Card.Body>
        </div>
      </Collapse>
    </Card>
  );
}

/**
 * Historical benchmark runs with trend chart and per-run detail.
 */
export default function BenchmarkResults() {
  const history = useHistory();
  const location = useLocation();
  const query = useMemo(
    () => new URLSearchParams(location.search || ""),
    [location.search]
  );
  const selectedId = query.get("id") || "";

  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [page, setPage] = useState(1);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const pageSize = 20;

  const loadResults = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await evaluationService.getResults();
      setResults(sortByDate(list).reverse());
    } catch (err) {
      setError(err);
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadResults().catch(() => {});
  }, [loadResults]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    const fromList = results.find((row) => resultId(row) === selectedId);
    if (fromList) setDetail(fromList);

    let cancelled = false;
    setDetailLoading(true);
    evaluationService
      .getResult(selectedId)
      .then((row) => {
        if (!cancelled) setDetail(row);
      })
      .catch(() => {
        if (!cancelled && fromList) setDetail(fromList);
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId, results]);

  const pagedRows = useMemo(() => {
    const start = (Math.max(1, page) - 1) * pageSize;
    return results.slice(start, start + pageSize).map((row) => ({
      ...row,
      id: resultId(row),
    }));
  }, [results, page]);

  const chartData = useMemo(() => {
    const chronological = sortByDate(results);
    return {
      labels: chronological.map((row) =>
        formatDate(row.evaluated_at) || shortId(resultId(row))
      ),
      datasets: [
        {
          label: "Precision",
          data: chronological.map((row) => scoreToPercent(row.precision)),
          borderColor: "#0d6efd",
          backgroundColor: "#0d6efd",
          tension: 0.2,
        },
        {
          label: "Recall",
          data: chronological.map((row) => scoreToPercent(row.recall)),
          borderColor: "#198754",
          backgroundColor: "#198754",
          tension: 0.2,
        },
        {
          label: "F1",
          data: chronological.map((row) => scoreToPercent(row.f1_score)),
          borderColor: "#fd7e14",
          backgroundColor: "#fd7e14",
          tension: 0.2,
        },
      ],
    };
  }, [results]);

  const categoryRows = useMemo(() => extractPerCategory(detail), [detail]);
  const identifierLists = useMemo(
    () => extractIdentifierLists(detail),
    [detail]
  );

  const selectResult = (id) => {
    const params = new URLSearchParams();
    if (id) params.set("id", id);
    const qs = params.toString();
    history.replace(
      qs
        ? `${Routes.EvaluationBenchmarkHistory.path}?${qs}`
        : Routes.EvaluationBenchmarkHistory.path
    );
  };

  const columns = useMemo(
    () => [
      {
        key: "dataset_name",
        header: "Dataset",
        sortable: true,
        render: (row) => row.dataset_name || "—",
      },
      {
        key: "precision",
        header: "Precision",
        sortable: true,
        render: (row) => {
          const pct = scoreToPercent(row.precision);
          return (
            <span className={pct > 80 ? "text-success fw-bold" : ""}>
              {formatPercentage(pct)}
            </span>
          );
        },
      },
      {
        key: "recall",
        header: "Recall",
        sortable: true,
        render: (row) => formatPercentage(scoreToPercent(row.recall)),
      },
      {
        key: "f1",
        header: "F1",
        sortable: true,
        render: (row) => formatPercentage(scoreToPercent(row.f1_score)),
      },
      {
        key: "ttt",
        header: "TTT",
        render: (row) => formatDuration(row.time_to_triage_seconds),
      },
      {
        key: "evaluated_at",
        header: "Date",
        sortable: true,
        render: (row) => formatDate(row.evaluated_at),
      },
    ],
    []
  );

  const renderActions = (row) => (
    <Button
      variant="outline-primary"
      size="sm"
      onClick={() => selectResult(resultId(row))}
    >
      <FontAwesomeIcon icon={faEye} className="me-1" />
      View Detail
    </Button>
  );

  return (
    <Container fluid className="px-0">
      <PageHeader
        title="Benchmark History"
        subtitle="Precision, recall, and F1 trends across DFRWS / CFReDS runs"
        breadcrumbs={[
          { label: "Home", to: Routes.Dashboard.path },
          { label: "Evaluation", to: Routes.Evaluation.path },
          { label: "History" },
        ]}
        actions={
          <Button as={Link} to={Routes.EvaluationBenchmark.path} variant="primary">
            <FontAwesomeIcon icon={faPlay} className="me-2" />
            Run Benchmark
          </Button>
        }
      />

      {error ? (
        <ApiErrorDisplay error={error} onRetry={loadResults} className="mb-3" />
      ) : null}

      <Card border="light" className="shadow-sm mb-4">
        <Card.Header className="border-bottom border-light">
          <h5 className="mb-0">P / R / F1 over time</h5>
        </Card.Header>
        <Card.Body>
          {loading ? (
            <SkeletonLoader type="card" rows={2} />
          ) : results.length ? (
            <div style={{ minHeight: 260 }}>
              <Line
                data={chartData}
                options={{
                  responsive: true,
                  maintainAspectRatio: true,
                  plugins: { legend: { display: true, position: "bottom" } },
                  scales: {
                    y: {
                      beginAtZero: true,
                      max: 100,
                      ticks: { callback: (value) => `${value}%` },
                    },
                  },
                }}
              />
            </div>
          ) : (
            <EmptyState
              title="No trend data"
              description="Run a benchmark to plot precision, recall, and F1 over time."
            />
          )}
        </Card.Body>
      </Card>

      <Card border="light" className="shadow-sm mb-4">
        <Card.Header className="border-bottom border-light">
          <h5 className="mb-0">All runs</h5>
        </Card.Header>
        <Card.Body className="pt-0">
          <DataTable
            columns={columns}
            data={pagedRows}
            loading={loading}
            emptyMessage="No benchmark runs yet"
            sortable
            actions={renderActions}
            pagination={{ page, pageSize, total: results.length }}
            onPageChange={setPage}
          />
        </Card.Body>
      </Card>

      {selectedId ? (
        <Card border="light" className="shadow-sm mb-4">
          <Card.Header className="border-bottom border-light d-flex justify-content-between align-items-center">
            <h5 className="mb-0">
              Run detail {detail ? `· ${detail.dataset_name || ""}` : ""}
            </h5>
            <Button
              variant="outline-secondary"
              size="sm"
              onClick={() => selectResult("")}
            >
              Close
            </Button>
          </Card.Header>
          <Card.Body>
            {detailLoading && !detail ? (
              <SkeletonLoader type="detail" rows={4} />
            ) : !detail ? (
              <EmptyState
                title="Result unavailable"
                description="This benchmark run could not be loaded."
              />
            ) : (
              <>
                <Row className="g-3 mb-4">
                  <Col xs={6} md={3}>
                    <MetricGauge
                      value={scoreToPercent(detail.precision)}
                      label="Precision"
                      size={100}
                      thresholds={{ warning: 50, success: 80 }}
                    />
                  </Col>
                  <Col xs={6} md={3}>
                    <MetricGauge
                      value={scoreToPercent(detail.recall)}
                      label="Recall"
                      size={100}
                    />
                  </Col>
                  <Col xs={6} md={3}>
                    <MetricGauge
                      value={scoreToPercent(detail.f1_score)}
                      label="F1"
                      size={100}
                    />
                  </Col>
                  <Col xs={6} md={3}>
                    <MetricGauge
                      value={Math.min(
                        100,
                        ((Number(detail.time_to_triage_seconds) || 0) / 300) *
                          100
                      )}
                      label="TTT"
                      size={100}
                      invert
                      display={formatDuration(detail.time_to_triage_seconds)}
                    />
                  </Col>
                </Row>

                <h6 className="mb-3">Per-category breakdown</h6>
                {categoryRows.length ? (
                  <Table responsive hover size="sm" className="mb-4">
                    <thead className="thead-light">
                      <tr>
                        <th>Category</th>
                        <th>Precision</th>
                        <th>Recall</th>
                        <th>F1</th>
                      </tr>
                    </thead>
                    <tbody>
                      {categoryRows.map((row) => (
                        <tr key={row.category}>
                          <td>{humanise(row.category)}</td>
                          <td>{formatPercentage(scoreToPercent(row.precision))}</td>
                          <td>{formatPercentage(scoreToPercent(row.recall))}</td>
                          <td>{formatPercentage(scoreToPercent(row.f1))}</td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                ) : (
                  <p className="small text-muted mb-4">
                    Per-category metrics are not included on this stored run.
                    Overall: expected {detail.artefacts_expected ?? 0}, recovered{" "}
                    {detail.artefacts_recovered ?? 0}.
                  </p>
                )}

                <h6 className="mb-3">False positives / false negatives</h6>
                <ExpandableList
                  title="False positives"
                  count={
                    identifierLists.fp.length || detail.false_positives || 0
                  }
                  items={identifierLists.fp}
                  emptyHint={
                    Number(detail.false_positives)
                      ? `${detail.false_positives} false positives recorded (artefact identifiers are not persisted on historical runs).`
                      : "No false positives recorded for this run."
                  }
                />
                <ExpandableList
                  title="False negatives"
                  count={
                    identifierLists.fn.length || detail.false_negatives || 0
                  }
                  items={identifierLists.fn}
                  emptyHint={
                    Number(detail.false_negatives)
                      ? `${detail.false_negatives} false negatives recorded (artefact identifiers are not persisted on historical runs).`
                      : "No false negatives recorded for this run."
                  }
                />
              </>
            )}
          </Card.Body>
        </Card>
      ) : null}
    </Container>
  );
}
