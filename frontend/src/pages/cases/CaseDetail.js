import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useHistory, useParams } from "react-router-dom";
import {
  Badge,
  Button,
  Card,
  Col,
  Container,
  Form,
  ListGroup,
  Modal,
  Nav,
  Row,
  Spinner,
  Tab,
  Table,
} from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faArchive,
  faFolderOpen,
  faLock,
  faPlus,
  faRedo,
  faStar,
  faTrash,
  faUserPlus,
} from "@fortawesome/free-solid-svg-icons";

import PageHeader from "components/common/PageHeader";
import StatusBadge from "components/common/StatusBadge";
import DataTable from "components/common/DataTable";
import ApiErrorDisplay from "components/common/ApiErrorDisplay";
import EmptyState from "components/common/EmptyState";
import SkeletonLoader from "components/common/SkeletonLoader";
import ConfirmDialog from "components/common/ConfirmDialog";
import CaseLifecycleBar from "components/forensic/CaseLifecycleBar";
import { CASE_STATUS } from "utils/constants";
import {
  formatBytes,
  formatCaseId,
  formatDate,
  formatDateRelative,
} from "utils/formatters";
import usePermission from "hooks/usePermission";
import useNotification from "hooks/useNotification";
import useConfirmDialog from "hooks/useConfirmDialog";
import casesService from "services/cases.service";
import evidenceService from "services/evidence.service";
import pipelineService from "services/pipeline.service";
import usersService from "services/users.service";
import { Routes } from "routes";

function shortEvidenceId(id) {
  if (!id) return "—";
  return String(id).slice(0, 8);
}

function basename(path) {
  if (!path) return "—";
  const parts = String(path).replace(/\\/g, "/").split("/");
  return parts[parts.length - 1] || path;
}

/**
 * Case detail — lifecycle, investigators, evidence, and activity.
 */
