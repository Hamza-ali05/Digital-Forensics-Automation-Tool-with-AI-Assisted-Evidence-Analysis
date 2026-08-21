import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Badge,
  Button,
  Card,
  Col,
  Collapse,
  Container,
  Form,
  Row,
} from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faCaretDown,
  faCaretRight,
  faDownload,
} from "@fortawesome/free-solid-svg-icons";
import Datetime from "react-datetime";
import moment from "moment-timezone";

import PageHeader from "components/common/PageHeader";
import DataTable from "components/common/DataTable";
import SearchInput from "components/common/SearchInput";
import ApiErrorDisplay from "components/common/ApiErrorDisplay";
import { PIPELINE_STAGE } from "utils/constants";
import { formatDate, formatHash } from "utils/formatters";
import useNotification from "hooks/useNotification";
import auditService from "services/audit.service";
import usersService from "services/users.service";

const STAGE_OPTIONS = [
  { value: "", label: "All stages" },
  ...Object.values(PIPELINE_STAGE).map((value) => ({
    value,
    label: value.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
  })),
];

function toMoment(value) {
  if (!value) return null;
  if (moment.isMoment(value)) return value.isValid() ? value : null;
  const m = moment(value);
  return m.isValid() ? m : null;
}

function shortId(id) {
  return id ? String(id).slice(0, 8) : "—";
}

