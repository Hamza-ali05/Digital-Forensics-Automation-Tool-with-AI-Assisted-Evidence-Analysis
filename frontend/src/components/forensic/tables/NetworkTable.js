import React, { useMemo } from "react";
import { Badge } from "@themesberg/react-bootstrap";

import DataTable from "components/common/DataTable";
import { formatDate } from "utils/formatters";
import {
  raw,
  renderArtefactActions,
  suspicionScoreColumns,
} from "components/forensic/tables/tableHelpers";

const EXTERNAL_ROW_STYLE = { backgroundColor: "#ffe5cc" };

function formatEndpoint(address, port) {
  if (!address) return "—";
  if (port == null || port === "") return String(address);
  return `${address}:${port}`;
}

function isExternal(row) {
  const data = raw(row);
  if (data.is_external === true) return true;
  return (
    String(row?.metadata?.sub_category || "").toLowerCase() ===
    "external_connection"
  );
}

function ExternalBadge({ external }) {
  if (external) {
    return <Badge bg="warning" text="dark">External</Badge>;
  }
  return <Badge bg="light" text="dark">Internal</Badge>;
}

/**
 * Network connection artefact table with external-connection highlighting.
 *
 * @param {{
 *   data?: object[],
 *   loading?: boolean,
 *   emptyMessage?: string,
 *   onViewDetails?: (row: object) => void,
 *   onAiExplain?: (row: object) => void,
 *   onViewCorrelations?: (row: object) => void,
 * }} props
 */
export default function NetworkTable({
  data = [],
  loading = false,
  emptyMessage = "No network artefacts found",
  onViewDetails,
  onAiExplain,
  onViewCorrelations,
}) {
  const handlers = useMemo(
    () => ({ onViewDetails, onAiExplain, onViewCorrelations }),
    [onViewDetails, onAiExplain, onViewCorrelations]
  );

  const columns = useMemo(
    () => [
      {
        key: "protocol",
        header: "Protocol",
        render: (row) => raw(row).protocol || "—",
      },
      {
        key: "local_endpoint",
        header: "Local Address:Port",
        render: (row) => {
          const data = raw(row);
          return formatEndpoint(data.local_address, data.local_port);
        },
      },
      {
        key: "remote_endpoint",
        header: "Remote Address:Port",
        render: (row) => {
          const data = raw(row);
          return formatEndpoint(data.remote_address, data.remote_port);
        },
      },
      {
        key: "state",
        header: "State",
        render: (row) => raw(row).state || "—",
      },
      {
        key: "pid",
        header: "PID",
        render: (row) => {
          const pid = raw(row).pid;
          return pid == null ? "—" : pid;
        },
      },
      {
        key: "owner_process",
        header: "Owner Process",
        render: (row) => raw(row).owner_process || "—",
      },
      {
        key: "is_external",
        header: "Is External",
        render: (row) => <ExternalBadge external={isExternal(row)} />,
      },
      {
        key: "created_time",
        header: "Created",
        render: (row) => formatDate(raw(row).created_time),
      },
      ...suspicionScoreColumns(),
    ],
    []
  );

  return (
    <DataTable
      columns={columns}
      data={data}
      loading={loading}
      emptyMessage={emptyMessage}
      getRowStyle={(row) => (isExternal(row) ? EXTERNAL_ROW_STYLE : undefined)}
      actions={(row) => renderArtefactActions(row, handlers)}
    />
  );
}
