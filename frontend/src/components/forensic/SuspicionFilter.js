import React from "react";
import { Form } from "@themesberg/react-bootstrap";

import { SUSPICION_LEVEL, SUSPICION_COLOURS } from "utils/constants";
import { formatSuspicionLevel } from "utils/formatters";

const LEVEL_ORDER = [
  SUSPICION_LEVEL.CRITICAL,
  SUSPICION_LEVEL.HIGH,
  SUSPICION_LEVEL.MEDIUM,
  SUSPICION_LEVEL.LOW,
  SUSPICION_LEVEL.INFORMATIONAL,
];

/**
 * Multi-select filter for suspicion levels with coloured checkbox indicators.
 *
 * @param {{
 *   value?: string[],
 *   onChange?: (levels: string[]) => void,
 *   className?: string,
 * }} props
 */
export default function SuspicionFilter({
  value = [],
  onChange,
  className = "",
}) {
  const selected = new Set((value || []).map((item) => String(item).toLowerCase()));

  const toggle = (level) => {
    const key = String(level).toLowerCase();
    const next = new Set(selected);
    if (next.has(key)) {
      next.delete(key);
    } else {
      next.add(key);
    }
    if (typeof onChange === "function") {
      onChange(Array.from(next));
    }
  };

  return (
    <div className={className}>
      <Form.Label className="small text-muted text-uppercase fw-bold mb-2">
        Suspicion level
      </Form.Label>
      <div className="d-flex flex-wrap gap-3">
        {LEVEL_ORDER.map((level) => {
          const { label, colour } = formatSuspicionLevel(level);
          const checked = selected.has(level);
          return (
            <Form.Check
              key={level}
              type="checkbox"
              id={`suspicion-filter-${level}`}
              label={
                <span className="d-inline-flex align-items-center gap-2">
                  <span
                    aria-hidden
                    style={{
                      width: 12,
                      height: 12,
                      borderRadius: 2,
                      backgroundColor: colour,
                      border: `1px solid ${colour}`,
                      flexShrink: 0,
                    }}
                  />
                  {label}
                </span>
              }
              checked={checked}
              onChange={() => toggle(level)}
            />
          );
        })}
      </div>
    </div>
  );
}

export { LEVEL_ORDER as SUSPICION_LEVEL_ORDER, SUSPICION_COLOURS };
