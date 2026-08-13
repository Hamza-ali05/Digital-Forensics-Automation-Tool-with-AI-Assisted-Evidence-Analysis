import React, { useMemo } from "react";
import { Badge } from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faStar } from "@fortawesome/free-solid-svg-icons";

import DataTable from "components/common/DataTable";
import { formatDate } from "utils/formatters";
import {
  raw,
  renderArtefactActions,
  suspicionScoreColumns,
} from "components/forensic/tables/tableHelpers";

const SECURITY_ROW_STYLE = { backgroundColor: "#fff3cd" };

function isSecurityRelevant(row) {
  const data = raw(row);
  if (data.is_security_relevant === true) return true;
  return (
    String(row?.metadata?.sub_category || "").toLowerCase() === "security_event"
  );
}

function levelBadge(level) {
  const label = String(level || "").trim() || "—";
  const key = label.toLowerCase();
  let bg = "secondary";
  if (key.includes("error") || key.includes("critical")) bg = "danger";
  else if (key.includes("warn")) bg = "warning";
  else if (key.includes("info")) bg = "info";
  else if (key.includes("verbose") || key.includes("debug")) bg = "light";

  return (
    <Badge bg={bg} text={bg === "light" || bg === "warning" ? "dark" : undefined}>
      {label}
    </Badge>
  );
}

/**
 * Event log artefact table with security-relevant highlighting.
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
export default function EventLogTable({
  data = [],
  loading = false,
  emptyMessage = "No event log artefacts found",
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
        key: "event_id",
        header: "Event ID",
        render: (row) => {
          const id = raw(row).event_id;
          return id == null ? "—" : id;
        },
      },
      {
        key: "channel",
        header: "Channel",
        render: (row) => raw(row).channel || "—",
      },
      {
        key: "source",
        header: "Source",
        render: (row) => raw(row).source || "—",
      },
      {
        key: "level",
        header: "Level",
        render: (row) => levelBadge(raw(row).level),
      },
      {
        key: "timestamp",
        header: "Timestamp",
        render: (row) => formatDate(raw(row).timestamp),
      },
      {
        key: "computer",
        header: "Computer",
        render: (row) =>
          raw(row).computer_name || raw(row).computer || "—",
      },
      {
        key: "security_relevant",
        header: "Security Relevant",
        render: (row) =>
          isSecurityRelevant(row) ? (
            <FontAwesomeIcon
              icon={faStar}
              className="text-warning"
              title="Security relevant"
            />
          ) : (
            <span className="text-muted">—</span>
          ),
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
      getRowStyle={(row) =>
        isSecurityRelevant(row) ? SECURITY_ROW_STYLE : undefined
      }
      actions={(row) => renderArtefactActions(row, handlers)}
    />
  );
}
