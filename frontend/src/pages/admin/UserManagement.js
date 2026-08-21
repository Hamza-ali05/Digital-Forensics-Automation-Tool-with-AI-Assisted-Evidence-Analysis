import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Badge,
  Button,
  Card,
  Container,
  Form,
  Modal,
  Spinner,
} from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faEye,
  faPlus,
  faUserSlash,
} from "@fortawesome/free-solid-svg-icons";

import PageHeader from "components/common/PageHeader";
import DataTable from "components/common/DataTable";
import ApiErrorDisplay from "components/common/ApiErrorDisplay";
import ConfirmDialog from "components/common/ConfirmDialog";
import PasswordStrength from "pages/auth/PasswordStrength";
import { formatDate } from "utils/formatters";
import {
  validateEmail,
  validatePassword,
  validateRequired,
} from "utils/validators";
import useAuth from "hooks/useAuth";
import useNotification from "hooks/useNotification";
import useConfirmDialog from "hooks/useConfirmDialog";
import usersService from "services/users.service";

function userStatus(user) {
  if (user?.is_locked || user?.locked_until) return "locked";
  if (user?.is_active === false) return "locked";
  return "active";
}

const ROLE_COLOURS = {
  admin: "danger",
  investigator: "primary",
  analyst: "info",
  viewer: "secondary",
};

/**
 * Admin user management — list, register, deactivate.
 */
