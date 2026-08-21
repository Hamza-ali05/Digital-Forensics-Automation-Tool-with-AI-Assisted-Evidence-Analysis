import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Alert,
  Button,
  Card,
  Col,
  Container,
  Form,
  Row,
  Table,
} from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faBolt,
  faClock,
  faHistory,
  faSave,
  faTachometerAlt,
} from "@fortawesome/free-solid-svg-icons";
import {
  Chart as ChartJS,
  BarElement,
  CategoryScale,
  LinearScale,
  LineElement,
  PointElement,
  Legend,
  Tooltip,
} from "chart.js";
import { Bar } from "react-chartjs-2";

import PageHeader from "components/common/PageHeader";
import StatCard from "components/forensic/StatCard";
import ApiErrorDisplay from "components/common/ApiErrorDisplay";
import EmptyState from "components/common/EmptyState";
import SkeletonLoader from "components/common/SkeletonLoader";
import { PIPELINE_STAGE } from "utils/constants";
import { formatDuration, formatPercentage } from "utils/formatters";
import useNotification from "hooks/useNotification";
import evaluationService from "services/evaluation.service";
import pipelineService from "services/pipeline.service";
import { Routes } from "routes";

ChartJS.register(
  BarElement,
  CategoryScale,
  LinearScale,
  LineElement,
  PointElement,
  Legend,
  Tooltip
);

const BASELINE_KEY = "dfat.evaluation.baselineTtt";

const STAGE_KEYS = [
  PIPELINE_STAGE.ACQUISITION,
  PIPELINE_STAGE.PARSING,
  PIPELINE_STAGE.AI_TRIAGE,
  PIPELINE_STAGE.REPORTING,
];

const STAGE_LABELS = {
  [PIPELINE_STAGE.ACQUISITION]: "Acquisition",
  [PIPELINE_STAGE.PARSING]: "Parsing",
  [PIPELINE_STAGE.AI_TRIAGE]: "Triage",
  [PIPELINE_STAGE.REPORTING]: "Reporting",
};

const STAGE_COLOURS = ["#0d6efd", "#198754", "#fd7e14", "#6f42c1"];

const PARSER_SUCCESS = new Set(["completed"]);

function readBaseline() {
  try {
    const raw = localStorage.getItem(BASELINE_KEY);
    const num = Number(raw);
    return Number.isFinite(num) && num > 0 ? num : "";
  } catch {
    return "";
  }
}

function percentile(ordered, p) {
  if (!ordered.length) return 0;
  if (ordered.length === 1) return ordered[0];
  const rank = (p / 100) * (ordered.length - 1);
  const lower = Math.floor(rank);
  const upper = Math.ceil(rank);
  if (lower === upper) return ordered[lower];
  const weight = rank - lower;
  return ordered[lower] * (1 - weight) + ordered[upper] * weight;
}

function computeTimeStats(values) {
  const ordered = values
    .map((n) => Number(n))
    .filter((n) => Number.isFinite(n) && n >= 0)
    .sort((a, b) => a - b);
  if (!ordered.length) return null;
  const n = ordered.length;
  const sum = ordered.reduce((acc, v) => acc + v, 0);
  const mean = sum / n;
  const median =
    n % 2 === 1
      ? ordered[(n - 1) / 2]
      : (ordered[n / 2 - 1] + ordered[n / 2]) / 2;
  return {
    mean,
    median,
    min_val: ordered[0],
    max_val: ordered[n - 1],
    p95: percentile(ordered, 95),
    sample_count: n,
  };
}

function stageDuration(executions, key) {
  const item = executions?.[key] || executions?.[key.replace(/-/g, "_")] || {};
  const value = Number(item.duration_seconds);
  return Number.isFinite(value) ? value : 0;
}

