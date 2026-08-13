import React, { useMemo } from "react";
import { OverlayTrigger, Tooltip } from "@themesberg/react-bootstrap";

import DataTable from "components/common/DataTable";
import { formatDate } from "utils/formatters";
import {
  raw,
  renderArtefactActions,
  suspicionScoreColumns,
  truncateText,
} from "components/forensic/tables/tableHelpers";

function safeHref(url) {
  if (!url) return null;
  const text = String(url).trim();
  if (!/^https?:\/\//i.test(text)) return null;
  return text;
}

/**
 * Browser history artefact table with truncated, clickable URLs.
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
export default function BrowserHistoryTable({
  data = [],
  loading = false,
  emptyMessage = "No browser history artefacts found",
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
        key: "url",
        header: "URL",
        render: (row) => {
          const url = raw(row).url || "";
          const href = safeHref(url);
          const truncated = truncateText(url || "—", 64);
          const tip = (
            <Tooltip id={`url-${row.artefact_id || "x"}`}>
              {url || "—"}
            </Tooltip>
          );
          const content = href ? (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="small text-break"
            >
              {truncated}
            </a>
          ) : (
            <span className="small text-break">{truncated}</span>
          );
          return (
            <OverlayTrigger placement="top" overlay={tip}>
              <span>{content}</span>
            </OverlayTrigger>
          );
        },
      },
      {
        key: "title",
        header: "Title",
        render: (row) => (
          <span className="small" title={raw(row).title || ""}>
            {truncateText(raw(row).title, 48)}
          </span>
        ),
      },
      {
        key: "browser",
        header: "Browser",
        render: (row) => {
          const browser = raw(row).browser_type || raw(row).browser || "—";
          return String(browser)
            .replace(/_/g, " ")
            .replace(/\b\w/g, (c) => c.toUpperCase());
        },
      },
      {
        key: "visit_count",
        header: "Visit Count",
        render: (row) => {
          const count = raw(row).visit_count;
          return count == null ? "—" : Number(count);
        },
      },
      {
        key: "last_visit",
        header: "Last Visit",
        render: (row) =>
          formatDate(raw(row).last_visit_time || raw(row).last_visit),
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
      actions={(row) => renderArtefactActions(row, handlers)}
    />
  );
}
