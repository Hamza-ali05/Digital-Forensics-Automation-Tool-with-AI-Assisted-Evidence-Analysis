import React from "react";

import EmptyState from "components/common/EmptyState";

/**
 * Vertical timeline for status history and custody chain entries.
 *
 * @param {{
 *   entries?: Array,
 *   renderEntry: (entry: object, index: number, isCurrent: boolean) => React.ReactNode,
 *   emptyTitle?: string,
 *   emptyDescription?: string,
 *   className?: string,
 * }} props
 */
export default function StatusTimeline({
  entries = [],
  renderEntry,
  emptyTitle = "No history yet",
  emptyDescription = "Timeline entries will appear here.",
  className = "",
}) {
  const items = Array.isArray(entries) ? entries : [];

  if (!items.length) {
    return (
      <EmptyState title={emptyTitle} description={emptyDescription} />
    );
  }

  return (
    <div className={`dfat-status-timeline ${className}`.trim()}>
      <ul className="list-unstyled mb-0 position-relative">
        {items.map((entry, index) => {
          const isCurrent = index === 0;
          const isLast = index === items.length - 1;
          return (
            <li
              key={entry.id || entry.record_id || entry.entry_number || index}
              className="d-flex position-relative pb-4"
            >
              <div
                className="d-flex flex-column align-items-center me-3"
                style={{ width: 24 }}
              >
                <span
                  className="rounded-circle flex-shrink-0"
                  style={{
                    width: 14,
                    height: 14,
                    marginTop: 4,
                    backgroundColor: isCurrent ? "#0d6efd" : "#198754",
                    boxShadow: isCurrent
                      ? "0 0 0 4px rgba(13,110,253,0.2)"
                      : "none",
                    border: "2px solid #fff",
                  }}
                  aria-hidden="true"
                />
                {!isLast ? (
                  <span
                    className="flex-grow-1"
                    style={{
                      width: 2,
                      minHeight: 28,
                      backgroundColor: "#dee2e6",
                      marginTop: 4,
                    }}
                    aria-hidden="true"
                  />
                ) : null}
              </div>
              <div className="flex-grow-1" style={{ minWidth: 0 }}>
                {typeof renderEntry === "function"
                  ? renderEntry(entry, index, isCurrent)
                  : null}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