function csvEscape(value) {
  const text = value == null ? "" : String(value);
  if (/[",\n]/.test(text)) return `"${text.replace(/"/g, '""')}"`;
  return text;
}

function downloadCsv(filename, rows) {
  const header = [
    "timestamp",
    "stage",
    "action",
    "user_id",
    "evidence_id",
    "details",
  ];
  const lines = [header.join(",")];
  rows.forEach((row) => {
    lines.push(
      [
        row.timestamp,
        row.stage,
        row.action,
        row.user_id,
        row.evidence_id,
        JSON.stringify(row.details || {}),
      ]
        .map(csvEscape)
        .join(",")
    );
  });
  const blob = new Blob([lines.join("\n")], {
    type: "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function DetailsCell({ row }) {
  const [open, setOpen] = useState(false);
  const details = row.details || {};
  const keys = Object.keys(details);
  return (
    <div>
      <Button
        size="sm"
        variant="link"
        className="p-0"
        onClick={() => setOpen((prev) => !prev)}
      >
        <FontAwesomeIcon
          icon={open ? faCaretDown : faCaretRight}
          className="me-1"
        />
        {keys.length ? `${keys.length} fields` : "Empty"}
      </Button>
      <Collapse in={open}>
        <div className="small mt-2">
          {row.hash_before || row.hash_after ? (
            <div className="mb-1">
              {row.hash_before ? (
                <div>
                  Before: <code>{formatHash(row.hash_before, 10)}</code>
                </div>
              ) : null}
              {row.hash_after ? (
                <div>
                  After: <code>{formatHash(row.hash_after, 10)}</code>
                </div>
              ) : null}
            </div>
          ) : null}
          {keys.length ? (
            <pre
              className="mb-0 p-2 bg-light border rounded"
              style={{ whiteSpace: "pre-wrap", maxHeight: 160, overflow: "auto" }}
            >
              {JSON.stringify(details, null, 2)}
            </pre>
          ) : (
            <span className="text-muted">No details</span>
          )}
        </div>
      </Collapse>
    </div>
  );
}

/**
 * Admin audit log browser with filters and CSV export.
 */
export default function AuditLogs() {
  const { info } = useNotification();

  const [entries, setEntries] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [page, setPage] = useState(1);
  const [dateFrom, setDateFrom] = useState(null);
  const [dateTo, setDateTo] = useState(null);
  const [stage, setStage] = useState("");
  const [userFilter, setUserFilter] = useState("");
  const [evidenceSearch, setEvidenceSearch] = useState("");
  const pageSize = 25;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [trail, userList] = await Promise.all([
        auditService.listAggregated(),
        usersService.list().catch(() => []),
      ]);
      setEntries(trail);
      setUsers(Array.isArray(userList) ? userList : userList?.users || []);
    } catch (err) {
      setError(err);
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load().catch(() => {});
  }, [load]);

  const userLabel = useCallback(
    (userId) => {
      if (!userId) return "system";
      const match = users.find(
        (user) => String(user.id) === String(userId) || user.username === userId
      );
      return match?.username || shortId(userId);
    },
    [users]
  );

  const filtered = useMemo(() => {
    let rows = [...entries];
    const fromM = toMoment(dateFrom)?.startOf("day");
    const toM = toMoment(dateTo)?.endOf("day");
    if (fromM || toM) {
      rows = rows.filter((row) => {
        const stamp = toMoment(row.timestamp);
        if (!stamp) return false;
        if (fromM && stamp.isBefore(fromM)) return false;
        if (toM && stamp.isAfter(toM)) return false;
        return true;
      });
    }
    if (stage) {
      rows = rows.filter(
        (row) => String(row.stage || "").toLowerCase() === stage
      );
    }
    if (userFilter) {
      rows = rows.filter((row) => String(row.user_id) === String(userFilter));
    }
    if (evidenceSearch.trim()) {
      const q = evidenceSearch.trim().toLowerCase();
      rows = rows.filter((row) =>
        String(row.evidence_id || "")
          .toLowerCase()
          .includes(q)
      );
    }
    return rows;
  }, [entries, dateFrom, dateTo, stage, userFilter, evidenceSearch]);

  useEffect(() => {
    setPage(1);
  }, [dateFrom, dateTo, stage, userFilter, evidenceSearch]);

  const paged = useMemo(() => {
    const start = (Math.max(1, page) - 1) * pageSize;
    return filtered.slice(start, start + pageSize);
  }, [filtered, page]);

  const columns = useMemo(
    () => [
      {
        key: "timestamp",
        header: "Timestamp",
        sortable: true,
        render: (row) => formatDate(row.timestamp),
      },
      {
        key: "stage",
        header: "Stage",
        render: (row) => (
          <Badge bg="light" text="dark" className="border">
            {String(row.stage || "—").replace(/_/g, " ")}
          </Badge>
        ),
      },
      {
        key: "action",
        header: "Action",
        render: (row) => <span className="fw-semibold small">{row.action}</span>,
      },
      {
        key: "user",
        header: "User",
        render: (row) => userLabel(row.user_id),
      },
      {
        key: "evidence_id",
        header: "Evidence ID",
        render: (row) =>
          row.evidence_id ? <code>{shortId(row.evidence_id)}</code> : "—",
      },
      {
        key: "details",
        header: "Details",
        render: (row) => <DetailsCell row={row} />,
      },
    ],
    [userLabel]
  );

  const handleExport = () => {
    downloadCsv(
      `dfat-audit-${new Date().toISOString().slice(0, 10)}.csv`,
      filtered
    );
    info("CSV exported", `${filtered.length} audit rows downloaded.`);
  };

  return (
    <Container fluid className="px-0">
      <PageHeader
        title="Audit Logs"
        subtitle="Forensic pipeline and evidence audit trail"
        actions={
          <Button variant="outline-secondary" onClick={handleExport}>
            <FontAwesomeIcon icon={faDownload} className="me-2" />
            Export as CSV
          </Button>
        }
      />

      {error ? (
        <ApiErrorDisplay error={error} onRetry={load} className="mb-3" />
      ) : null}

      <Card border="light" className="shadow-sm mb-4">
        <Card.Body>
          <Row className="g-3 align-items-end">
            <Col xs={12} md={3}>
              <Form.Group className="mb-0">
                <Form.Label className="small text-muted mb-1">From</Form.Label>
                <Datetime
                  value={dateFrom}
                  onChange={(value) => setDateFrom(toMoment(value))}
                  timeFormat={false}
                  inputProps={{ className: "form-control", placeholder: "Start" }}
                />
              </Form.Group>
            </Col>
            <Col xs={12} md={3}>
              <Form.Group className="mb-0">
                <Form.Label className="small text-muted mb-1">To</Form.Label>
                <Datetime
                  value={dateTo}
                  onChange={(value) => setDateTo(toMoment(value))}
                  timeFormat={false}
                  inputProps={{ className: "form-control", placeholder: "End" }}
                />
              </Form.Group>
            </Col>
            <Col xs={12} md={2}>
              <Form.Group className="mb-0">
                <Form.Label className="small text-muted mb-1">Stage</Form.Label>
                <Form.Select
                  value={stage}
                  onChange={(e) => setStage(e.target.value)}
                >
                  {STAGE_OPTIONS.map((opt) => (
                    <option key={opt.value || "all"} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </Form.Select>
              </Form.Group>
            </Col>
            <Col xs={12} md={2}>
              <Form.Group className="mb-0">
                <Form.Label className="small text-muted mb-1">User</Form.Label>
                <Form.Select
                  value={userFilter}
                  onChange={(e) => setUserFilter(e.target.value)}
                >
                  <option value="">All users</option>
                  {users.map((user) => (
                    <option key={user.id} value={user.id}>
                      {user.username}
                    </option>
                  ))}
                </Form.Select>
              </Form.Group>
            </Col>
            <Col xs={12} md={2}>
              <Form.Group className="mb-0">
                <Form.Label className="small text-muted mb-1">
                  Evidence ID
                </Form.Label>
                <SearchInput
                  value={evidenceSearch}
                  onChange={setEvidenceSearch}
                  placeholder="Search…"
                />
              </Form.Group>
            </Col>
          </Row>
        </Card.Body>
      </Card>

      <Card border="light" className="shadow-sm">
        <Card.Body className="pt-0">
          <DataTable
            columns={columns}
            data={paged}
            loading={loading}
            emptyMessage="No audit entries match the filters"
            sortable
            pagination={{ page, pageSize, total: filtered.length }}
            onPageChange={setPage}
          />
        </Card.Body>
      </Card>
    </Container>
  );
}
