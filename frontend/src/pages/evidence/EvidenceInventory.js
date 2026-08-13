import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useHistory, useLocation } from "react-router-dom";
import {
  Badge,
  Button,
  Card,
  Col,
  Container,
  Form,
  OverlayTrigger,
  Row,
  Tooltip,
} from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faCheckCircle,
  faCopy,
  faDatabase,
  faEye,
  faHdd,
  faMemory,
  faPlus,
  faShieldAlt,
} from "@fortawesome/free-solid-svg-icons";
import { CopyToClipboard } from "react-copy-to-clipboard";
import {
  Chart as ChartJS,
  ArcElement,
  Legend,
  Tooltip as ChartTooltip,
} from "chart.js";
import { Doughnut } from "react-chartjs-2";

import PageHeader from "components/common/PageHeader";
import DataTable from "components/common/DataTable";
import SearchInput from "components/common/SearchInput";
import StatusBadge from "components/common/StatusBadge";
import ApiErrorDisplay from "components/common/ApiErrorDisplay";
import StatCard from "components/forensic/StatCard";
import {
  EVIDENCE_STATUS,
  EVIDENCE_STATUS_COLOURS,
  EVIDENCE_TYPE,
} from "utils/constants";
import {
  formatBytes,
  formatDateRelative,
  formatHash,
} from "utils/formatters";
import usePagination from "hooks/usePagination";
import usePermission from "hooks/usePermission";
import useNotification from "hooks/useNotification";
import evidenceService from "services/evidence.service";
import casesService from "services/cases.service";
import { Routes } from "routes";

ChartJS.register(ArcElement, Legend, ChartTooltip);

const STATUS_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: EVIDENCE_STATUS.REGISTERED, label: "Registered" },
  { value: EVIDENCE_STATUS.VALIDATING, label: "Validating" },
  { value: EVIDENCE_STATUS.VALIDATED, label: "Validated" },
  { value: EVIDENCE_STATUS.PROCESSING, label: "Processing" },
  { value: EVIDENCE_STATUS.PROCESSED, label: "Processed" },
  { value: EVIDENCE_STATUS.QUARANTINED, label: "Quarantined" },
  { value: EVIDENCE_STATUS.ARCHIVED, label: "Archived" },
];

function sha256Of(row) {
  const set = row.hash_set || {};
  return set.sha256 || set.SHA256 || row.original_hash || "";
}

