import React, { useEffect, useMemo, useState } from "react";
import { useHistory } from "react-router-dom";
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Form,
  Row,
  Spinner,
} from "@themesberg/react-bootstrap";

import PageHeader from "components/common/PageHeader";
import SkeletonLoader from "components/common/SkeletonLoader";
import ApiErrorDisplay from "components/common/ApiErrorDisplay";
import ConfirmDialog from "components/common/ConfirmDialog";
import { AUTH_CONFIG } from "config/auth.config";
import useAuth from "hooks/useAuth";
import useApi from "hooks/useApi";
import useConfirmDialog from "hooks/useConfirmDialog";
import useNotification from "hooks/useNotification";
import authService from "services/auth.service";
import usersService from "services/users.service";
import { formatDate } from "utils/formatters";
import { validatePassword, validateRequired } from "utils/validators";
import { Routes } from "routes";
import PasswordStrength from "pages/auth/PasswordStrength";

function useCountdown(targetMs) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!targetMs) return undefined;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [targetMs]);

  if (!targetMs) return "—";
  const remaining = Math.max(0, targetMs - now);
  const totalSec = Math.floor(remaining / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  if (remaining <= 0) return "Expired";
  if (h > 0) return `${h}h ${m}m ${s}s`;
  return `${m}m ${s}s`;
}

/**
 * Authenticated user profile, password change, and session controls.
 */
