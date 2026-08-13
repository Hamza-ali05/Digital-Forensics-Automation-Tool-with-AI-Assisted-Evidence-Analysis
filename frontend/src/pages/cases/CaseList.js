import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useHistory } from "react-router-dom";
import {
  Button,
  Card,
  Col,
  Container,
  Form,
  Row,
} from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faEye,
  faFolderOpen,
  faFolderPlus,
  faLock,
  faPlus,
} from "@fortawesome/free-solid-svg-icons";
import Datetime from "react-datetime";
import moment from "moment-timezone";

import PageHeader from "components/common/PageHeader";
import DataTable from "components/common/DataTable";
import SearchInput from "components/common/SearchInput";
import StatusBadge from "components/common/StatusBadge";
import ApiErrorDisplay from "components/common/ApiErrorDisplay";
import ConfirmDialog from "components/common/ConfirmDialog";
import { CASE_STATUS } from "utils/constants";
import { formatCaseId, formatDateRelative } from "utils/formatters";
import usePagination from "hooks/usePagination";
import usePermission from "hooks/usePermission";
import useNotification from "hooks/useNotification";
import useConfirmDialog from "hooks/useConfirmDialog";
import casesService from "services/cases.service";
import { Routes } from "routes";

const STATUS_OPTIONS = [
  { value: "", label: "All" },
  { value: CASE_STATUS.CREATED, label: "Created" },
  { value: CASE_STATUS.OPEN, label: "Open" },
  { value: CASE_STATUS.ACTIVE, label: "Active" },
  { value: CASE_STATUS.UNDER_REVIEW, label: "Under Review" },
  { value: CASE_STATUS.CLOSED, label: "Closed" },
  { value: CASE_STATUS.ARCHIVED, label: "Archived" },
];

const CLOSEABLE = new Set([
  CASE_STATUS.OPEN,
  CASE_STATUS.ACTIVE,
  CASE_STATUS.UNDER_REVIEW,
]);

function toMoment(value) {
  if (!value) return null;
  if (moment.isMoment(value)) return value.isValid() ? value : null;
  const m = moment(value);
  return m.isValid() ? m : null;
}

function leadInvestigatorLabel(row) {
  const lead =
    (row.investigators || []).find((inv) => inv.role === "lead") || null;
  if (lead?.full_name) return lead.full_name;
  if (lead?.username) return lead.username;
  if (row.lead_investigator_id) {
    return String(row.lead_investigator_id).slice(0, 8);
  }
  return "—";
}

/**
 * Case list with status/search/date filters, pagination, and lifecycle actions.
 */
