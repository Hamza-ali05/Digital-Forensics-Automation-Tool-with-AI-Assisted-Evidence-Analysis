import React, { useMemo } from "react";
import { Alert, Badge } from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faExclamationTriangle } from "@fortawesome/free-solid-svg-icons";

import DataTable from "components/common/DataTable";
import {
  raw,
  renderArtefactActions,
  suspicionScoreColumns,
  truncateText,
} from "components/forensic/tables/tableHelpers";

const INJECTION_ROW_STYLE = { backgroundColor: "#f8d7da" };

function formatVadRange(row) {
  const data = raw(row);
  const start = data.vad_start || "?";
  const end = data.vad_end || "?";
  return `${start} – ${end}`;
}

function indicatorBadges(row) {
  const indicators = raw(row).suspicious_indicators;
  if (!Array.isArray(indicators) || !indicators.length) {
    return <span className="text-muted">—</span>;
  }
  return (
    <div className="d-flex flex-wrap gap-1">
      {indicators.map((item) => (
        <Badge key={item} bg="danger">
          {item}
        </Badge>
      ))}
    </div>
  );
}

/**
 * Injected-code artefact table with compromise warning banner.
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
export default function InjectedCodeTable({
  data = [],
  loading = false,
  emptyMessage = "No injected code artefacts found",
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
        key: "pid",
        header: "PID",
        render: (row) => {
          const pid = raw(row).pid;
          return pid == null ? "—" : pid;
        },
      },
      {
        key: "process_name",
        header: "Process Name",
        render: (row) => raw(row).process_name || "—",
      },
      {
        key: "vad_range",
        header: "VAD Start-End",
        render: (row) => (
          <code className="small">{formatVadRange(row)}</code>
        ),
      },
      {
        key: "protection",
        header: "Protection",
        render: (row) => raw(row).protection || "—",
      },
      {
        key: "vad_tag",
        header: "Tag",
        render: (row) => raw(row).vad_tag || "—",
      },
      {
        key: "hex_dump_preview",
        header: "Hex Preview",
        render: (row) => {
          const hex = raw(row).hex_dump_preview || "";
          return (
            <code
              className="small text-break"
              style={{ fontFamily: "monospace" }}
              title={hex}
            >
              {truncateText(hex, 32)}
            </code>
          );
        },
      },
      {
        key: "suspicious_indicators",
        header: "Suspicious Indicators",
        render: (row) => indicatorBadges(row),
      },
      ...suspicionScoreColumns(),
    ],
    []
  );

  return (
    <>
      <Alert variant="danger" className="m-3 mb-0">
        <FontAwesomeIcon icon={faExclamationTriangle} className="me-2" />
        Code injection findings indicate potential compromise.
      </Alert>
      <DataTable
        columns={columns}
        data={data}
        loading={loading}
        emptyMessage={emptyMessage}
        getRowStyle={() => INJECTION_ROW_STYLE}
        actions={(row) => renderArtefactActions(row, handlers)}
      />
    </>
  );
}
