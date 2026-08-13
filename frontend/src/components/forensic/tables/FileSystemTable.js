import React, { useMemo } from "react";

import DataTable from "components/common/DataTable";
import { formatBytes, formatDate } from "utils/formatters";
import {
  DeletedBadge,
  raw,
  renderArtefactActions,
  suspicionScoreColumns,
} from "components/forensic/tables/tableHelpers";

const DELETED_ROW_STYLE = { backgroundColor: "#f8d7da" };

function isDeleted(row) {
  const data = raw(row);
  return (
    data.is_deleted === true ||
    String(row?.metadata?.sub_category || "").toLowerCase() === "deleted_file"
  );
}

/**
 * File-system metadata artefact table with deleted-file highlighting.
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
export default function FileSystemTable({
  data = [],
  loading = false,
  emptyMessage = "No file system artefacts found",
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
        key: "path",
        header: "Path",
        render: (row) => {
          const path = raw(row).path || row.source_path || "—";
          return (
            <code className="small text-break" title={path}>
              {path}
            </code>
          );
        },
      },
      {
        key: "filename",
        header: "Filename",
        render: (row) => raw(row).filename || "—",
      },
      {
        key: "size",
        header: "Size",
        render: (row) => {
          const size = raw(row).size;
          return size == null || size === "" ? "—" : formatBytes(size);
        },
      },
      {
        key: "created",
        header: "Created",
        render: (row) =>
          formatDate(raw(row).created_time || raw(row).created),
      },
      {
        key: "modified",
        header: "Modified",
        render: (row) =>
          formatDate(raw(row).modified_time || raw(row).modified),
      },
      {
        key: "accessed",
        header: "Accessed",
        render: (row) =>
          formatDate(raw(row).accessed_time || raw(row).accessed),
      },
      {
        key: "file_type",
        header: "Type",
        render: (row) => {
          const type = String(raw(row).file_type || "").toLowerCase();
          if (type === "directory" || type === "dir") return "directory";
          if (type === "file") return "file";
          if (type) return type;
          return "—";
        },
      },
      {
        key: "is_deleted",
        header: "Is Deleted",
        render: (row) => <DeletedBadge deleted={isDeleted(row)} />,
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
      getRowStyle={(row) => (isDeleted(row) ? DELETED_ROW_STYLE : undefined)}
      actions={(row) => renderArtefactActions(row, handlers)}
    />
  );
}
