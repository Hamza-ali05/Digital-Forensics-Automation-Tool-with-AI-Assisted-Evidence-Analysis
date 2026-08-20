import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useHistory } from "react-router-dom";
import {
  Badge,
  Button,
  Card,
  Col,
  Container,
  Form,
  Row,
} from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faDatabase,
  faEye,
  faHdd,
  faSearch,
  faSync,
} from "@fortawesome/free-solid-svg-icons";
import {
  Chart as ChartJS,
  ArcElement,
  BarElement,
  CategoryScale,
  Legend,
  LinearScale,
  Tooltip,
} from "chart.js";
import { Bar, Doughnut } from "react-chartjs-2";

import PageHeader from "components/common/PageHeader";
import DataTable from "components/common/DataTable";
import ApiErrorDisplay from "components/common/ApiErrorDisplay";
import EmptyState from "components/common/EmptyState";
import SkeletonLoader from "components/common/SkeletonLoader";
import StatusBadge from "components/common/StatusBadge";
import StatCard from "components/forensic/StatCard";
import {
  DATASET_CATEGORY,
  DATASET_FORMAT,
  DATASET_STATUS,
} from "utils/constants";
import { formatBytes } from "utils/formatters";
import useAuth from "hooks/useAuth";
import useNotification from "hooks/useNotification";
import datasetsService from "services/datasets.service";
import { Routes } from "routes";

ChartJS.register(
  ArcElement,
  BarElement,
  CategoryScale,
  LinearScale,
  Legend,
  Tooltip
);

const CATEGORY_OPTIONS = [
  { value: "", label: "All categories" },
  ...Object.values(DATASET_CATEGORY).map((value) => ({
    value,
    label: value.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
  })),
];

const FORMAT_OPTIONS = [
  { value: "", label: "All formats" },
  ...Object.values(DATASET_FORMAT).map((value) => ({
    value,
    label: value.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
  })),
];

const STATUS_OPTIONS = [
  { value: "", label: "All statuses" },
  ...Object.values(DATASET_STATUS).map((value) => ({
    value,
    label: value.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
  })),
];

function chartFromCounts(counts = {}) {
  const labels = Object.keys(counts).map((key) =>
    key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
  );
  const values = Object.values(counts);
  return {
    labels,
    datasets: [
      {
        data: values,
        backgroundColor: [
          "#0d6efd",
          "#198754",
          "#ffc107",
          "#dc3545",
          "#6f42c1",
          "#fd7e14",
          "#20c997",
          "#6c757d",
        ],
      },
    ],
  };
}

/**
 * Dataset intelligence overview with statistics charts and registry table.
 */