function collectParserRows(jobs) {
  const byName = {};
  (jobs || []).forEach((job) => {
    const parsing =
      job?.stage_executions?.[PIPELINE_STAGE.PARSING] ||
      job?.stage_executions?.parsing;
    const results = parsing?.parser_results || {};
    Object.values(results).forEach((item) => {
      const name = item.parser_name || item.name || "unknown";
      if (!byName[name]) {
        byName[name] = {
          parser_name: name,
          durations: [],
          artefacts: 0,
          success: 0,
          total: 0,
        };
      }
      const row = byName[name];
      row.total += 1;
      const duration = Number(item.duration_seconds) || 0;
      row.durations.push(duration);
      row.artefacts += Number(item.artefacts_found) || 0;
      const status = String(item.status || "").toLowerCase();
      if (PARSER_SUCCESS.has(status) && !item.error) row.success += 1;
    });
  });
  return Object.values(byName)
    .map((row) => {
      const totalDuration = row.durations.reduce((a, b) => a + b, 0);
      const avg =
        row.durations.length > 0 ? totalDuration / row.durations.length : 0;
      return {
        parser_name: row.parser_name,
        avg_duration: avg,
        artefacts_per_second:
          totalDuration > 0 ? row.artefacts / totalDuration : 0,
        success_rate: row.total ? (row.success / row.total) * 100 : 0,
        runs: row.total,
      };
    })
    .sort((a, b) => a.parser_name.localeCompare(b.parser_name));
}

function collectStageStats(jobs) {
  const buckets = {};
  STAGE_KEYS.forEach((key) => {
    buckets[key] = [];
  });
  (jobs || []).forEach((job) => {
    const executions = job.stage_executions || {};
    STAGE_KEYS.forEach((key) => {
      const duration = stageDuration(executions, key);
      if (duration > 0) buckets[key].push(duration);
    });
  });
  const averages = STAGE_KEYS.map((key) => {
    const list = buckets[key];
    if (!list.length) return 0;
    return list.reduce((a, b) => a + b, 0) / list.length;
  });
  const totalAvg = averages.reduce((a, b) => a + b, 0) || 1;
  return STAGE_KEYS.map((key, index) => {
    const list = buckets[key];
    const stats = computeTimeStats(list);
    return {
      stage: STAGE_LABELS[key],
      key,
      average: stats ? stats.mean : 0,
      min: stats ? stats.min_val : 0,
      max: stats ? stats.max_val : 0,
      percent: (averages[index] / totalAvg) * 100,
      samples: list.length,
    };
  });
}

/**
 * Time-to-triage analytics, stage bottlenecks, and parser throughput.
 */