export default function Profile() {
  const history = useHistory();
  const { user: authUser, logoutAll, refreshUser } = useAuth();
  const { success, error: notifyError } = useNotification();
  const { dialogProps, openDialog } = useConfirmDialog();

  const { data: profile, loading, error, execute } = useApi(usersService.getMe);

  const [pwd, setPwd] = useState({
    current: "",
    next: "",
    confirm: "",
  });
  const [pwdError, setPwdError] = useState(null);
  const [pwdSubmitting, setPwdSubmitting] = useState(false);
  const [fieldErrors, setFieldErrors] = useState({});

  useEffect(() => {
    execute().catch(() => {});
  }, [execute]);

  const displayUser = profile || authUser;

  const sessionStart = useMemo(() => {
    const raw = localStorage.getItem(AUTH_CONFIG.sessionStartKey);
    return raw ? Number(raw) : null;
  }, []);

  const tokenExpiry = useMemo(() => {
    const raw = localStorage.getItem(AUTH_CONFIG.tokenExpiryKey);
    return raw ? Number(raw) : null;
  }, []);

  const expiryCountdown = useCountdown(tokenExpiry);

  const validatePasswordForm = () => {
    const next = {};
    const currentErr = validateRequired(pwd.current, "Current password");
    const strength = validatePassword(pwd.next);
    if (currentErr) next.current = currentErr;
    if (!strength.isValid) next.next = strength.errors[0];
    if (pwd.next !== pwd.confirm) next.confirm = "Passwords do not match";
    setFieldErrors(next);
    return Object.keys(next).length === 0;
  };

  const handleChangePassword = async (event) => {
    event.preventDefault();
    setPwdError(null);
    if (!validatePasswordForm()) return;

    setPwdSubmitting(true);
    try {
      await authService.changePassword(pwd.current, pwd.next);
      setPwd({ current: "", next: "", confirm: "" });
      success("Password updated", "Your password has been changed.");
      await refreshUser().catch(() => {});
    } catch (err) {
      setPwdError(err?.message || "Password change failed");
      notifyError("Password change failed", err?.message || "Unexpected error");
    } finally {
      setPwdSubmitting(false);
    }
  };

  const handleLogoutAll = async () => {
    try {
      await openDialog({
        title: "Logout all sessions?",
        message:
          "This will revoke every active session for your account, including this one.",
        confirmLabel: "Logout all",
        variant: "danger",
      });
    } catch {
      return;
    }

    try {
      await logoutAll();
      success("Sessions revoked", "You have been signed out everywhere.");
      history.replace(Routes.Login.path);
    } catch (err) {
      notifyError("Logout all failed", err?.message || "Unexpected error");
    }
  };

  if (loading && !displayUser) {
    return (
      <>
        <PageHeader title="Profile" subtitle="Account and session settings" />
        <SkeletonLoader type="detail" rows={4} />
      </>
    );
  }

  if (error && !displayUser) {
    return (
      <>
        <PageHeader title="Profile" subtitle="Account and session settings" />
        <ApiErrorDisplay error={error} onRetry={() => execute()} />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Profile"
        subtitle="Account details, password, and sessions"
      />

      <Row>
        <Col xs={12} lg={6} className="mb-4">
          <Card border="light" className="shadow-sm">
            <Card.Body>
              <h5 className="mb-3">User information</h5>
              <dl className="row mb-0">
                <dt className="col-sm-4 text-muted">Username</dt>
                <dd className="col-sm-8">{displayUser?.username || "—"}</dd>
                <dt className="col-sm-4 text-muted">Email</dt>
                <dd className="col-sm-8">{displayUser?.email || "—"}</dd>
                <dt className="col-sm-4 text-muted">Full name</dt>
                <dd className="col-sm-8">{displayUser?.full_name || "—"}</dd>
                <dt className="col-sm-4 text-muted">Role</dt>
                <dd className="col-sm-8">
                  <Badge bg="primary" className="text-uppercase">
                    {displayUser?.role_name || "—"}
                  </Badge>
                </dd>
                <dt className="col-sm-4 text-muted">Last login</dt>
                <dd className="col-sm-8">
                  {displayUser?.last_login
                    ? formatDate(displayUser.last_login)
                    : "—"}
                </dd>
              </dl>
            </Card.Body>
          </Card>
        </Col>

        <Col xs={12} lg={6} className="mb-4">
          <Card border="light" className="shadow-sm">
            <Card.Body>
              <h5 className="mb-3">Session</h5>
              <dl className="row mb-3">
                <dt className="col-sm-5 text-muted">Session start</dt>
                <dd className="col-sm-7">
                  {sessionStart ? formatDate(new Date(sessionStart)) : "—"}
                </dd>
                <dt className="col-sm-5 text-muted">Token expires in</dt>
                <dd className="col-sm-7">{expiryCountdown}</dd>
              </dl>
              <Button variant="outline-danger" onClick={handleLogoutAll}>
                Logout all sessions
              </Button>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      <Card border="light" className="shadow-sm mb-4">
        <Card.Body>
          <h5 className="mb-3">Change password</h5>
          {pwdError ? <Alert variant="danger">{pwdError}</Alert> : null}
          <Form onSubmit={handleChangePassword} noValidate style={{ maxWidth: 480 }}>
            <Form.Group className="mb-3">
              <Form.Label>Current password</Form.Label>
              <Form.Control
                type="password"
                value={pwd.current}
                onChange={(e) =>
                  setPwd((prev) => ({ ...prev, current: e.target.value }))
                }
                isInvalid={Boolean(fieldErrors.current)}
                disabled={pwdSubmitting}
                autoComplete="current-password"
              />
              <Form.Control.Feedback type="invalid">
                {fieldErrors.current}
              </Form.Control.Feedback>
            </Form.Group>

            <Form.Group className="mb-2">
              <Form.Label>New password</Form.Label>
              <Form.Control
                type="password"
                value={pwd.next}
                onChange={(e) =>
                  setPwd((prev) => ({ ...prev, next: e.target.value }))
                }
                isInvalid={Boolean(fieldErrors.next)}
                disabled={pwdSubmitting}
                autoComplete="new-password"
              />
              <Form.Control.Feedback type="invalid">
                {fieldErrors.next}
              </Form.Control.Feedback>
            </Form.Group>
            <PasswordStrength password={pwd.next} />

            <Form.Group className="mb-4">
              <Form.Label>Confirm new password</Form.Label>
              <Form.Control
                type="password"
                value={pwd.confirm}
                onChange={(e) =>
                  setPwd((prev) => ({ ...prev, confirm: e.target.value }))
                }
                isInvalid={Boolean(fieldErrors.confirm)}
                disabled={pwdSubmitting}
                autoComplete="new-password"
              />
              <Form.Control.Feedback type="invalid">
                {fieldErrors.confirm}
              </Form.Control.Feedback>
            </Form.Group>

            <Button type="submit" variant="primary" disabled={pwdSubmitting}>
              {pwdSubmitting ? (
                <>
                  <Spinner as="span" animation="border" size="sm" className="me-2" />
                  Updating…
                </>
              ) : (
                "Update password"
              )}
            </Button>
          </Form>
        </Card.Body>
      </Card>

      <ConfirmDialog {...dialogProps} />
    </>
  );
}