export default function UserManagement() {
  const { register } = useAuth();
  const { success, error: notifyError } = useNotification();
  const { dialogProps, openDialog } = useConfirmDialog();

  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [page, setPage] = useState(1);
  const [busyId, setBusyId] = useState(null);
  const [detailUser, setDetailUser] = useState(null);
  const [showRegister, setShowRegister] = useState(false);
  const pageSize = 20;

  const [form, setForm] = useState({
    username: "",
    email: "",
    full_name: "",
    password: "",
    confirmPassword: "",
    role_name: "analyst",
  });
  const [fieldErrors, setFieldErrors] = useState({});
  const [formError, setFormError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const loadUsers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await usersService.list();
      setUsers(Array.isArray(list) ? list : list?.users || []);
    } catch (err) {
      setError(err);
      setUsers([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadUsers().catch(() => {});
  }, [loadUsers]);

  const paged = useMemo(() => {
    const start = (Math.max(1, page) - 1) * pageSize;
    return users.slice(start, start + pageSize).map((user) => ({
      ...user,
      id: user.id || user.user_id,
    }));
  }, [users, page]);

  const setField = (key, value) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const resetForm = () => {
    setForm({
      username: "",
      email: "",
      full_name: "",
      password: "",
      confirmPassword: "",
      role_name: "analyst",
    });
    setFieldErrors({});
    setFormError(null);
  };

  const validateRegister = () => {
    const next = {};
    const usernameErr = validateRequired(form.username, "Username");
    const emailRequired = validateRequired(form.email, "Email");
    const nameErr = validateRequired(form.full_name, "Full name");
    const passwordCheck = validatePassword(form.password);

    if (usernameErr) next.username = usernameErr;
    else if (form.username.trim().length < 3) {
      next.username = "Username must be at least 3 characters";
    }
    if (emailRequired) next.email = emailRequired;
    else if (!validateEmail(form.email)) next.email = "Enter a valid email";
    if (nameErr) next.full_name = nameErr;
    if (!passwordCheck.isValid) next.password = passwordCheck.errors[0];
    if (form.password !== form.confirmPassword) {
      next.confirmPassword = "Passwords do not match";
    }
    if (!["admin", "investigator", "analyst", "viewer"].includes(form.role_name)) {
      next.role_name = "Select a role";
    }
    setFieldErrors(next);
    return Object.keys(next).length === 0;
  };

  const handleRegister = async (event) => {
    event.preventDefault();
    setFormError(null);
    if (!validateRegister()) return;
    setSubmitting(true);
    try {
      await register({
        username: form.username.trim(),
        email: form.email.trim(),
        full_name: form.full_name.trim(),
        password: form.password,
        role_name: form.role_name,
      });
      success("User registered", `${form.username.trim()} can now sign in.`);
      setShowRegister(false);
      resetForm();
      await loadUsers();
    } catch (err) {
      setFormError(err?.message || "Registration failed");
      notifyError("Registration failed", err?.message || "Unexpected error");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeactivate = async (user) => {
    try {
      await openDialog({
        title: "Deactivate user?",
        message: `Deactivate ${user.username}? They will no longer be able to sign in.`,
        confirmLabel: "Deactivate",
        variant: "danger",
      });
    } catch {
      return;
    }
    setBusyId(user.id);
    try {
      await usersService.deactivate(user.id);
      success("User deactivated", `${user.username} is now inactive.`);
      await loadUsers();
    } catch (err) {
      notifyError("Deactivate failed", err?.message || "Could not deactivate user.");
    } finally {
      setBusyId(null);
    }
  };

  const columns = useMemo(
    () => [
      {
        key: "username",
        header: "Username",
        sortable: true,
        render: (row) => <span className="fw-bold">{row.username}</span>,
      },
      { key: "email", header: "Email", accessor: "email" },
      { key: "full_name", header: "Full Name", accessor: "full_name" },
      {
        key: "role",
        header: "Role",
        render: (row) => (
          <Badge bg={ROLE_COLOURS[row.role_name] || "secondary"}>
            {row.role_name || "—"}
          </Badge>
        ),
      },
      {
        key: "status",
        header: "Status",
        render: (row) => {
          const status = userStatus(row);
          return (
            <Badge bg={status === "active" ? "success" : "secondary"}>
              {status === "active" ? "Active" : "Locked"}
            </Badge>
          );
        },
      },
      {
        key: "last_login",
        header: "Last Login",
        render: (row) => formatDate(row.last_login) || "—",
      },
    ],
    []
  );

  const renderActions = (row) => {
    const busy = busyId === row.id;
    const active = userStatus(row) === "active";
    return (
      <div className="d-flex justify-content-end flex-wrap gap-1">
        <Button
          size="sm"
          variant="outline-primary"
          onClick={() => setDetailUser(row)}
        >
          <FontAwesomeIcon icon={faEye} className="me-1" />
          View
        </Button>
        {active ? (
          <Button
            size="sm"
            variant="outline-danger"
            disabled={busy}
            onClick={() => handleDeactivate(row)}
          >
            {busy ? (
              <Spinner animation="border" size="sm" className="me-1" />
            ) : (
              <FontAwesomeIcon icon={faUserSlash} className="me-1" />
            )}
            Deactivate
          </Button>
        ) : null}
      </div>
    );
  };

  return (
    <Container fluid className="px-0">
      <PageHeader
        title="User Management"
        subtitle="Register and deactivate investigator accounts"
        actions={
          <Button
            variant="primary"
            onClick={() => {
              resetForm();
              setShowRegister(true);
            }}
          >
            <FontAwesomeIcon icon={faPlus} className="me-2" />
            Register User
          </Button>
        }
      />

      {error ? (
        <ApiErrorDisplay error={error} onRetry={loadUsers} className="mb-3" />
      ) : null}

      <Card border="light" className="shadow-sm">
        <Card.Body className="pt-0">
          <DataTable
            columns={columns}
            data={paged}
            loading={loading}
            emptyMessage="No users found"
            sortable
            actions={renderActions}
            pagination={{ page, pageSize, total: users.length }}
            onPageChange={setPage}
          />
        </Card.Body>
      </Card>

      <Modal
        show={showRegister}
        onHide={() => !submitting && setShowRegister(false)}
        centered
      >
        <Form onSubmit={handleRegister}>
          <Modal.Header closeButton>
            <Modal.Title>Register User</Modal.Title>
          </Modal.Header>
          <Modal.Body>
            {formError ? <ApiErrorDisplay error={formError} className="mb-3" /> : null}
            <Form.Group className="mb-3">
              <Form.Label>Username</Form.Label>
              <Form.Control
                value={form.username}
                onChange={(e) => setField("username", e.target.value)}
                isInvalid={Boolean(fieldErrors.username)}
              />
              <Form.Control.Feedback type="invalid">
                {fieldErrors.username}
              </Form.Control.Feedback>
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Email</Form.Label>
              <Form.Control
                type="email"
                value={form.email}
                onChange={(e) => setField("email", e.target.value)}
                isInvalid={Boolean(fieldErrors.email)}
              />
              <Form.Control.Feedback type="invalid">
                {fieldErrors.email}
              </Form.Control.Feedback>
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Full name</Form.Label>
              <Form.Control
                value={form.full_name}
                onChange={(e) => setField("full_name", e.target.value)}
                isInvalid={Boolean(fieldErrors.full_name)}
              />
              <Form.Control.Feedback type="invalid">
                {fieldErrors.full_name}
              </Form.Control.Feedback>
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Role</Form.Label>
              <Form.Select
                value={form.role_name}
                onChange={(e) => setField("role_name", e.target.value)}
                isInvalid={Boolean(fieldErrors.role_name)}
              >
                <option value="investigator">Investigator</option>
                <option value="analyst">Analyst</option>
                <option value="viewer">Viewer</option>
                <option value="admin">Admin</option>
              </Form.Select>
              <Form.Control.Feedback type="invalid">
                {fieldErrors.role_name}
              </Form.Control.Feedback>
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Password</Form.Label>
              <Form.Control
                type="password"
                value={form.password}
                onChange={(e) => setField("password", e.target.value)}
                isInvalid={Boolean(fieldErrors.password)}
              />
              <Form.Control.Feedback type="invalid">
                {fieldErrors.password}
              </Form.Control.Feedback>
              <PasswordStrength password={form.password} />
            </Form.Group>
            <Form.Group className="mb-0">
              <Form.Label>Confirm password</Form.Label>
              <Form.Control
                type="password"
                value={form.confirmPassword}
                onChange={(e) => setField("confirmPassword", e.target.value)}
                isInvalid={Boolean(fieldErrors.confirmPassword)}
              />
              <Form.Control.Feedback type="invalid">
                {fieldErrors.confirmPassword}
              </Form.Control.Feedback>
            </Form.Group>
          </Modal.Body>
          <Modal.Footer>
            <Button
              variant="link"
              disabled={submitting}
              onClick={() => setShowRegister(false)}
            >
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={submitting}>
              {submitting ? (
                <Spinner animation="border" size="sm" className="me-2" />
              ) : null}
              Register
            </Button>
          </Modal.Footer>
        </Form>
      </Modal>

      <Modal show={Boolean(detailUser)} onHide={() => setDetailUser(null)} centered>
        <Modal.Header closeButton>
          <Modal.Title>User detail</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {detailUser ? (
            <dl className="row mb-0 small">
              <dt className="col-4 text-muted">ID</dt>
              <dd className="col-8">
                <code>{detailUser.id}</code>
              </dd>
              <dt className="col-4 text-muted">Username</dt>
              <dd className="col-8">{detailUser.username}</dd>
              <dt className="col-4 text-muted">Email</dt>
              <dd className="col-8">{detailUser.email}</dd>
              <dt className="col-4 text-muted">Full name</dt>
              <dd className="col-8">{detailUser.full_name}</dd>
              <dt className="col-4 text-muted">Role</dt>
              <dd className="col-8">{detailUser.role_name}</dd>
              <dt className="col-4 text-muted">Status</dt>
              <dd className="col-8">{userStatus(detailUser)}</dd>
              <dt className="col-4 text-muted">Last login</dt>
              <dd className="col-8">{formatDate(detailUser.last_login) || "—"}</dd>
              <dt className="col-4 text-muted">Created</dt>
              <dd className="col-8">{formatDate(detailUser.created_at) || "—"}</dd>
            </dl>
          ) : null}
        </Modal.Body>
      </Modal>

      <ConfirmDialog {...dialogProps} />
    </Container>
  );
}
