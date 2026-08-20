import React, { useCallback, useMemo, useState } from "react";
import { Badge, Button, Container } from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faRedo } from "@fortawesome/free-solid-svg-icons";

import PageHeader from "components/common/PageHeader";
import DataTable from "components/common/DataTable";
import ApiErrorDisplay from "components/common/ApiErrorDisplay";
import SkeletonLoader from "components/common/SkeletonLoader";
import usePolling from "hooks/usePolling";
import useNotification from "hooks/useNotification";
import systemService from "services/system.service";
import { formatDate, formatDateRelative } from "utils/formatters";

/**
 * Admin background task monitor with restart actions.
 */
export default function TaskMonitor() {
  const { success, error: notifyError } = useNotification();
  const [restarting, setRestarting] = useState(null);

  const fetchTasks = useCallback(() => systemService.getTasks(), []);

  const {
    data: tasks,
    loading,
    error,
    startPolling,
  } = usePolling(fetchTasks, 10000, true);

  const rows = useMemo(
    () =>
      Object.entries(tasks || {}).map(([name, status]) => ({
        id: name,
        name,
        ...status,
      })),
    [tasks]
  );

  const handleRestart = async (name) => {
    setRestarting(name);
    try {
      await systemService.restartTask(name);
      success(`Restarted background task: ${name}`);
      startPolling();
      await fetchTasks();
    } catch (err) {
      notifyError(err?.message || `Failed to restart ${name}`);
    } finally {
      setRestarting(null);
    }
  };

  const columns = [
    {
      key: "name",
      label: "Task",
      sortable: true,
      render: (row) => <span className="fw-semibold">{row.name}</span>,
    },
    {
      key: "is_running",
      label: "Status",
      render: (row) => (
        <Badge bg={row.is_running ? "success" : "secondary"}>
          {row.is_running ? "Running" : "Stopped"}
        </Badge>
      ),
    },
    {
      key: "last_run",
      label: "Last Run",
      render: (row) =>
        row.last_run ? (
          <span title={formatDate(row.last_run)}>{formatDateRelative(row.last_run)}</span>
        ) : (
          "—"
        ),
    },
    {
      key: "next_run",
      label: "Next Run",
      render: (row) =>
        row.next_run ? (
          <span title={formatDate(row.next_run)}>{formatDateRelative(row.next_run)}</span>
        ) : (
          "—"
        ),
    },
    {
      key: "run_count",
      label: "Runs",
      sortable: true,
      render: (row) => row.run_count ?? 0,
    },
    {
      key: "error_count",
      label: "Errors",
      sortable: true,
      render: (row) =>
        row.error_count > 0 ? (
          <span className="text-danger">{row.error_count}</span>
        ) : (
          row.error_count ?? 0
        ),
    },
    {
      key: "actions",
      label: "Actions",
      render: (row) => (
        <Button
          size="sm"
          variant="outline-primary"
          disabled={restarting === row.name}
          onClick={() => handleRestart(row.name)}
        >
          <FontAwesomeIcon icon={faRedo} className="me-1" aria-hidden="true" />
          {restarting === row.name ? "Restarting…" : "Restart"}
        </Button>
      ),
    },
  ];

  return (
    <Container fluid className="px-4 py-4">
      <PageHeader
        title="Background Tasks"
        subtitle="Periodic workers registered at startup (auto-refresh every 10s)"
      />

      {error ? <ApiErrorDisplay error={error} className="mb-3" /> : null}

      {loading && !tasks ? (
        <SkeletonLoader lines={5} />
      ) : (
        <DataTable
          columns={columns}
          data={rows}
          sortable
          emptyMessage="No background tasks registered."
        />
      )}
    </Container>
  );
}
