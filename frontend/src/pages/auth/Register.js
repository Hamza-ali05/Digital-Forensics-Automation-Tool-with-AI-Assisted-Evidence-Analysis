import React, { useState } from "react";
import { useHistory } from "react-router-dom";
import {
  Alert,
  Button,
  Col,
  Container,
  Form,
  Row,
  Spinner,
} from "@themesberg/react-bootstrap";

import useAuth from "hooks/useAuth";
import useNotification from "hooks/useNotification";
import {
  validateEmail,
  validatePassword,
  validateRequired,
} from "utils/validators";
import { Routes } from "routes";
import PasswordStrength from "./PasswordStrength";
import BgImage from "../../assets/img/illustrations/signin.svg";

/**
 * Register a new investigator/analyst account (admin & investigator only).
 */
export default function Register() {
  const history = useHistory();
  const { register } = useAuth();
  const { success, error: notifyError } = useNotification();

  const [form, setForm] = useState({
    username: "",
    email: "",
    full_name: "",
    password: "",
    confirmPassword: "",
    role_name: "analyst",
  });
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);
  const [fieldErrors, setFieldErrors] = useState({});

  const setField = (key, value) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const validate = () => {
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

    if (!passwordCheck.isValid) {
      next.password = passwordCheck.errors[0];
    }
    if (form.password !== form.confirmPassword) {
      next.confirmPassword = "Passwords do not match";
    }
    if (!["investigator", "analyst"].includes(form.role_name)) {
      next.role_name = "Select investigator or analyst";
    }

    setFieldErrors(next);
    return Object.keys(next).length === 0;
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setFormError(null);
    if (!validate()) return;

    setSubmitting(true);
    try {
      await register({
        username: form.username.trim(),
        email: form.email.trim(),
        full_name: form.full_name.trim(),
        password: form.password,
        role_name: form.role_name,
      });
      success(
        "Registration successful",
        "The new account can now sign in."
      );
      history.push(Routes.Login.path);
    } catch (err) {
      setFormError(err?.message || "Registration failed");
      notifyError("Registration failed", err?.message || "Unexpected error");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="d-flex align-items-center my-4 mt-lg-5 mb-lg-5">
      <Container>
        <Row
          className="justify-content-center form-bg-image"
          style={{ backgroundImage: `url(${BgImage})` }}
        >
          <Col xs={12} className="d-flex align-items-center justify-content-center">
            <div className="bg-white shadow-soft border rounded border-light p-4 p-lg-5 w-100 fmxw-500">
              <div className="text-center mb-4">
                <h3 className="mb-0">Register user</h3>
                <p className="text-gray mb-0">
                  Create an investigator or analyst account
                </p>
              </div>

              {formError ? (
                <Alert variant="danger" className="mb-3">
                  {formError}
                </Alert>
              ) : null}

              <Form onSubmit={handleSubmit} noValidate>
                <Form.Group className="mb-3">
                  <Form.Label>Username</Form.Label>
                  <Form.Control
                    value={form.username}
                    onChange={(e) => setField("username", e.target.value)}
                    isInvalid={Boolean(fieldErrors.username)}
                    disabled={submitting}
                    autoComplete="username"
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
                    disabled={submitting}
                    autoComplete="email"
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
                    disabled={submitting}
                    autoComplete="name"
                  />
                  <Form.Control.Feedback type="invalid">
                    {fieldErrors.full_name}
                  </Form.Control.Feedback>
                </Form.Group>

                <Form.Group className="mb-3">
                  <Form.Label>Role</Form.Label>
                  <Form.Control
                    as="select"
                    value={form.role_name}
                    onChange={(e) => setField("role_name", e.target.value)}
                    isInvalid={Boolean(fieldErrors.role_name)}
                    disabled={submitting}
                  >
                    <option value="analyst">Analyst</option>
                    <option value="investigator">Investigator</option>
                  </Form.Control>
                  <Form.Control.Feedback type="invalid">
                    {fieldErrors.role_name}
                  </Form.Control.Feedback>
                </Form.Group>

                <Form.Group className="mb-2">
                  <Form.Label>Password</Form.Label>
                  <Form.Control
                    type="password"
                    value={form.password}
                    onChange={(e) => setField("password", e.target.value)}
                    isInvalid={Boolean(fieldErrors.password)}
                    disabled={submitting}
                    autoComplete="new-password"
                  />
                  <Form.Control.Feedback type="invalid">
                    {fieldErrors.password}
                  </Form.Control.Feedback>
                </Form.Group>
                <PasswordStrength password={form.password} />

                <Form.Group className="mb-4">
                  <Form.Label>Confirm password</Form.Label>
                  <Form.Control
                    type="password"
                    value={form.confirmPassword}
                    onChange={(e) => setField("confirmPassword", e.target.value)}
                    isInvalid={Boolean(fieldErrors.confirmPassword)}
                    disabled={submitting}
                    autoComplete="new-password"
                  />
                  <Form.Control.Feedback type="invalid">
                    {fieldErrors.confirmPassword}
                  </Form.Control.Feedback>
                </Form.Group>

                <Button
                  variant="primary"
                  type="submit"
                  className="w-100"
                  disabled={submitting}
                >
                  {submitting ? (
                    <>
                      <Spinner
                        as="span"
                        animation="border"
                        size="sm"
                        className="me-2"
                      />
                      Creating account…
                    </>
                  ) : (
                    "Create account"
                  )}
                </Button>
              </Form>
            </div>
          </Col>
        </Row>
      </Container>
    </section>
  );
}
