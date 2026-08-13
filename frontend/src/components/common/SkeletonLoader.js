import React from "react";

/**
 * Animated content placeholders for loading states.
 *
 * @param {{ type?: "table"|"card"|"detail"|"text", rows?: number, className?: string }} props
 */
export default function SkeletonLoader({
  type = "text",
  rows = 3,
  className = "",
}) {
  const count = Math.max(1, Number(rows) || 1);

  if (type === "table") {
    return (
      <div className={`dfat-skeleton dfat-skeleton-table ${className}`.trim()}>
        <div className="dfat-skeleton-line dfat-skeleton-line-lg mb-3" />
        {Array.from({ length: count }).map((_, index) => (
          <div key={index} className="d-flex gap-2 mb-2">
            <div className="dfat-skeleton-line flex-grow-1" />
            <div className="dfat-skeleton-line" style={{ width: "20%" }} />
            <div className="dfat-skeleton-line" style={{ width: "15%" }} />
          </div>
        ))}
      </div>
    );
  }

  if (type === "card") {
    return (
      <div className={`dfat-skeleton dfat-skeleton-card ${className}`.trim()}>
        {Array.from({ length: count }).map((_, index) => (
          <div key={index} className="dfat-skeleton-card-item mb-3 p-3 border rounded">
            <div className="dfat-skeleton-line dfat-skeleton-line-lg mb-2" style={{ width: "40%" }} />
            <div className="dfat-skeleton-line mb-2" />
            <div className="dfat-skeleton-line" style={{ width: "70%" }} />
          </div>
        ))}
      </div>
    );
  }

  if (type === "detail") {
    return (
      <div className={`dfat-skeleton dfat-skeleton-detail ${className}`.trim()}>
        <div className="dfat-skeleton-line dfat-skeleton-line-lg mb-3" style={{ width: "45%" }} />
        <div className="dfat-skeleton-line mb-2" style={{ width: "30%" }} />
        {Array.from({ length: count }).map((_, index) => (
          <div key={index} className="mb-3">
            <div className="dfat-skeleton-line mb-2" style={{ width: "25%" }} />
            <div className="dfat-skeleton-line" />
          </div>
        ))}
      </div>
    );
  }

  // type === "text"
  return (
    <div className={`dfat-skeleton dfat-skeleton-text ${className}`.trim()}>
      {Array.from({ length: count }).map((_, index) => (
        <div
          key={index}
          className="dfat-skeleton-line mb-2"
          style={{ width: index === count - 1 ? "60%" : "100%" }}
        />
      ))}
    </div>
  );
}
