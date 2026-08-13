import React, { useMemo } from "react";

import DataTable from "components/common/DataTable";
import { formatDate } from "utils/formatters";
import {
  raw,
  renderArtefactActions,
  suspicionScoreColumns,
  truncateText,
} from "components/forensic/tables/tableHelpers";

const AUTORUN_ROW_STYLE = { backgroundColor: "#ffe5cc" };

const AUTORUN_PATH_RE = /\\Run(Once(Ex)?)?(\\|$)/i;

function isAutorunKey(row) {
  const data = raw(row);
  if (String(row?.metadata?.sub_category || "").toLowerCase() === "autorun_key") {
    return true;
  }
  const keyPath = String(data.key_path || data.registry_path || "");
  return AUTORUN_PATH_RE.test(keyPath);
}

/**
 * Registry key artefact table with autorun-key highlighting.
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
export default function RegistryTable({
  data = [],
  loading = false,
  emptyMessage = "No registry artefacts found",
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
        key: "hive",
        header: "Hive",
        render: (row) => raw(row).hive_name || raw(row).hive || "—",
      },
      {
        key: "key_path",
        header: "Key Path",
        render: (row) => {
          const path = raw(row).key_path || raw(row).registry_path || "—";
          return (
            <code className="small text-break" title={path}>
              {truncateText(path, 80)}
            </code>
          );
        },
      },
      {
        key: "value_name",
        header: "Value Name",
        render: (row) => raw(row).value_name || "—",
      },
      {
        key: "value_data",
        header: "Value Data",
        render: (row) => {
          const value = raw(row).value_data;
          const text =
            value == null
              ? "—"
              : typeof value === "object"
                ? JSON.stringify(value)
                : String(value);
          return (
            <span className="small text-break" title={text}>
              {truncateText(text, 48)}
            </span>
          );
        },
      },
      {
        key: "value_type",
        header: "Value Type",
        render: (row) => raw(row).value_type || "—",
      },
      {
        key: "last_modified",
        header: "Last Modified",
        render: (row) => formatDate(raw(row).last_modified),
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
      getRowStyle={(row) => (isAutorunKey(row) ? AUTORUN_ROW_STYLE : undefined)}
      actions={(row) => renderArtefactActions(row, handlers)}
    />
  );
}
