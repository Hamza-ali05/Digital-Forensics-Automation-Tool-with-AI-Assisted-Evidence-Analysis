import React, { useState } from "react";
import { useHistory } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faUnlockAlt, faUser } from "@fortawesome/free-solid-svg-icons";
import {
  Alert,
  Button,
  Col,
  Container,
  Form,
  FormCheck,
  InputGroup,
  Row,
  Spinner,
} from "@themesberg/react-bootstrap";

import { AUTH_CONFIG } from "config/auth.config";
import useAuth from "hooks/useAuth";
import useLocalStorage from "hooks/useLocalStorage";
import useNotification from "hooks/useNotification";
import usePageTitle from "hooks/usePageTitle";
import { validateRequired } from "utils/validators";
import { Routes } from "routes";
import BgImage from "../../assets/img/illustrations/signin.svg";

function formatLockoutRemaining(lockedUntil) {
  if (!lockedUntil) return null;
  const until = new Date(lockedUntil).getTime();
  if (Number.isNaN(until)) return null;
  const ms = until - Date.now();
  if (ms <= 0) return "a short time";
  const minutes = Math.ceil(ms / 60000);
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"}`;
  const hours = Math.ceil(minutes / 60);
  return `${hours} hour${hours === 1 ? "" : "s"}`;
}

/**
 * DFAT login — username/password against OAuth2 token endpoint.
 */
export default function Login() {
  usePageTitle("Sign in");
  const history = useHistory();
  const { login } = useAuth();
  const { error: notifyError } = useNotification();
  const [rememberMe, setRememberMe] = useLocalStorage(
    AUTH_CONFIG.rememberMeKey,
    false
  );

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);
  const [fieldErrors, setFieldErrors] = useState({});

  const validate = () => {
    const next = {};
    const userErr = validateRequired(username, "Username");
    const passErr = validateRequired(password, "Password");
    if (userErr) next.username = userErr;
    if (passErr) next.password = passErr;
    setFieldErrors(next);
    return Object.keys(next).length === 0;
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setFormError(null);
    if (!validate()) return;

    setSubmitting(true);
    try {
      await login(username.trim(), password);
      // rememberMe already persisted via useLocalStorage setter
      history.replace(Routes.Dashboard.path);
    } catch (err) {
      const status = err?.status;
      if (status === 423) {
        const remaining = formatLockoutRemaining(err?.details?.locked_until);
        setFormError(
          remaining
            ? `Account locked. Try again in ${remaining}.`
            : "Account locked. Please try again later."
        );
      } else if (status === 401) {
        setFormError("Invalid username or password.");
      } else {
        setFormError(err?.message || "Sign in failed. Please try again.");
        notifyError("Sign in failed", err?.message || "Unexpected error");
      }
      // Keep password field on failure (do not clear).
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
              <div className="text-center text-md-center mb-4 mt-md-0">
                <h1 className="h3 mb-0">Sign in to DFAT</h1>
                <p className="text-gray mb-0">Digital Forensics Automation Tool</p>
              </div>

              {formError ? (
                <Alert variant="danger" className="mb-3">
                  {formError}
                </Alert>
              ) : null}

              <Form className="mt-3" onSubmit={handleSubmit} noValidate>
                <Form.Group id="username" className="mb-4">
                  <Form.Label htmlFor="login-username">Username</Form.Label>
                  <InputGroup>
                    <InputGroup.Text aria-hidden="true">
                      <FontAwesomeIcon icon={faUser} aria-hidden="true" />
                    </InputGroup.Text>
                    <Form.Control
                      id="login-username"
                      autoFocus
                      required
                      type="text"
                      placeholder="investigator"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      isInvalid={Boolean(fieldErrors.username)}
                      disabled={submitting}
                      autoComplete="username"
                    />
                    <Form.Control.Feedback type="invalid">
                      {fieldErrors.username}
                    </Form.Control.Feedback>
                  </InputGroup>
                </Form.Group>

                <Form.Group id="password" className="mb-4">
                  <Form.Label htmlFor="login-password">Password</Form.Label>
                  <InputGroup>
                    <InputGroup.Text aria-hidden="true">
                      <FontAwesomeIcon icon={faUnlockAlt} aria-hidden="true" />
                    </InputGroup.Text>
                    <Form.Control
                      id="login-password"
                      required
                      type="password"
                      placeholder="Password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      isInvalid={Boolean(fieldErrors.password)}
                      disabled={submitting}
                      autoComplete="current-password"
                    />
                    <Form.Control.Feedback type="invalid">
                      {fieldErrors.password}
                    </Form.Control.Feedback>
                  </InputGroup>
                </Form.Group>

                <div className="d-flex justify-content-between align-items-center mb-4">
                  <Form.Check type="checkbox">
                    <FormCheck.Input
                      id="rememberMe"
                      className="me-2"
                      checked={Boolean(rememberMe)}
                      onChange={(e) => setRememberMe(e.target.checked)}
                      disabled={submitting}
                    />
                    <FormCheck.Label htmlFor="rememberMe" className="mb-0">
                      Remember me
                    </FormCheck.Label>
                  </Form.Check>
                </div>

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
                        role="status"
                        className="me-2"
                      >
                        <span className="visually-hidden">Signing in</span>
                      </Spinner>
                      Signing in…
                    </>
                  ) : (
                    "Sign in"
                  )}
                </Button>
              </Form>

              <div className="d-flex justify-content-center align-items-center mt-4">
                <span className="fw-normal text-muted small text-center">
                  Need an account? Ask an administrator or investigator to
                  register you via the in-app registration flow.
                </span>
              </div>
            </div>
          </Col>
        </Row>
      </Container>
    </section>
  );
}