function typeLabel(type) {
  if (type === EVIDENCE_TYPE.DISK_IMAGE) return "Disk Image";
  if (type === EVIDENCE_TYPE.MEMORY_DUMP) return "Memory Dump";
  return String(type || "—")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function shortId(id) {
  if (!id) return "—";
  return String(id).slice(0, 8);
}

function HashCell({ hash }) {
  const { info } = useNotification();
  if (!hash) return "—";
  return (
    <span className="d-inline-flex align-items-center">
      <code className="small me-1">{formatHash(hash, 12)}</code>
      <CopyToClipboard
        text={hash}
        onCopy={() => info("Copied", "SHA-256 hash copied to clipboard.")}
      >
        <Button
          variant="link"
          size="sm"
          className="p-0 text-muted"
          title="Copy SHA-256"
          aria-label="Copy SHA-256 hash"
        >
          <FontAwesomeIcon icon={faCopy} />
        </Button>
      </CopyToClipboard>
    </span>
  );
}

/**
 * Evidence inventory with filters, statistics, and integrity actions.
 */
export default function EvidenceInventory() {
  const history = useHistory();
  const location = useLocation();
  const { canCreate, canUpdate } = usePermission("evidence");
  const { success, error: notifyError } = useNotification();

  const queryCaseId = useMemo(() => {
    const params = new URLSearchParams(location.search);
    return params.get("caseId") || "";
  }, [location.search]);

  const [cases, setCases] = useState([]);
  const [stats, setStats] = useState(null);
  const [caseFilter, setCaseFilter] = useState(queryCaseId);
  const [statusFilter, setStatusFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [search, setSearch] = useState("");
  const [actionBusy, setActionBusy] = useState(null);

  const filtersRef = useRef({
    caseFilter,
    statusFilter,
    typeFilter,
    search,
  });
  filtersRef.current = { caseFilter, statusFilter, typeFilter, search };

  useEffect(() => {
    casesService
      .list()
      .then((result) => {
        const items = Array.isArray(result?.cases) ? result.cases : [];
        setCases(items);
      })
      .catch(() => setCases([]));
  }, []);

  useEffect(() => {
    evidenceService
      .getStatistics()
      .then(setStats)
      .catch(() => setStats(null));
  }, []);

  const fetchInventory = useCallback(async ({ page, pageSize }) => {
    const {
      caseFilter: caseId,
      statusFilter: status,
      typeFilter: type,
      search: query,
    } = filtersRef.current;

    const params = {};
    if (caseId) params.case_id = caseId;

    const result = await evidenceService.getInventory(params);
    let items = Array.isArray(result?.items) ? result.items : [];

    if (status) {
      items = items.filter(
        (row) => String(row.status || "").toLowerCase() === status
      );
    }
    if (type) {
      items = items.filter(
        (row) => String(row.evidence_type || "").toLowerCase() === type
      );
    }
    const q = String(query || "")
      .trim()
      .toLowerCase();
    if (q) {
      items = items.filter((row) => {
        const hay = [
          row.file_name,
          row.evidence_id,
          row.case_name,
          row.mime_type,
          sha256Of(row),
        ]
          .join(" ")
          .toLowerCase();
        return hay.includes(q);
      });
    }

    items = [...items].sort((a, b) => {
      const ta = new Date(a.registered_at || 0).getTime();
      const tb = new Date(b.registered_at || 0).getTime();
      return tb - ta;
    });

    const total = items.length;
    const start = (Math.max(1, page) - 1) * pageSize;
    const pageItems = items.slice(start, start + pageSize).map((row) => ({
      ...row,
      id: row.evidence_id,
    }));
    return { items: pageItems, total };
  }, []);

  const {
    data,
    loading,
    error,
    page,
    pageSize,
    total,
    goToPage,
    refresh,
  } = usePagination(fetchInventory, { pageSize: 20 });

  useEffect(() => {
    goToPage(1).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseFilter, statusFilter, typeFilter, search]);

  const diskCount = Number(stats?.by_type?.[EVIDENCE_TYPE.DISK_IMAGE]) || 0;
  const memoryCount = Number(stats?.by_type?.[EVIDENCE_TYPE.MEMORY_DUMP]) || 0;
  const totalCount = Number(stats?.total) || 0;

  const statusChart = useMemo(() => {
    const byStatus = stats?.by_status || {};
    const entries = Object.entries(byStatus).filter(([, n]) => Number(n) > 0);
    if (!entries.length) {
      return {
        labels: ["No data"],
        datasets: [{ data: [1], backgroundColor: ["#e9ecef"], borderWidth: 0 }],
      };
    }
    return {
      labels: entries.map(([key]) =>
        key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
      ),
      datasets: [
        {
          data: entries.map(([, n]) => Number(n) || 0),
          backgroundColor: entries.map(
            ([key]) => EVIDENCE_STATUS_COLOURS[key] || "#6c757d"
          ),
          borderWidth: 1,
          borderColor: "#fff",
        },
      ],
    };
  }, [stats]);

  const handleValidate = async (row) => {
    setActionBusy(row.evidence_id);
    try {
      const result = await evidenceService.validate(row.evidence_id);
      if (result?.validation_passed) {
        success("Validated", `${row.file_name || shortId(row.evidence_id)} passed validation.`);
      } else {
        const failures = (result?.validation_failures || []).join("; ");
        notifyError(
          "Validation failed",
          failures || "Evidence did not pass validation."
        );
      }
      await refresh();
    } catch (err) {
      notifyError("Validate failed", err?.message || "Could not validate evidence.");
    } finally {
      setActionBusy(null);
    }
  };

  const handleVerify = async (row) => {
    setActionBusy(row.evidence_id);
    try {
      const result = await evidenceService.verifyIntegrity(row.evidence_id);
      if (result?.integrity_verified) {
        success(
          "Integrity verified",
          `${row.file_name || shortId(row.evidence_id)} hash matches.`
        );
      } else {
        notifyError(
          "Integrity mismatch",
          "Current file hash does not match the registered digest."
        );
      }
      await refresh();
    } catch (err) {
      notifyError("Verify failed", err?.message || "Could not verify integrity.");
    } finally {
      setActionBusy(null);
    }
  };

  const columns = useMemo(
    () => [
      {
        key: "evidence_id",
        header: "Evidence ID",
        sortable: true,
        render: (row) => (
          <Link
            to={Routes.EvidenceDetail.path.replace(":id", row.evidence_id)}
            className="fw-bold"
          >
            {shortId(row.evidence_id)}
          </Link>
        ),
      },
      {
        key: "file_name",
        header: "File Name",
        sortable: true,
        accessor: "file_name",
      },
      {
        key: "case",
        header: "Case",
        render: (row) =>
          row.case_id ? (
            <Link to={Routes.CaseDetail.path.replace(":id", row.case_id)}>
              {row.case_name || shortId(row.case_id)}
            </Link>
          ) : (
            "—"
          ),
      },
      {
        key: "evidence_type",
        header: "Type",
        sortable: true,
        render: (row) => (
          <Badge
            bg={
              row.evidence_type === EVIDENCE_TYPE.MEMORY_DUMP
                ? "info"
                : "secondary"
            }
          >
            {typeLabel(row.evidence_type)}
          </Badge>
        ),
      },
      {
        key: "status",
        header: "Status",
        sortable: true,
        render: (row) => <StatusBadge status={row.status} type="evidence" />,
      },
      {
        key: "file_size_bytes",
        header: "Size",
        sortable: true,
        render: (row) => formatBytes(row.file_size_bytes),
      },
      {
        key: "mime_type",
        header: "MIME Type",
        render: (row) => row.mime_type || "—",
      },
      {
        key: "hash",
        header: "Hash",
        render: (row) => <HashCell hash={sha256Of(row)} />,
      },
      {
        key: "registered_at",
        header: "Registered",
        sortable: true,
        render: (row) => formatDateRelative(row.registered_at),
      },
    ],
    []
  );

  const renderActions = (row) => {
    const busy = actionBusy === row.evidence_id;
    return (
      <div className="d-flex justify-content-end flex-wrap gap-1">
        <Button
          as={Link}
          to={Routes.EvidenceDetail.path.replace(":id", row.evidence_id)}
          variant="outline-primary"
          size="sm"
          title="View"
        >
          <FontAwesomeIcon icon={faEye} className="me-1" />
          View
        </Button>
        {canUpdate ? (
          <>
            <OverlayTrigger
              overlay={<Tooltip>Re-run evidence validation</Tooltip>}
            >
              <Button
                variant="outline-success"
                size="sm"
                disabled={busy}
                onClick={() => handleValidate(row)}
              >
                <FontAwesomeIcon icon={faCheckCircle} className="me-1" />
                Validate
              </Button>
            </OverlayTrigger>
            <OverlayTrigger
              overlay={<Tooltip>Verify SHA-256 integrity</Tooltip>}
            >
              <Button
                variant="outline-info"
                size="sm"
                disabled={busy}
                onClick={() => handleVerify(row)}
              >
                <FontAwesomeIcon icon={faShieldAlt} className="me-1" />
                Verify Integrity
              </Button>
            </OverlayTrigger>
          </>
        ) : null}
      </div>
    );
  };

  return (
    <Container fluid className="px-0">
      <PageHeader
        title="Evidence Inventory"
        subtitle="Registered forensic images and memory dumps"
        breadcrumbs={[
          { label: "Home", to: Routes.Dashboard.path },
          { label: "Evidence" },
        ]}
        actions={
          canCreate ? (
            <Button
              variant="primary"
              onClick={() => history.push(Routes.EvidenceRegister.path)}
            >
              <FontAwesomeIcon icon={faPlus} className="me-2" />
              Register Evidence
            </Button>
          ) : null
        }
      />

      <Row className="mb-4">
        <Col xs={12} sm={6} xl={3} className="mb-3 mb-xl-0">
          <StatCard
            title="Total Evidence"
            value={totalCount}
            icon={faDatabase}
            colour="primary"
          />
        </Col>
        <Col xs={12} sm={6} xl={3} className="mb-3 mb-xl-0">
          <StatCard
            title="Disk Images"
            value={diskCount}
            icon={faHdd}
            colour="success"
          />
        </Col>
        <Col xs={12} sm={6} xl={3} className="mb-3 mb-xl-0">
          <StatCard
            title="Memory Dumps"
            value={memoryCount}
            icon={faMemory}
            colour="info"
          />
        </Col>
        <Col xs={12} sm={6} xl={3}>
          <Card border="light" className="shadow-sm h-100">
            <Card.Body className="py-2">
              <h6 className="text-muted mb-2 text-uppercase small fw-bold">
                By Status
              </h6>
              <div style={{ maxHeight: 120 }}>
                <Doughnut
                  data={statusChart}
                  options={{
                    responsive: true,
                    maintainAspectRatio: true,
                    plugins: { legend: { display: false } },
                  }}
                />
              </div>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      <Card border="light" className="shadow-sm mb-4">
        <Card.Body>
          <Row className="g-3 align-items-end">
            <Col xs={12} md={3}>
              <Form.Group className="mb-0">
                <Form.Label className="small text-muted mb-1">Case</Form.Label>
                <Form.Select
                  value={caseFilter}
                  onChange={(e) => setCaseFilter(e.target.value)}
                  aria-label="Filter by case"
                >
                  <option value="">All cases</option>
                  {cases.map((c) => (
                    <option key={c.case_id} value={c.case_id}>
                      {c.case_name} ({c.status})
                    </option>
                  ))}
                </Form.Select>
              </Form.Group>
            </Col>
            <Col xs={12} md={2}>
              <Form.Group className="mb-0">
                <Form.Label className="small text-muted mb-1">Status</Form.Label>
                <Form.Select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  aria-label="Filter by status"
                >
                  {STATUS_OPTIONS.map((opt) => (
                    <option key={opt.value || "all"} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </Form.Select>
              </Form.Group>
            </Col>
            <Col xs={12} md={2}>
              <Form.Group className="mb-0">
                <Form.Label className="small text-muted mb-1">Type</Form.Label>
                <Form.Select
                  value={typeFilter}
                  onChange={(e) => setTypeFilter(e.target.value)}
                  aria-label="Filter by type"
                >
                  <option value="">All types</option>
                  <option value={EVIDENCE_TYPE.DISK_IMAGE}>Disk Image</option>
                  <option value={EVIDENCE_TYPE.MEMORY_DUMP}>Memory Dump</option>
                </Form.Select>
              </Form.Group>
            </Col>
            <Col xs={12} md={4}>
              <Form.Label className="small text-muted mb-1">Search</Form.Label>
              <SearchInput
                placeholder="Search filename, hash, case…"
                value={search}
                onChange={setSearch}
              />
            </Col>
            <Col xs={12} md={1}>
              <Button
                variant="outline-secondary"
                className="w-100"
                onClick={() => {
                  setCaseFilter("");
                  setStatusFilter("");
                  setTypeFilter("");
                  setSearch("");
                }}
              >
                Reset
              </Button>
            </Col>
          </Row>
        </Card.Body>
      </Card>

      {error ? (
        <ApiErrorDisplay
          error={error}
          onRetry={() => goToPage(page).catch(() => {})}
          className="mb-3"
        />
      ) : null}

      <Card border="light" className="shadow-sm">
        <Card.Body className="p-0">
          <DataTable
            columns={columns}
            data={data}
            loading={loading}
            sortable
            emptyMessage="No evidence found. Register a forensic image to begin."
            pagination={{ page, pageSize, total }}
            onPageChange={(next) => goToPage(next).catch(() => {})}
            actions={renderActions}
          />
        </Card.Body>
      </Card>
    </Container>
  );
}