export default function PerformanceDashboard() {
  const { success, error: notifyError } = useNotification();

  const [results, setResults] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [datasetFilter, setDatasetFilter] = useState("");
  const [baselineInput, setBaselineInput] = useState(() => {
    const stored = readBaseline();
    return stored === "" ? "" : String(stored);
  });
  const [baseline, setBaseline] = useState(() => {
    const stored = readBaseline();
    return stored === "" ? null : stored;
  });
  const [apiReport, setApiReport] = useState(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [benchmarks, jobList] = await Promise.all([
        evaluationService.getResults(),
        pipelineService.listJobs().catch(() => []),
      ]);
      setResults(Array.isArray(benchmarks) ? benchmarks : []);
      setJobs(Array.isArray(jobList) ? jobList : []);
    } catch (err) {
      setError(err);
      setResults([]);
      setJobs([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData().catch(() => {});
  }, [loadData]);

  const datasets = useMemo(() => {
    const names = new Set(
      (results || []).map((row) => row.dataset_name).filter(Boolean)
    );
    return Array.from(names).sort();
  }, [results]);

  const filteredResults = useMemo(() => {
    const list = [...(results || [])].sort((a, b) => {
      const ta = new Date(a.evaluated_at || 0).getTime();
      const tb = new Date(b.evaluated_at || 0).getTime();
      return ta - tb;
    });
    if (!datasetFilter) return list;
    return list.filter((row) => row.dataset_name === datasetFilter);
  }, [results, datasetFilter]);

  useEffect(() => {
    if (!datasetFilter) {
      setApiReport(null);
      return;
    }
    let cancelled = false;
    const params = { dataset_name: datasetFilter };
    if (baseline && baseline > 0) params.baseline_ttt = baseline;
    evaluationService
      .getPerformance(params)
      .then((report) => {
        if (!cancelled) setApiReport(report);
      })
      .catch(() => {
        if (!cancelled) setApiReport(null);
      });
    return () => {
      cancelled = true;
    };
  }, [datasetFilter, baseline]);

  const timeStats = useMemo(() => {
    if (apiReport?.time_stats && datasetFilter) {
      return apiReport.time_stats;
    }
    return computeTimeStats(
      filteredResults.map((row) => row.time_to_triage_seconds)
    );
  }, [apiReport, datasetFilter, filteredResults]);

  const speedup = useMemo(() => {
    if (apiReport?.baseline_comparison) return apiReport.baseline_comparison;
    if (!baseline || !timeStats?.mean || timeStats.mean <= 0) return null;
    const factor = baseline / timeStats.mean;
    const percentage = ((baseline - timeStats.mean) / baseline) * 100;
    return {
      tool_ttt: timeStats.mean,
      baseline_ttt: baseline,
      speedup_factor: factor,
      percentage_improvement: percentage,
    };
  }, [apiReport, baseline, timeStats]);

  const tttChart = useMemo(() => {
    const labels = filteredResults.map(
      (row, index) => `Run ${index + 1}`
    );
    const data = filteredResults.map(
      (row) => Number(row.time_to_triage_seconds) || 0
    );
    const datasetsForChart = [
      {
        type: "bar",
        label: "TTT (seconds)",
        data,
        backgroundColor: "#0d6efd",
        borderRadius: 4,
      },
    ];
    if (baseline && baseline > 0 && labels.length) {
      datasetsForChart.push({
        type: "line",
        label: "Manual baseline",
        data: labels.map(() => baseline),
        borderColor: "#dc3545",
        backgroundColor: "#dc3545",
        borderDash: [6, 4],
        pointRadius: 0,
        tension: 0,
      });
    }
    return { labels, datasets: datasetsForChart };
  }, [filteredResults, baseline]);

  const stageJobs = useMemo(
    () =>
      (jobs || []).filter((job) => {
        const executions = job.stage_executions || {};
        return STAGE_KEYS.some((key) => stageDuration(executions, key) > 0);
      }),
    [jobs]
  );

  const stageChart = useMemo(() => {
    const labels = stageJobs.map(
      (job, index) => `Job ${index + 1}`
    );
    return {
      labels,
      datasets: STAGE_KEYS.map((key, i) => ({
        label: STAGE_LABELS[key],
        data: stageJobs.map((job) =>
          stageDuration(job.stage_executions || {}, key)
        ),
        backgroundColor: STAGE_COLOURS[i],
        stack: "stages",
      })),
    };
  }, [stageJobs]);

  const stageRows = useMemo(() => collectStageStats(stageJobs), [stageJobs]);
  const parserRows = useMemo(() => collectParserRows(jobs), [jobs]);

  const saveBaseline = (event) => {
    event.preventDefault();
    const num = Number(baselineInput);
    if (!Number.isFinite(num) || num <= 0) {
      notifyError("Invalid baseline", "Enter a positive number of seconds.");
      return;
    }
    try {
      localStorage.setItem(BASELINE_KEY, String(num));
    } catch {
      notifyError("Save failed", "Could not write baseline to local storage.");
      return;
    }
    setBaseline(num);
    success("Baseline saved", `Manual triage baseline set to ${formatDuration(num)}.`);
  };

  return (
    <Container fluid className="px-0">
      <PageHeader
        title="Performance Analytics"
        subtitle="Time-to-triage, pipeline stage bottlenecks, and parser throughput"
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

      {error ? (
        <ApiErrorDisplay error={error} onRetry={loadData} className="mb-3" />
      ) : null}

      <Card border="light" className="shadow-sm mb-4">
        <Card.Body>
          <Form.Group className="mb-0" style={{ maxWidth: 320 }}>
            <Form.Label className="small text-muted mb-1">Dataset</Form.Label>
            <Form.Select
              value={datasetFilter}
              onChange={(event) => setDatasetFilter(event.target.value)}
              aria-label="Dataset filter"
            >
              <option value="">All datasets</option>
              {datasets.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </Form.Select>
          </Form.Group>
        </Card.Body>
      </Card>

      <h5 className="mb-3">Time-to-Triage Summary</h5>
      {loading ? (
        <SkeletonLoader type="card" rows={1} />
      ) : !timeStats ? (
        <EmptyState
          title="No TTT data"
          description="Run a benchmark evaluation to populate time-to-triage statistics."
        />
      ) : (
        <>
          <Row className="g-3 mb-3">
            <Col xs={12} sm={6} xl>
              <StatCard
                title="Average TTT"
                value={formatDuration(timeStats.mean)}
                icon={faClock}
                colour="primary"
              />
            </Col>
            <Col xs={12} sm={6} xl>
              <StatCard
                title="Median TTT"
                value={formatDuration(timeStats.median)}
                icon={faClock}
                colour="info"
              />
            </Col>
            <Col xs={12} sm={6} xl>
              <StatCard
                title="Best TTT"
                value={formatDuration(timeStats.min_val)}
                icon={faBolt}
                colour="success"
              />
            </Col>
            <Col xs={12} sm={6} xl>
              <StatCard
                title="Worst TTT"
                value={formatDuration(timeStats.max_val)}
                icon={faTachometerAlt}
                colour="warning"
              />
            </Col>
            <Col xs={12} sm={6} xl>
              <StatCard
                title="P95 TTT"
                value={formatDuration(timeStats.p95)}
                icon={faClock}
                colour="secondary"
              />
            </Col>
          </Row>
          {speedup ? (
            <Alert
              variant={speedup.percentage_improvement >= 0 ? "success" : "warning"}
              className="mb-4"
            >
              <div className="fw-bold">
                {Math.abs(speedup.percentage_improvement).toFixed(1)}%{" "}
                {speedup.percentage_improvement >= 0 ? "faster" : "slower"} than
                manual baseline
              </div>
              <div className="small mb-0">
                Speedup factor {Number(speedup.speedup_factor).toFixed(2)}× · tool{" "}
                {formatDuration(speedup.tool_ttt)} vs baseline{" "}
                {formatDuration(speedup.baseline_ttt)}
              </div>
            </Alert>
          ) : (
            <p className="small text-muted mb-4">
              Save a manual baseline below to compute speedup against these runs (
              {timeStats.sample_count} sample
              {timeStats.sample_count === 1 ? "" : "s"}).
            </p>
          )}
        </>
      )}

      <Card border="light" className="shadow-sm mb-4">
        <Card.Header className="border-bottom border-light">
          <h5 className="mb-0">TTT Distribution</h5>
        </Card.Header>
        <Card.Body>
          {loading ? (
            <SkeletonLoader type="card" rows={2} />
          ) : filteredResults.length ? (
            <div style={{ minHeight: 260 }}>
              <Bar
                data={tttChart}
                options={{
                  responsive: true,
                  maintainAspectRatio: true,
                  plugins: { legend: { display: true, position: "bottom" } },
                  scales: {
                    x: { title: { display: true, text: "Run number" } },
                    y: {
                      beginAtZero: true,
                      title: { display: true, text: "Seconds" },
                    },
                  },
                }}
              />
            </div>
          ) : (
            <EmptyState
              title="No benchmark runs"
              description="TTT bars appear after at least one benchmark comparison."
            />
          )}
        </Card.Body>
      </Card>

      <Card border="light" className="shadow-sm mb-4">
        <Card.Header className="border-bottom border-light">
          <h5 className="mb-0">Stage Timing Breakdown</h5>
        </Card.Header>
        <Card.Body>
          {loading ? (
            <SkeletonLoader type="card" rows={2} />
          ) : stageJobs.length ? (
            <div style={{ minHeight: 280 }}>
              <Bar
                data={stageChart}
                options={{
                  responsive: true,
                  maintainAspectRatio: true,
                  plugins: { legend: { display: true, position: "bottom" } },
                  scales: {
                    x: { stacked: true, title: { display: true, text: "Pipeline job" } },
                    y: {
                      stacked: true,
                      beginAtZero: true,
                      title: { display: true, text: "Seconds" },
                    },
                  },
                }}
              />
            </div>
          ) : (
            <EmptyState
              title="No stage timings"
              description="Completed pipeline jobs with stage durations will appear here."
            />
          )}
        </Card.Body>
      </Card>

      <Card border="light" className="shadow-sm mb-4">
        <Card.Header className="border-bottom border-light">
          <h5 className="mb-0">Per-Stage Details</h5>
        </Card.Header>
        <Card.Body className="pt-0">
          <Table responsive hover className="align-middle">
            <thead className="thead-light">
              <tr>
                <th>Stage</th>
                <th>Average Duration</th>
                <th>Min</th>
                <th>Max</th>
                <th>% of Total Pipeline Time</th>
              </tr>
            </thead>
            <tbody>
              {stageRows.every((row) => row.samples === 0) ? (
                <tr>
                  <td colSpan={5} className="text-muted">
                    No stage duration samples yet.
                  </td>
                </tr>
              ) : (
                stageRows.map((row) => (
                  <tr key={row.key}>
                    <td>{row.stage}</td>
                    <td>{row.samples ? formatDuration(row.average) : "—"}</td>
                    <td>{row.samples ? formatDuration(row.min) : "—"}</td>
                    <td>{row.samples ? formatDuration(row.max) : "—"}</td>
                    <td>{row.samples ? formatPercentage(row.percent) : "—"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </Table>
        </Card.Body>
      </Card>

      <Card border="light" className="shadow-sm mb-4">
        <Card.Header className="border-bottom border-light">
          <h5 className="mb-0">Parser Performance</h5>
        </Card.Header>
        <Card.Body className="pt-0">
          <Table responsive hover className="align-middle">
            <thead className="thead-light">
              <tr>
                <th>Parser Name</th>
                <th>Average Duration</th>
                <th>Artefacts per Second</th>
                <th>Success Rate</th>
              </tr>
            </thead>
            <tbody>
              {!parserRows.length ? (
                <tr>
                  <td colSpan={4} className="text-muted">
                    Parser timings appear after parsing-stage jobs complete.
                  </td>
                </tr>
              ) : (
                parserRows.map((row) => (
                  <tr key={row.parser_name}>
                    <td>{row.parser_name}</td>
                    <td>{formatDuration(row.avg_duration)}</td>
                    <td>
                      {Number.isFinite(row.artefacts_per_second)
                        ? row.artefacts_per_second.toFixed(2)
                        : "—"}
                    </td>
                    <td>{formatPercentage(row.success_rate)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </Table>
        </Card.Body>
      </Card>

      <Card border="light" className="shadow-sm mb-4">
        <Card.Header className="border-bottom border-light">
          <h5 className="mb-0">Baseline Configuration</h5>
        </Card.Header>
        <Card.Body>
          <p className="small text-muted">
            Enter the average time for manual triage of the same dataset to compute
            speedup factor.
          </p>
          <Form onSubmit={saveBaseline}>
            <Row className="g-3 align-items-end">
              <Col xs={12} md={6} lg={4}>
                <Form.Group className="mb-0">
                  <Form.Label>Manual baseline TTT (seconds)</Form.Label>
                  <Form.Control
                    type="number"
                    min="0.1"
                    step="0.1"
                    value={baselineInput}
                    onChange={(event) => setBaselineInput(event.target.value)}
                    placeholder="e.g. 1800"
                    aria-label="Manual baseline TTT in seconds"
                  />
                </Form.Group>
              </Col>
              <Col xs="auto">
                <Button type="submit" variant="primary">
                  <FontAwesomeIcon icon={faSave} className="me-2" />
                  Save Baseline
                </Button>
              </Col>
            </Row>
          </Form>
        </Card.Body>
      </Card>
    </Container>
  );
}
