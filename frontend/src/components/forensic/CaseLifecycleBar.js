import React from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faCheck, faCircle } from "@fortawesome/free-solid-svg-icons";

import { CASE_STATUS } from "utils/constants";

const STEPS = [
  { key: CASE_STATUS.CREATED, label: "Created" },
  { key: CASE_STATUS.OPEN, label: "Open" },
  { key: CASE_STATUS.ACTIVE, label: "Active" },
  { key: CASE_STATUS.UNDER_REVIEW, label: "Under Review" },
  { key: CASE_STATUS.CLOSED, label: "Closed" },
  { key: CASE_STATUS.ARCHIVED, label: "Archived" },
];

/**
 * Horizontal visual stepper for case lifecycle progression.
 *
 * @param {{ status?: string, className?: string }} props
 */
export default function CaseLifecycleBar({ status, className = "" }) {
  const current = String(status || CASE_STATUS.CREATED).toLowerCase();
  let currentIndex = STEPS.findIndex((step) => step.key === current);
  if (currentIndex < 0) currentIndex = 0;

  return (
    <div className={`dfat-case-lifecycle ${className}`.trim()}>
      <div className="d-flex align-items-center justify-content-between flex-wrap">
        {STEPS.map((step, index) => {
          const completed = index < currentIndex;
          const active = index === currentIndex;

          let circleStyle = {
            width: 32,
            height: 32,
            borderRadius: "50%",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 12,
            border: "2px solid #adb5bd",
            backgroundColor: "#fff",
            color: "#6c757d",
          };

          if (completed) {
            circleStyle = {
              ...circleStyle,
              borderColor: "#198754",
              backgroundColor: "#198754",
              color: "#fff",
            };
          } else if (active) {
            circleStyle = {
              ...circleStyle,
              borderColor: "#0d6efd",
              backgroundColor: "#0d6efd",
              color: "#fff",
              boxShadow: "0 0 0 4px rgba(13,110,253,0.2)",
            };
          }

          return (
            <React.Fragment key={step.key}>
              <div className="text-center px-1 mb-2" style={{ minWidth: 72 }}>
                <div className="mx-auto mb-1" style={circleStyle}>
                  {completed ? (
                    <FontAwesomeIcon icon={faCheck} />
                  ) : active ? (
                    <FontAwesomeIcon icon={faCircle} style={{ fontSize: 8 }} />
                  ) : (
                    <span>{index + 1}</span>
                  )}
                </div>
                <div
                  className={`small ${
                    active
                      ? "fw-bold text-primary"
                      : completed
                        ? "text-success"
                        : "text-muted"
                  }`}
                >
                  {step.label}
                </div>
              </div>
              {index < STEPS.length - 1 ? (
                <div
                  className="flex-grow-1 mb-4 d-none d-md-block"
                  style={{
                    height: 3,
                    minWidth: 12,
                    backgroundColor: completed || active ? "#198754" : "#dee2e6",
                    borderRadius: 2,
                  }}
                  aria-hidden="true"
                />
              ) : null}
            </React.Fragment>
          );
        })}
      </div>
      {pendingNote(current)}
    </div>
  );
}

function pendingNote(current) {
  if (current === CASE_STATUS.ARCHIVED) {
    return (
      <p className="small text-muted mb-0 mt-1">
        Case is archived — lifecycle is complete.
      </p>
    );
  }
  return null;
}