export default function DatasetDashboard() {
  const history = useHistory();
  const { role } = useAuth();
  const { success, error: notifyError } = useNotification();
  const isAdmin = role === "admin";

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [stats, setStats] = useState(null);
  const [datasets, setDatasets] = useState([]);
  const [categoryFilter, setCategoryFilter] = useState("");
  const [formatFilter, setFormatFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [scanning, setScanning] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {};
      if (categoryFilter) params.category = categoryFilter;
      if (statusFilter) params.status = statusFilter;
      const [statsResult, listResult] = await Promise.all([
        datasetsService.getStatistics(),
        datasetsService.list(params),
      ]);
      setStats(statsResult);
      let rows = Array.isArray(listResult) ? listResult : [];
      if (formatFilter) {
        rows = rows.filter(
          (row) => String(row.format || "").toLowerCase() === formatFilter
        );
      }
      setDatasets(rows);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [categoryFilter, formatFilter, statusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const handleScan = async () => {
    setScanning(true);
    try {
      const result = await datasetsService.scan();
      success(
        "Scan complete",
        `Found ${result.datasets_found ?? 0} datasets (${result.new_count ?? 0} new).`
      );
      await load();
    } catch (err) {
      notifyError("Scan failed", err?.message || "Unable to scan datasets.");
    } finally {
      setScanning(false);
    }
  };

  const columns = useMemo(
    () => [
      {
        key: "name",
        header: "Name",
        render: (row) => (
          <Link to={Routes.DatasetDetail.path.replace(":id", row.dataset_id)}>
            {row.name}
          </Link>
        ),
      },
      {
        key: "category",
        header: "Category",
        render: (row) => (
          <Badge bg="light" text="dark">
            {String(row.category || "—").replace(/_/g, " ")}
          </Badge>
        ),
      },
      {
        key: "format",
        header: "Format",
        render: (row) => String(row.format || "—").replace(/_/g, " "),
      },
      {
        key: "status",
        header: "Status",
        render: (row) => (
          <StatusBadge status={row.status} type="dataset" />
        ),
      },
      {
        key: "file_size_bytes",
        header: "Size",
        render: (row) => formatBytes(row.file_size_bytes),
      },
      {
        key: "indexing_status",
        header: "Indexed",
        render: (row) => (
          <StatusBadge status={row.indexing_status} type="indexing" />
        ),
      },
      {
        key: "actions",
        header: "",
        render: (row) => (
          <Button
            size="sm"
            variant="outline-primary"
            onClick={() =>
              history.push(
                Routes.DatasetDetail.path.replace(":id", row.dataset_id)
              )
            }
          >
            <FontAwesomeIcon icon={faEye} className="me-1" />
            View
          </Button>
        ),
      },
    ],
    [history]
  );

  const categoryChart = useMemo(
    () => chartFromCounts(stats?.category_counts || {}),
    [stats]
  );
  const formatChart = useMemo(
    () => chartFromCounts(stats?.format_counts || {}),
    [stats]
  );
  const statusChart = useMemo(
    () => chartFromCounts(stats?.status_counts || {}),
    [stats]
  );

  if (loading && !stats) {
    return (
      <Container fluid className="px-0">
        <SkeletonLoader type="dashboard" />
      </Container>
    );
  }

  return (
    <Container fluid className="px-0">
      <PageHeader
        title="Datasets"
        subtitle="Dataset intelligence registry, discovery, and indexing"
        breadcrumbs={[
          { label: "Home", to: Routes.Dashboard.path },
          { label: "Datasets" },
        ]}
        actions={
          isAdmin ? (
            <Button variant="primary" onClick={handleScan} disabled={scanning}>
              <FontAwesomeIcon icon={faSearch} className="me-2" />
              {scanning ? "Scanning…" : "Scan for Datasets"}
            </Button>
          ) : null
        }
      />

      {error ? (
        <ApiErrorDisplay error={error} onRetry={load} className="mb-3" />
      ) : null}

      <Row className="g-3 mb-3">
        <Col xs={12} md={6} lg={3}>
          <StatCard
            title="Total Datasets"
            value={stats?.total_count ?? datasets.length}
            icon={faDatabase}
            colour="primary"
          />
        </Col>
        <Col xs={12} md={6} lg={3}>
          <StatCard
            title="Indexed Size"
            value={formatBytes(stats?.total_size_bytes || 0)}
            icon={faHdd}
            colour="success"
          />
        </Col>
        <Col xs={12} md={6} lg={3}>
          <StatCard
            title="Categories"
            value={Object.keys(stats?.category_counts || {}).length}
            icon={faDatabase}
            colour="info"
          />
        </Col>
        <Col xs={12} md={6} lg={3}>
          <StatCard
            title="Ready"
            value={stats?.status_counts?.ready ?? 0}
            icon={faSync}
            colour="warning"
          />
        </Col>
      </Row>

      <Row className="g-3 mb-3">
        <Col xs={12} lg={4}>
          <Card border="light" className="shadow-sm h-100">
            <Card.Header>By Category</Card.Header>
            <Card.Body>
              {categoryChart.labels.length ? (
                <Doughnut data={categoryChart} />
              ) : (
                <EmptyState message="No category data yet." />
              )}
            </Card.Body>
          </Card>
        </Col>
        <Col xs={12} lg={4}>
          <Card border="light" className="shadow-sm h-100">
            <Card.Header>By Format</Card.Header>
            <Card.Body>
              {formatChart.labels.length ? (
                <Bar data={formatChart} options={{ indexAxis: "y", plugins: { legend: { display: false } } }} />
              ) : (
                <EmptyState message="No format data yet." />
              )}
            </Card.Body>
          </Card>
        </Col>
        <Col xs={12} lg={4}>
          <Card border="light" className="shadow-sm h-100">
            <Card.Header>By Status</Card.Header>
            <Card.Body>
              {statusChart.labels.length ? (
                <Doughnut data={statusChart} />
              ) : (
                <EmptyState message="No status data yet." />
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      <Card border="light" className="shadow-sm mb-3">
        <Card.Body>
          <Row className="g-2 align-items-end">
            <Col xs={12} md={4}>
              <Form.Label className="small text-muted">Category</Form.Label>
              <Form.Select
                value={categoryFilter}
                onChange={(e) => setCategoryFilter(e.target.value)}
              >
                {CATEGORY_OPTIONS.map((opt) => (
                  <option key={opt.value || "all"} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </Form.Select>
            </Col>
            <Col xs={12} md={4}>
              <Form.Label className="small text-muted">Format</Form.Label>
              <Form.Select
                value={formatFilter}
                onChange={(e) => setFormatFilter(e.target.value)}
              >
                {FORMAT_OPTIONS.map((opt) => (
                  <option key={opt.value || "all"} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </Form.Select>
            </Col>
            <Col xs={12} md={4}>
              <Form.Label className="small text-muted">Status</Form.Label>
              <Form.Select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
              >
                {STATUS_OPTIONS.map((opt) => (
                  <option key={opt.value || "all"} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </Form.Select>
            </Col>
          </Row>
        </Card.Body>
      </Card>

      <Card border="light" className="shadow-sm">
        <Card.Header className="d-flex justify-content-between align-items-center">
          <span>Registered Datasets</span>
          <Button size="sm" variant="outline-secondary" onClick={load}>
            <FontAwesomeIcon icon={faSync} className="me-1" />
            Refresh
          </Button>
        </Card.Header>
        <Card.Body className="p-0">
          <DataTable
            columns={columns}
            data={datasets}
            keyField="dataset_id"
            emptyMessage="No datasets registered. Run a scan to discover datasets."
          />
        </Card.Body>
      </Card>
    </Container>
  );
}
