import React, { useMemo, useState } from "react";
import { Button } from "@themesberg/react-bootstrap";

import DataTable from "components/common/DataTable";
import { formatDate } from "utils/formatters";
import {
  raw,
  renderArtefactActions,
  suspicionScoreColumns,
} from "components/forensic/tables/tableHelpers";

const SUSPICIOUS_ROW_STYLE = { backgroundColor: "#fff3cd" };

const SUSPICIOUS_NAME_RE = /mimikatz|psexec|procdump|lazagne|bloodhound|rubeus|sharphound|cobalt|beacon/i;
const SCRIPTING_HOST_RE =
  /^(cmd|powershell|pwsh|wscript|cscript|mshta|rundll32)\.exe$/i;

function processName(row) {
  const data = raw(row);
  return data.name || data.process_name || "—";
}

function isSuspiciousProcess(row) {
  const name = String(processName(row));
  if (SUSPICIOUS_NAME_RE.test(name)) return true;
  if (SCRIPTING_HOST_RE.test(name)) return true;
  return false;
}

function ExpandableCommandLine({ text, max = 48 }) {
  const [expanded, setExpanded] = useState(false);
  if (text == null || text === "") return "—";
  const value = String(text);
  if (value.length <= max) {
    return (
      <code className="small text-break" title={value}>
        {value}
      </code>
    );
  }
  return (
    <span>
      <code className="small text-break" title={value}>
        {expanded ? value : `${value.slice(0, max)}…`}
      </code>{" "}
      <Button
        variant="link"
        size="sm"
        className="p-0 align-baseline"
        onClick={() => setExpanded((prev) => !prev)}
      >
        {expanded ? "Less" : "More"}
      </Button>
    </span>
  );
}

/**
 * Running-process artefact table with suspicious-name highlighting.
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
export default function ProcessTable({
  data = [],
  loading = false,
  emptyMessage = "No process artefacts found",
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
        key: "ppid",
        header: "PPID",
        render: (row) => {
          const ppid = raw(row).ppid;
          return ppid == null ? "—" : ppid;
        },
      },
      {
        key: "name",
        header: "Process Name",
        render: (row) => processName(row),
      },
      {
        key: "create_time",
        header: "Create Time",
        render: (row) => formatDate(raw(row).create_time),
      },
      {
        key: "exit_time",
        header: "Exit Time",
        render: (row) => formatDate(raw(row).exit_time),
      },
      {
        key: "session_id",
        header: "Session ID",
        render: (row) => {
          const sessionId = raw(row).session_id;
          return sessionId == null ? "—" : sessionId;
        },
      },
      {
        key: "threads",
        header: "Threads",
        render: (row) => {
          const threads = raw(row).threads;
          return threads == null ? "—" : threads;
        },
      },
      {
        key: "command_line",
        header: "Command Line",
        render: (row) => (
          <ExpandableCommandLine text={raw(row).command_line} />
        ),
      },
      {
        key: "parent_name",
        header: "Parent Name",
        render: (row) => raw(row).parent_name || "—",
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
        isSuspiciousProcess(row) ? SUSPICIOUS_ROW_STYLE : undefined
      }
      actions={(row) => renderArtefactActions(row, handlers)}
    />
  );
}
