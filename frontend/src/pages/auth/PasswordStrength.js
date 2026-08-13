import React from "react";
import { ProgressBar } from "@themesberg/react-bootstrap";

import { validatePassword } from "utils/validators";

const CHECKS = [
  { id: "length", label: "At least 12 characters", test: (p) => p.length >= 12 },
  { id: "upper", label: "One uppercase letter", test: (p) => /[A-Z]/.test(p) },
  { id: "lower", label: "One lowercase letter", test: (p) => /[a-z]/.test(p) },
  { id: "digit", label: "One digit", test: (p) => /\d/.test(p) },
  { id: "special", label: "One special character", test: (p) => /[^A-Za-z0-9]/.test(p) },
];

/**
 * Real-time password strength meter + requirements checklist.
 */
export default function PasswordStrength({ password = "" }) {
  const result = validatePassword(password);
  const passed = CHECKS.filter((c) => c.test(password)).length;
  const percent = Math.round((passed / CHECKS.length) * 100);
  const variant =
    percent === 100 ? "success" : percent >= 60 ? "warning" : "danger";

  return (
    <div className="mt-2 mb-3">
      <div className="d-flex justify-content-between small mb-1">
        <span className="text-muted">Password strength</span>
        <span className={`text-${variant}`}>
          {percent === 100 ? "Strong" : percent >= 60 ? "Fair" : "Weak"}
        </span>
      </div>
      <ProgressBar now={percent} variant={variant} className="mb-2" style={{ height: 6 }} />
      <ul className="list-unstyled small mb-0">
        {CHECKS.map((check) => {
          const ok = check.test(password);
          return (
            <li key={check.id} className={ok ? "text-success" : "text-muted"}>
              {ok ? "✓" : "○"} {check.label}
            </li>
          );
        })}
      </ul>
      {!result.isValid && password.length > 0 ? (
        <p className="small text-danger mb-0 mt-2">{result.errors[0]}</p>
      ) : null}
    </div>
  );
}