export default function CaseDetail() {
  const { id: caseId } = useParams();
  const history = useHistory();
  const { canUpdate, canCreate } = usePermission("cases");
  const evidencePerm = usePermission("evidence");
  const { success, error: notifyError } = useNotification();
  const { dialogProps, openDialog } = useConfirmDialog();

  const [caseData, setCaseData] = useState(null);
  const [summary, setSummary] = useState(null);
  const [evidenceRows, setEvidenceRows] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [activeTab, setActiveTab] = useState("overview");

  const [assignOpen, setAssignOpen] = useState(false);
  const [users, setUsers] = useState([]);
  const [usersError, setUsersError] = useState(null);
  const [assignForm, setAssignForm] = useState({
    userId: "",
    role: "member",
  });
  const [assignBusy, setAssignBusy] = useState(false);

  const [addEvidenceOpen, setAddEvidenceOpen] = useState(false);
  const [inventory, setInventory] = useState([]);
  const [addEvidenceId, setAddEvidenceId] = useState("");
  const [addEvidenceBusy, setAddEvidenceBusy] = useState(false);

  const load = useCallback(async () => {
    if (!caseId) return;
    setLoading(true);
    setError(null);
    try {
      const [detail, caseSummary, inventoryResult, jobsResult] =
        await Promise.all([
          casesService.getById(caseId),
          casesService.getSummary(caseId),
          evidencePerm.canRead
            ? evidenceService
                .getInventory({ case_id: caseId })
                .catch(() => ({ items: [] }))
            : Promise.resolve({ items: [] }),
          pipelineService
            .listJobs({ case_id: caseId })
            .catch(() => []),
        ]);
      setCaseData(detail);
      setSummary(caseSummary);
      setEvidenceRows(
        Array.isArray(inventoryResult?.items) ? inventoryResult.items : []
      );
      setJobs(Array.isArray(jobsResult) ? jobsResult : []);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [caseId, evidencePerm.canRead]);

  useEffect(() => {
    load();
  }, [load]);

  const status = String(caseData?.status || "").toLowerCase();
  const investigators = caseData?.investigators || summary?.investigators || [];
  const hasLead = Boolean(
    caseData?.lead_investigator_id ||
      investigators.some((inv) => inv.role === "lead")
  );

  const stats = useMemo(() => {
    const evidenceCount =
      caseData?.evidence_count ??
      summary?.evidence_count ??
      evidenceRows.length ??
      0;
    const artefactCount = jobs.reduce(
      (max, job) => Math.max(max, Number(job.artefact_count) || 0),
      0
    );
    const reportCount = jobs.filter((job) => job.report_id).length;
    return { evidenceCount, artefactCount, reportCount };
  }, [caseData, summary, evidenceRows, jobs]);

  const activity = useMemo(() => {
    const entries = [];

    if (caseData?.created_at || summary?.created_at) {
      entries.push({
        id: "created",
        timestamp: caseData?.created_at || summary?.created_at,
        action: "Case created",
        user: "system",
        details: caseData?.case_name || summary?.case_name,
      });
    }
    if (caseData?.opened_at || summary?.opened_at) {
      entries.push({
        id: "opened",
        timestamp: caseData?.opened_at || summary?.opened_at,
        action: "Case opened",
        user: "system",
        details: null,
      });
    }
    if (caseData?.closed_at || summary?.closed_at) {
      entries.push({
        id: "closed",
        timestamp: caseData?.closed_at || summary?.closed_at,
        action: "Case closed",
        user: "system",
        details: caseData?.closure_reason || summary?.closure_reason,
      });
    }
    if (caseData?.archived_at || summary?.archived_at) {
      entries.push({
        id: "archived",
        timestamp: caseData?.archived_at || summary?.archived_at,
        action: "Case archived",
        user: "system",
        details: null,
      });
    }

    const notes = caseData?.notes || summary?.notes || [];
    notes.forEach((note, index) => {
      entries.push({
        id: `note-${index}`,
        timestamp: caseData?.closed_at || caseData?.created_at,
        action: "Case note",
        user: "system",
        details: note,
      });
    });

    investigators.forEach((inv, index) => {
      entries.push({
        id: `inv-${inv.user_id || index}`,
        timestamp: inv.assigned_at,
        action: `Investigator assigned (${inv.role})`,
        user: inv.full_name || inv.username || inv.user_id,
        details: inv.username,
      });
    });

    evidenceRows.forEach((item) => {
      entries.push({
        id: `ev-${item.evidence_id}`,
        timestamp: item.registered_at,
        action: "Evidence registered",
        user: "system",
        details: item.file_name || item.evidence_id,
      });
    });

    jobs.forEach((job) => {
      entries.push({
        id: `job-${job.job_id}`,
        timestamp: job.completed_at || job.started_at || job.created_at,
        action: `Pipeline ${job.status}`,
        user: job.user_id || "system",
        details: job.report_id
          ? `Report ${String(job.report_id).slice(0, 8)}`
          : job.job_id,
      });
    });

    return entries
      .filter((e) => e.timestamp)
      .sort(
        (a, b) =>
          new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
      );
  }, [caseData, summary, investigators, evidenceRows, jobs]);

  const runTransition = async (label, actionFn) => {
    setBusy(true);
    try {
      await actionFn();
      success("Case updated", `${label} completed successfully.`);
      await load();
    } catch (err) {
      notifyError(label, err?.message || "Transition failed.");
    } finally {
      setBusy(false);
    }
  };

  const handleLifecycle = async (action) => {
    if (!caseId) return;

    try {
      if (action === "open") {
        if (!hasLead) {
          notifyError(
            "Cannot open case",
            "Assign a lead investigator before opening the case."
          );
          return;
        }
        await openDialog({
          title: "Open case?",
          message: "Transition this case from Created to Open.",
          confirmLabel: "Open Case",
        });
        await runTransition("Open case", () => casesService.open(caseId));
        return;
      }

      if (action === "activate") {
        await openDialog({
          title: "Activate case?",
          message: "Mark this case as Active for investigation work.",
          confirmLabel: "Activate",
        });
        await runTransition("Activate case", () =>
          casesService.activate(caseId)
        );
        return;
      }

      if (action === "submit_review") {
        await openDialog({
          title: "Submit for review?",
          message: "Move this case to Under Review.",
          confirmLabel: "Submit",
        });
        await runTransition("Submit for review", () =>
          casesService.submitReview(caseId)
        );
        return;
      }

      if (action === "close") {
        const reason = await openDialog({
          title: "Close case?",
          message:
            "Closing seals linked evidence custody chains. Provide a closure reason.",
          confirmLabel: "Close",
          variant: "warning",
          requireReason: true,
          reasonLabel: "Closure reason",
        });
        await runTransition("Close case", () =>
          casesService.close(caseId, { reason })
        );
        return;
      }

      if (action === "reopen") {
        const reason = await openDialog({
          title: "Reopen case?",
          message: "Return this case from Under Review to Active.",
          confirmLabel: "Reopen",
          requireReason: true,
          reasonLabel: "Reopen reason",
        });
        await runTransition("Reopen case", () =>
          casesService.reopen(caseId, { reason })
        );
        return;
      }

      if (action === "archive") {
        await openDialog({
          title: "Archive case?",
          message: "Archive is a terminal state. Continue?",
          confirmLabel: "Archive",
          variant: "warning",
        });
        await runTransition("Archive case", () =>
          casesService.archive(caseId)
        );
      }
    } catch {
      // Cancelled confirm dialog
    }
  };

  const openAssignModal = async () => {
    setAssignForm({ userId: "", role: "member" });
    setUsersError(null);
    setAssignOpen(true);
    try {
      const list = await usersService.list();
      setUsers(Array.isArray(list) ? list : []);
    } catch (err) {
      setUsers([]);
      setUsersError(
        err?.status === 403
          ? "User directory is admin-only. Enter a user ID manually."
          : err?.message || "Unable to load users."
      );
    }
  };

  const handleAssign = async (event) => {
    event.preventDefault();
    if (!assignForm.userId.trim()) return;
    setAssignBusy(true);
    try {
      await casesService.assignInvestigator(caseId, {
        user_id: assignForm.userId.trim(),
        role: assignForm.role,
      });
      success("Investigator assigned", "The investigator was added to this case.");
      setAssignOpen(false);
      await load();
    } catch (err) {
      notifyError("Assign failed", err?.message || "Could not assign investigator.");
    } finally {
      setAssignBusy(false);
    }
  };

  const handleRemoveInvestigator = async (inv) => {
    if (investigators.length <= 1) {
      notifyError(
        "Cannot remove",
        "A case must keep at least one investigator."
      );
      return;
    }
    try {
      await openDialog({
        title: "Remove investigator?",
        message: `Remove ${inv.full_name || inv.username} from this case?`,
        confirmLabel: "Remove",
        variant: "danger",
      });
    } catch {
      return;
    }
    setBusy(true);
    try {
      await casesService.removeInvestigator(caseId, inv.user_id);
      success("Investigator removed", "Assignment updated.");
      await load();
    } catch (err) {
      notifyError("Remove failed", err?.message || "Could not remove investigator.");
    } finally {
      setBusy(false);
    }
  };

  const openAddEvidenceModal = async () => {
    setAddEvidenceId("");
    setAddEvidenceOpen(true);
    if (!evidencePerm.canRead) return;
    try {
      const result = await evidenceService.getInventory();
      const items = Array.isArray(result?.items) ? result.items : [];
      const linked = new Set(
        (caseData?.evidence_ids || []).concat(
          evidenceRows.map((r) => r.evidence_id)
        )
      );
      setInventory(items.filter((item) => !linked.has(item.evidence_id)));
    } catch {
      setInventory([]);
    }
  };

  const handleAddEvidence = async (event) => {
    event.preventDefault();
    if (!addEvidenceId.trim()) return;
    setAddEvidenceBusy(true);
    try {
      await casesService.addEvidence(caseId, {
        evidence_id: addEvidenceId.trim(),
      });
      success("Evidence linked", "Evidence was added to this case.");
      setAddEvidenceOpen(false);
      await load();
    } catch (err) {
      notifyError("Add evidence failed", err?.message || "Could not link evidence.");
    } finally {
      setAddEvidenceBusy(false);
    }
  };

  const lifecycleButtons = useMemo(() => {
    if (!canUpdate) return [];
    const buttons = [];
    if (status === CASE_STATUS.CREATED) {
      buttons.push({
        key: "open",
        label: "Open Case",
        icon: faFolderOpen,
        variant: "primary",
        disabled: !hasLead,
        title: hasLead
          ? "Open case"
          : "Assign a lead investigator first",
      });
    }
    if (status === CASE_STATUS.OPEN) {
      buttons.push({
        key: "activate",
        label: "Activate",
        icon: faFolderOpen,
        variant: "success",
      });
      buttons.push({
        key: "close",
        label: "Close",
        icon: faLock,
        variant: "warning",
      });
    }
    if (status === CASE_STATUS.ACTIVE) {
      buttons.push({
        key: "submit_review",
        label: "Submit for Review",
        icon: faRedo,
        variant: "info",
      });
      buttons.push({
        key: "close",
        label: "Close",
        icon: faLock,
        variant: "warning",
      });
    }
    if (status === CASE_STATUS.UNDER_REVIEW) {
      buttons.push({
        key: "reopen",
        label: "Reopen",
        icon: faRedo,
        variant: "primary",
      });
      buttons.push({
        key: "close",
        label: "Close",
        icon: faLock,
        variant: "warning",
      });
    }
    if (status === CASE_STATUS.CLOSED) {
      buttons.push({
        key: "archive",
        label: "Archive",
        icon: faArchive,
        variant: "secondary",
      });
    }
    return buttons;
  }, [canUpdate, status, hasLead]);

  const evidenceColumns = useMemo(
    () => [
      {
        key: "evidence_id",
        header: "ID",
        render: (row) => (
          <Link
            to={Routes.EvidenceDetail.path.replace(":id", row.evidence_id)}
            className="fw-bold"
          >
            {shortEvidenceId(row.evidence_id)}
          </Link>
        ),
      },
      {
        key: "file_name",
        header: "Filename",
        render: (row) => row.file_name || basename(row.file_path),
      },
      {
        key: "evidence_type",
        header: "Type",
        render: (row) =>
          String(row.evidence_type || "")
            .replace(/_/g, " ")
            .replace(/\b\w/g, (c) => c.toUpperCase()) || "—",
      },
      {
        key: "status",
        header: "Status",
        render: (row) => (
          <StatusBadge status={row.status} type="evidence" />
        ),
      },
      {
        key: "file_size_bytes",
        header: "Size",
        render: (row) => formatBytes(row.file_size_bytes),
      },
      {
        key: "registered_at",
        header: "Registered",
        render: (row) => formatDateRelative(row.registered_at),
      },
    ],
    []
  );

  if (loading && !caseData) {
    return (
      <Container fluid className="px-0">
        <SkeletonLoader type="detail" rows={6} />
      </Container>
    );
  }

  if (error && !caseData) {
    return (
      <Container fluid className="px-0">
        <PageHeader title="Case Detail" />
        <ApiErrorDisplay error={error} onRetry={load} />
        <Button
          variant="outline-secondary"
          className="mt-3"
          onClick={() => history.push(Routes.Cases.path)}
        >
          Back to cases
        </Button>
      </Container>
    );
  }

  return (
    <Container fluid className="px-0">
      <PageHeader
        title={caseData?.case_name || "Case Detail"}
        subtitle={formatCaseId(caseId)}
        breadcrumbs={[
          { label: "Home", to: Routes.Dashboard.path },
          { label: "Cases", to: Routes.Cases.path },
          { label: caseData?.case_name || "Detail" },
        ]}
        actions={
          <div className="d-flex align-items-center flex-wrap gap-2">
            <StatusBadge status={status} type="case" />
            {lifecycleButtons.map((btn) => (
              <Button
                key={btn.key}
                variant={btn.variant}
                size="sm"
                disabled={busy || btn.disabled}
                title={btn.title}
                onClick={() => handleLifecycle(btn.key)}
              >
                <FontAwesomeIcon icon={btn.icon} className="me-1" />
                {btn.label}
              </Button>
            ))}
          </div>
        }
      />

      <Card border="light" className="shadow-sm mb-4">
        <Card.Body>
          <CaseLifecycleBar status={status} />
        </Card.Body>
      </Card>

      {error ? (
        <ApiErrorDisplay error={error} onRetry={load} className="mb-3" />
      ) : null}

      <Tab.Container
        activeKey={activeTab}
        onSelect={(key) => key && setActiveTab(key)}
      >
        <Card border="light" className="shadow-sm">
          <Card.Header className="border-bottom border-light bg-white">
            <Nav variant="tabs" className="flex-nowrap">
              <Nav.Item>
                <Nav.Link eventKey="overview">Overview</Nav.Link>
              </Nav.Item>
              <Nav.Item>
                <Nav.Link eventKey="investigators">Investigators</Nav.Link>
              </Nav.Item>
              <Nav.Item>
                <Nav.Link eventKey="evidence">Evidence</Nav.Link>
              </Nav.Item>
              <Nav.Item>
                <Nav.Link eventKey="activity">Activity</Nav.Link>
              </Nav.Item>
            </Nav>
          </Card.Header>
          <Card.Body>
            <Tab.Content>
              <Tab.Pane eventKey="overview">
                <Row>
                  <Col xs={12} lg={8} className="mb-4 mb-lg-0">
                    <h5 className="mb-3">Case metadata</h5>
                    <Table responsive borderless className="mb-0">
                      <tbody>
                        <tr>
                          <th className="ps-0 text-muted" style={{ width: "30%" }}>
                            Case ID
                          </th>
                          <td>
                            <code>{caseId}</code> ({formatCaseId(caseId)})
                          </td>
                        </tr>
                        <tr>
                          <th className="ps-0 text-muted">Name</th>
                          <td>{caseData?.case_name}</td>
                        </tr>
                        <tr>
                          <th className="ps-0 text-muted">Description</th>
                          <td className="text-break">
                            {caseData?.description ||
                              summary?.description ||
                              "—"}
                          </td>
                        </tr>
                        <tr>
                          <th className="ps-0 text-muted">Status</th>
                          <td>
                            <StatusBadge status={status} type="case" />
                          </td>
                        </tr>
                        <tr>
                          <th className="ps-0 text-muted">Created</th>
                          <td>
                            {formatDate(
                              caseData?.created_at || summary?.created_at
                            )}
                          </td>
                        </tr>
                        <tr>
                          <th className="ps-0 text-muted">Opened</th>
                          <td>
                            {formatDate(
                              caseData?.opened_at || summary?.opened_at
                            )}
                          </td>
                        </tr>
                        <tr>
                          <th className="ps-0 text-muted">Closed</th>
                          <td>
                            {formatDate(
                              caseData?.closed_at || summary?.closed_at
                            )}
                          </td>
                        </tr>
                        {(caseData?.tags || summary?.tags || []).length ? (
                          <tr>
                            <th className="ps-0 text-muted">Tags</th>
                            <td>
                              {(caseData?.tags || summary?.tags || []).map(
                                (tag) => (
                                  <Badge
                                    key={tag}
                                    bg="secondary"
                                    className="me-1"
                                  >
                                    {tag}
                                  </Badge>
                                )
                              )}
                            </td>
                          </tr>
                        ) : null}
                      </tbody>
                    </Table>
                  </Col>
                  <Col xs={12} lg={4}>
                    <h5 className="mb-3">Statistics</h5>
                    <ListGroup>
                      <ListGroup.Item className="d-flex justify-content-between">
                        <span>Evidence</span>
                        <strong>{stats.evidenceCount}</strong>
                      </ListGroup.Item>
                      <ListGroup.Item className="d-flex justify-content-between">
                        <span>Artefacts</span>
                        <strong>{stats.artefactCount}</strong>
                      </ListGroup.Item>
                      <ListGroup.Item className="d-flex justify-content-between">
                        <span>Reports</span>
                        <strong>{stats.reportCount}</strong>
                      </ListGroup.Item>
                    </ListGroup>
                  </Col>
                </Row>
              </Tab.Pane>

              <Tab.Pane eventKey="investigators">
                <div className="d-flex justify-content-between align-items-center mb-3">
                  <h5 className="mb-0">Investigators</h5>
                  {canUpdate &&
                  status !== CASE_STATUS.CLOSED &&
                  status !== CASE_STATUS.ARCHIVED ? (
                    <Button size="sm" variant="primary" onClick={openAssignModal}>
                      <FontAwesomeIcon icon={faUserPlus} className="me-1" />
                      Assign Investigator
                    </Button>
                  ) : null}
                </div>
                {investigators.length === 0 ? (
                  <EmptyState
                    title="No investigators assigned"
                    description="Assign a lead investigator before opening the case."
                  />
                ) : (
                  <Table responsive hover className="align-middle">
                    <thead className="thead-light">
                      <tr>
                        <th>Name</th>
                        <th>Role</th>
                        <th>Assigned</th>
                        <th className="text-end">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {investigators.map((inv) => {
                        const isLead = inv.role === "lead";
                        return (
                          <tr
                            key={inv.user_id}
                            className={isLead ? "table-warning" : undefined}
                          >
                            <td>
                              {isLead ? (
                                <FontAwesomeIcon
                                  icon={faStar}
                                  className="text-warning me-2"
                                  title="Lead investigator"
                                />
                              ) : null}
                              <strong>{inv.full_name || inv.username}</strong>
                              <div className="small text-muted">
                                {inv.username}
                              </div>
                            </td>
                            <td>
                              <Badge bg={isLead ? "warning" : "secondary"}>
                                {inv.role}
                              </Badge>
                            </td>
                            <td>{formatDateRelative(inv.assigned_at)}</td>
                            <td className="text-end">
                              {canUpdate ? (
                                <Button
                                  size="sm"
                                  variant="outline-danger"
                                  disabled={
                                    busy || investigators.length <= 1
                                  }
                                  title={
                                    investigators.length <= 1
                                      ? "Cannot remove the only investigator"
                                      : "Remove"
                                  }
                                  onClick={() => handleRemoveInvestigator(inv)}
                                >
                                  <FontAwesomeIcon icon={faTrash} />
                                </Button>
                              ) : (
                                "—"
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </Table>
                )}
              </Tab.Pane>

              <Tab.Pane eventKey="evidence">
                <div className="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
                  <h5 className="mb-0">Evidence</h5>
                  <div className="d-flex gap-2">
                    {canUpdate &&
                    status !== CASE_STATUS.CLOSED &&
                    status !== CASE_STATUS.ARCHIVED ? (
                      <Button
                        size="sm"
                        variant="outline-primary"
                        onClick={openAddEvidenceModal}
                      >
                        <FontAwesomeIcon icon={faPlus} className="me-1" />
                        Add Evidence
                      </Button>
                    ) : null}
                    {(canCreate || evidencePerm.canCreate) &&
                    status !== CASE_STATUS.CLOSED &&
                    status !== CASE_STATUS.ARCHIVED ? (
                      <Button
                        as={Link}
                        to={`${Routes.EvidenceRegister.path}?caseId=${encodeURIComponent(
                          caseId
                        )}`}
                        size="sm"
                        variant="primary"
                      >
                        Register Evidence
                      </Button>
                    ) : null}
                  </div>
                </div>
                <DataTable
                  columns={evidenceColumns}
                  data={evidenceRows.map((row) => ({
                    ...row,
                    id: row.evidence_id,
                  }))}
                  loading={loading}
                  emptyMessage="No evidence registered to this case yet."
                />
              </Tab.Pane>

              <Tab.Pane eventKey="activity">
                <h5 className="mb-3">Activity</h5>
                {activity.length === 0 ? (
                  <EmptyState
                    title="No activity yet"
                    description="Lifecycle events, investigators, evidence, and pipeline jobs will appear here."
                  />
                ) : (
                  <ListGroup
                    variant="flush"
                    style={{ maxHeight: 480, overflowY: "auto" }}
                  >
                    {activity.map((item) => (
                      <ListGroup.Item
                        key={item.id}
                        className="px-0 border-bottom border-light"
                      >
                        <div className="fw-bold">{item.action}</div>
                        <div className="small text-muted">
                          {formatDate(item.timestamp)} · {item.user}
                        </div>
                        {item.details ? (
                          <div className="small mt-1 text-break">
                            {item.details}
                          </div>
                        ) : null}
                      </ListGroup.Item>
                    ))}
                  </ListGroup>
                )}
              </Tab.Pane>
            </Tab.Content>
          </Card.Body>
        </Card>
      </Tab.Container>

      <ConfirmDialog {...dialogProps} />

      {/* Assign investigator modal */}
      <Modal show={assignOpen} onHide={() => setAssignOpen(false)} centered>
        <Form onSubmit={handleAssign}>
          <Modal.Header closeButton>
            <Modal.Title>Assign Investigator</Modal.Title>
          </Modal.Header>
          <Modal.Body>
            {usersError ? (
              <p className="small text-muted">{usersError}</p>
            ) : null}
            {users.length > 0 ? (
              <Form.Group className="mb-3">
                <Form.Label>User</Form.Label>
                <Form.Select
                  value={assignForm.userId}
                  onChange={(e) => {
                    const userId = e.target.value;
                    setAssignForm((prev) => ({
                      ...prev,
                      userId,
                    }));
                  }}
                  required
                >
                  <option value="">Select user…</option>
                  {users.map((user) => (
                    <option key={user.id || user.user_id} value={user.id || user.user_id}>
                      {user.full_name || user.username} ({user.username})
                    </option>
                  ))}
                </Form.Select>
              </Form.Group>
            ) : (
              <Form.Group className="mb-3">
                <Form.Label>User ID</Form.Label>
                <Form.Control
                  value={assignForm.userId}
                  onChange={(e) => {
                    const userId = e.target.value;
                    setAssignForm((prev) => ({
                      ...prev,
                      userId,
                    }));
                  }}
                  placeholder="User UUID"
                  required
                />
              </Form.Group>
            )}
            <Form.Group>
              <Form.Label>Role</Form.Label>
              <Form.Select
                value={assignForm.role}
                onChange={(e) => {
                  const role = e.target.value;
                  setAssignForm((prev) => ({ ...prev, role }));
                }}
              >
                <option value="member">Member</option>
                <option value="lead">Lead</option>
              </Form.Select>
            </Form.Group>
          </Modal.Body>
          <Modal.Footer>
            <Button
              variant="link"
              className="text-gray-600"
              onClick={() => setAssignOpen(false)}
            >
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={assignBusy}>
              {assignBusy ? (
                <Spinner animation="border" size="sm" />
              ) : (
                "Assign"
              )}
            </Button>
          </Modal.Footer>
        </Form>
      </Modal>

      {/* Add evidence modal */}
      <Modal
        show={addEvidenceOpen}
        onHide={() => setAddEvidenceOpen(false)}
        centered
      >
        <Form onSubmit={handleAddEvidence}>
          <Modal.Header closeButton>
            <Modal.Title>Add Evidence</Modal.Title>
          </Modal.Header>
          <Modal.Body>
            {inventory.length > 0 ? (
              <Form.Group className="mb-3">
                <Form.Label>Select from inventory</Form.Label>
                <Form.Select
                  value={addEvidenceId}
                  onChange={(e) => setAddEvidenceId(e.target.value)}
                >
                  <option value="">Choose evidence…</option>
                  {inventory.map((item) => (
                    <option key={item.evidence_id} value={item.evidence_id}>
                      {item.file_name} ({shortEvidenceId(item.evidence_id)})
                    </option>
                  ))}
                </Form.Select>
              </Form.Group>
            ) : null}
            <Form.Group>
              <Form.Label>Evidence ID</Form.Label>
              <Form.Control
                value={addEvidenceId}
                onChange={(e) => setAddEvidenceId(e.target.value)}
                placeholder="Evidence UUID"
                required
              />
            </Form.Group>
          </Modal.Body>
          <Modal.Footer>
            <Button
              variant="link"
              className="text-gray-600"
              onClick={() => setAddEvidenceOpen(false)}
            >
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={addEvidenceBusy}>
              {addEvidenceBusy ? (
                <Spinner animation="border" size="sm" />
              ) : (
                "Add to case"
              )}
            </Button>
          </Modal.Footer>
        </Form>
      </Modal>
    </Container>
  );
}
