import React, { useMemo, useState } from "react";
import {
  Button,
  Form,
  Pagination,
  Spinner,
  Table,
} from "@themesberg/react-bootstrap";

import EmptyState from "components/common/EmptyState";

function getRowKey(row, index) {
  return (
    row?.artefact_id ??
    row?.id ??
    row?.uuid ??
    row?.key ??
    index
  );
}

function cellValue(row, column) {
  if (typeof column.render === "function") {
    return column.render(row);
  }
  if (column.accessor) {
    return row?.[column.accessor];
  }
  return row?.[column.key];
}

/**
 * Forensic data table with loading, empty, sort, pagination, and selection.
 */
export default function DataTable({
  columns = [],
  data = [],
  loading = false,
  emptyMessage = "No records found",
  sortable = false,
  onSort,
  pagination,
  onPageChange,
  selectable = false,
  onSelect,
  actions,
  getRowClassName,
  getRowStyle,
}) {
  const [sortKey, setSortKey] = useState(null);
  const [sortDir, setSortDir] = useState("asc");
  const [selected, setSelected] = useState(() => new Set());

  const rows = Array.isArray(data) ? data : [];

  const allSelected =
    rows.length > 0 && rows.every((row, i) => selected.has(getRowKey(row, i)));

  const toggleAll = () => {
    if (allSelected) {
      setSelected(new Set());
      if (onSelect) onSelect([]);
      return;
    }
    const next = new Set(rows.map((row, i) => getRowKey(row, i)));
    setSelected(next);
    if (onSelect) onSelect([...rows]);
  };

  const toggleRow = (row, index) => {
    const key = getRowKey(row, index);
    const next = new Set(selected);
    if (next.has(key)) {
      next.delete(key);
    } else {
      next.add(key);
    }
    setSelected(next);
    if (onSelect) {
      onSelect(rows.filter((r, i) => next.has(getRowKey(r, i))));
    }
  };

  const handleSort = (column) => {
    if (!sortable && !column.sortable) return;
    const key = column.key || column.accessor;
    if (!key) return;

    const nextDir = sortKey === key && sortDir === "asc" ? "desc" : "asc";
    setSortKey(key);
    setSortDir(nextDir);
    if (onSort) {
      onSort({ key, direction: nextDir, column });
    }
  };

  const pageInfo = useMemo(() => {
    if (!pagination) return null;
    const page = pagination.page || 1;
    const pageSize = pagination.pageSize || pagination.perPage || 10;
    const total = pagination.total || 0;
    const totalPages = Math.max(1, Math.ceil(total / pageSize) || 1);
    return { page, pageSize, total, totalPages };
  }, [pagination]);

  const colSpan =
    columns.length + (selectable ? 1 : 0) + (actions ? 1 : 0) || 1;

  return (
    <div className="dfat-data-table">
      <Table responsive hover className="align-items-center table-flush">
        <thead className="thead-light">
          <tr>
            {selectable ? (
              <th style={{ width: 40 }}>
                <Form.Check
                  type="checkbox"
                  checked={allSelected}
                  onChange={toggleAll}
                  aria-label="Select all rows"
                />
              </th>
            ) : null}
            {columns.map((column) => {
              const key = column.key || column.accessor || column.header;
              const canSort = sortable || column.sortable;
              return (
                <th
                  key={key}
                  style={canSort ? { cursor: "pointer", userSelect: "none" } : undefined}
                  onClick={() => canSort && handleSort(column)}
                >
                  {column.header || column.label || key}
                  {canSort && sortKey === (column.key || column.accessor) ? (
                    <span className="ms-1">{sortDir === "asc" ? "▲" : "▼"}</span>
                  ) : null}
                </th>
              );
            })}
            {actions ? <th className="text-end">Actions</th> : null}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            Array.from({ length: 5 }).map((_, index) => (
              <tr key={`skeleton-${index}`}>
                <td colSpan={colSpan}>
                  <div className="d-flex align-items-center text-muted py-2">
                    <Spinner animation="border" size="sm" className="me-2" />
                    Loading…
                  </div>
                </td>
              </tr>
            ))
          ) : rows.length === 0 ? (
            <tr>
              <td colSpan={colSpan} className="p-0 border-0">
                <EmptyState title={emptyMessage} description="" />
              </td>
            </tr>
          ) : (
            rows.map((row, index) => {
              const key = getRowKey(row, index);
              const className =
                typeof getRowClassName === "function"
                  ? getRowClassName(row, index)
                  : undefined;
              const style =
                typeof getRowStyle === "function"
                  ? getRowStyle(row, index)
                  : undefined;
              return (
                <tr key={key} className={className} style={style}>
                  {selectable ? (
                    <td>
                      <Form.Check
                        type="checkbox"
                        checked={selected.has(key)}
                        onChange={() => toggleRow(row, index)}
                        aria-label={`Select row ${index + 1}`}
                      />
                    </td>
                  ) : null}
                  {columns.map((column) => {
                    const colKey = column.key || column.accessor || column.header;
                    return <td key={colKey}>{cellValue(row, column)}</td>;
                  })}
                  {actions ? (
                    <td className="text-end">{actions(row, index)}</td>
                  ) : null}
                </tr>
              );
            })
          )}
        </tbody>
      </Table>

      {pageInfo && pageInfo.totalPages > 1 ? (
        <div className="d-flex justify-content-between align-items-center px-2 pb-2">
          <span className="small text-muted">
            Page {pageInfo.page} of {pageInfo.totalPages} ({pageInfo.total}{" "}
            total)
          </span>
          <Pagination className="mb-0">
            <Pagination.Prev
              disabled={pageInfo.page <= 1}
              onClick={() =>
                onPageChange && onPageChange(pageInfo.page - 1, pageInfo)
              }
            />
            <Pagination.Item active>{pageInfo.page}</Pagination.Item>
            <Pagination.Next
              disabled={pageInfo.page >= pageInfo.totalPages}
              onClick={() =>
                onPageChange && onPageChange(pageInfo.page + 1, pageInfo)
              }
            />
          </Pagination>
        </div>
      ) : null}

      {pageInfo && !loading && rows.length > 0 && pageInfo.totalPages <= 1 ? (
        <div className="px-2 pb-2">
          <Button variant="link" size="sm" className="text-muted p-0" disabled>
            {pageInfo.total} record{pageInfo.total === 1 ? "" : "s"}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