export default function CaseList() {
  const history = useHistory();
  const { canCreate, canUpdate } = usePermission("cases");
  const { success, error: notifyError } = useNotification();
  const { dialogProps, openDialog } = useConfirmDialog();

  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [dateFrom, setDateFrom] = useState(null);
  const [dateTo, setDateTo] = useState(null);
  const [actionBusy, setActionBusy] = useState(null);

  const filtersRef = useRef({ status, search, dateFrom, dateTo });
  filtersRef.current = { status, search, dateFrom, dateTo };

  const fetchCases = useCallback(async ({ page, pageSize }) => {
    const {
      status: statusFilter,
      search: nameQuery,
      dateFrom: from,
      dateTo: to,
    } = filtersRef.current;

    const params = {};
    if (statusFilter) params.status = statusFilter;

    const result = await casesService.list(params);
    let items = Array.isArray(result?.cases)
      ? result.cases
      : Array.isArray(result)
        ? result
        : [];

    const q = String(nameQuery || "")
      .trim()
      .toLowerCase();
    if (q) {
      items = items.filter((c) =>
        String(c.case_name || "")
          .toLowerCase()
          .includes(q)
      );
    }

    const fromM = toMoment(from)?.startOf("day");
    const toM = toMoment(to)?.endOf("day");
    if (fromM || toM) {
      items = items.filter((c) => {
        const created = toMoment(c.created_at);
        if (!created) return false;
        if (fromM && created.isBefore(fromM)) return false;
        if (toM && created.isAfter(toM)) return false;
        return true;
      });
    }

    // Newest first
    items = [...items].sort((a, b) => {
      const ta = new Date(a.created_at || 0).getTime();
      const tb = new Date(b.created_at || 0).getTime();
      return tb - ta;
    });

    const total = items.length;
    const start = (Math.max(1, page) - 1) * pageSize;
    const pageItems = items.slice(start, start + pageSize).map((c) => ({
      ...c,
      id: c.case_id,
    }));

    return { cases: pageItems, total };
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
  } = usePagination(fetchCases, { pageSize: 20 });

  useEffect(() => {
    goToPage(1).catch(() => {});
    // Re-fetch when filters change
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, search, dateFrom, dateTo]);

  const handleOpen = async (row) => {
    try {
      await openDialog({
        title: "Open case?",
        message: `Open ${row.case_name || formatCaseId(row.case_id)}? A lead investigator must already be assigned.`,
        confirmLabel: "Open",
        variant: "primary",
      });
    } catch {
      return;
    }

    setActionBusy(row.case_id);
    try {
      await casesService.open(row.case_id);
      success("Case opened", `${row.case_name} is now open.`);
      await refresh();
    } catch (err) {
      notifyError(
        "Unable to open case",
        err?.message || "The case could not be opened."
      );
    } finally {
      setActionBusy(null);
    }
  };

  const handleClose = async (row) => {
    try {
      await openDialog({
        title: "Close case?",
        message: `Close ${row.case_name || formatCaseId(row.case_id)}? This seals linked evidence custody chains.`,
        confirmLabel: "Close",
        variant: "warning",
      });
    } catch {
      return;
    }

    setActionBusy(row.case_id);
    try {
      await casesService.close(row.case_id, {
        reason: "Closed from case list",
      });
      success("Case closed", `${row.case_name} has been closed.`);
      await refresh();
    } catch (err) {
      notifyError(
        "Unable to close case",
        err?.message || "The case could not be closed."
      );
    } finally {
      setActionBusy(null);
    }
  };

  const columns = useMemo(
    () => [
      {
        key: "case_id",
        header: "Case ID",
        sortable: true,
        render: (row) => (
          <Link
            to={Routes.CaseDetail.path.replace(":id", row.case_id)}
            className="fw-bold"
          >
            {formatCaseId(row.case_id)}
          </Link>
        ),
      },
      {
        key: "case_name",
        header: "Case Name",
        sortable: true,
        accessor: "case_name",
      },
      {
        key: "status",
        header: "Status",
        sortable: true,
        render: (row) => <StatusBadge status={row.status} type="case" />,
      },
      {
        key: "lead",
        header: "Lead Investigator",
        render: (row) => leadInvestigatorLabel(row),
      },
      {
        key: "evidence_count",
        header: "Evidence Count",
        sortable: true,
        render: (row) => row.evidence_count ?? row.evidence_ids?.length ?? 0,
      },
      {
        key: "created_at",
        header: "Created",
        sortable: true,
        render: (row) => formatDateRelative(row.created_at),
      },
    ],
    []
  );

  const renderActions = (row) => {
    const busy = actionBusy === row.case_id;
    const statusValue = String(row.status || "").toLowerCase();
    const showOpen = canUpdate && statusValue === CASE_STATUS.CREATED;
    const showClose = canUpdate && CLOSEABLE.has(statusValue);

    return (
      <div className="d-flex justify-content-end gap-1 flex-wrap">
        <Button
          as={Link}
          to={Routes.CaseDetail.path.replace(":id", row.case_id)}
          variant="outline-primary"
          size="sm"
          title="View"
        >
          <FontAwesomeIcon icon={faEye} className="me-1" />
          View
        </Button>
        {showOpen ? (
          <Button
            variant="outline-success"
            size="sm"
            disabled={busy}
            onClick={() => handleOpen(row)}
            title="Open case"
          >
            <FontAwesomeIcon icon={faFolderOpen} className="me-1" />
            Open
          </Button>
        ) : null}
        {showClose ? (
          <Button
            variant="outline-warning"
            size="sm"
            disabled={busy}
            onClick={() => handleClose(row)}
            title="Close case"
          >
            <FontAwesomeIcon icon={faLock} className="me-1" />
            Close
          </Button>
        ) : null}
      </div>
    );
  };

  return (
    <Container fluid className="px-0">
      <PageHeader
        title="Cases"
        subtitle="Investigate and manage forensic cases"
        breadcrumbs={[
          { label: "Home", to: Routes.Dashboard.path },
          { label: "Cases" },
        ]}
        actions={
          canCreate ? (
            <Button
              variant="primary"
              onClick={() => history.push(Routes.CasesNew.path)}
            >
              <FontAwesomeIcon icon={faPlus} className="me-2" />
              New Case
            </Button>
          ) : null
        }
      />

      <Card border="light" className="shadow-sm mb-4">
        <Card.Body>
          <Row className="g-3 align-items-end">
            <Col xs={12} md={3}>
              <Form.Group className="mb-0">
                <Form.Label className="small text-muted mb-1">Status</Form.Label>
                <Form.Select
                  value={status}
                  onChange={(e) => setStatus(e.target.value)}
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
            <Col xs={12} md={4}>
              <Form.Label className="small text-muted mb-1">Search</Form.Label>
              <SearchInput
                placeholder="Search by case name…"
                value={search}
                onChange={setSearch}
              />
            </Col>
            <Col xs={6} md={2}>
              <Form.Group className="mb-0">
                <Form.Label className="small text-muted mb-1">From</Form.Label>
                <Datetime
                  value={dateFrom}
                  onChange={(value) => setDateFrom(toMoment(value))}
                  timeFormat={false}
                  inputProps={{
                    placeholder: "Start date",
                    className: "form-control",
                  }}
                />
              </Form.Group>
            </Col>
            <Col xs={6} md={2}>
              <Form.Group className="mb-0">
                <Form.Label className="small text-muted mb-1">To</Form.Label>
                <Datetime
                  value={dateTo}
                  onChange={(value) => setDateTo(toMoment(value))}
                  timeFormat={false}
                  inputProps={{
                    placeholder: "End date",
                    className: "form-control",
                  }}
                />
              </Form.Group>
            </Col>
            <Col xs={12} md={1} className="d-flex">
              <Button
                variant="outline-secondary"
                className="w-100"
                onClick={() => {
                  setStatus("");
                  setSearch("");
                  setDateFrom(null);
                  setDateTo(null);
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
            emptyMessage="No cases found. Create your first case to begin an investigation."
            pagination={{ page, pageSize, total }}
            onPageChange={(next) => goToPage(next).catch(() => {})}
            actions={renderActions}
          />
        </Card.Body>
        {!loading && canCreate && data.length === 0 && !error ? (
          <Card.Footer className="bg-white text-center border-0 pb-4">
            <Button
              variant="primary"
              onClick={() => history.push(Routes.CasesNew.path)}
            >
              <FontAwesomeIcon icon={faFolderPlus} className="me-2" />
              Create first case
            </Button>
          </Card.Footer>
        ) : null}
      </Card>

      <ConfirmDialog {...dialogProps} />
    </Container>
  );
}
