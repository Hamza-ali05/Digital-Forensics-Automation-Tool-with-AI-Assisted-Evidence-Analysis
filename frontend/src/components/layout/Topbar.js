import React, { useEffect, useMemo, useState } from "react";
import { Link, useHistory } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faBars,
  faBell,
  faCog,
  faKey,
  faSignOutAlt,
  faUser,
} from "@fortawesome/free-solid-svg-icons";
import { faUserCircle } from "@fortawesome/free-regular-svg-icons";
import {
  Badge,
  Button,
  Container,
  Dropdown,
  Nav,
  Navbar,
} from "@themesberg/react-bootstrap";

import Breadcrumbs from "components/layout/Breadcrumbs";
import { API_ENDPOINTS } from "config/api.config";
import useAuth from "hooks/useAuth";
import useNotification from "hooks/useNotification";
import { apiGet } from "services/api";
import { Routes } from "routes";

function formatLastLogin(value) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return String(value);
  }
}

/**
 * Dashboard top bar: mobile toggle, breadcrumbs, AI health, notifications, user menu.
 */
export default function Topbar({ onToggleSidebar }) {
  const history = useHistory();
  const { user, role, logout } = useAuth();
  const { notifications, clearAll } = useNotification();
  const [aiHealthy, setAiHealthy] = useState(null);

  useEffect(() => {
    let cancelled = false;

    async function checkAi() {
      try {
        const { data } = await apiGet(API_ENDPOINTS.AI.HEALTH);
        const ok =
          data?.status === "healthy" ||
          data?.status === "ok" ||
          data?.healthy === true ||
          data?.available === true ||
          !data?.status;
        if (!cancelled) setAiHealthy(Boolean(ok || data));
      } catch {
        if (!cancelled) setAiHealthy(false);
      }
    }

    checkAi();
    const id = window.setInterval(checkAi, 30000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const unread = notifications.length;

  const roleLabel = useMemo(() => role || user?.role_name || "unknown", [role, user]);

  const handleLogout = async () => {
    try {
      await logout();
    } finally {
      history.push(Routes.Login.path);
    }
  };

  return (
    <Navbar variant="dark" expanded className="ps-0 pe-2 pb-0" aria-label="Toolbar">
      <Container fluid className="px-0">
        <div className="d-flex justify-content-between w-100 align-items-center">
          <div className="d-flex align-items-center flex-grow-1 min-w-0">
            <Button
              variant="link"
              className="d-md-none text-dark px-2 me-1"
              onClick={onToggleSidebar}
              aria-label="Toggle navigation"
            >
              <FontAwesomeIcon icon={faBars} aria-hidden="true" />
            </Button>
            <div className="flex-grow-1 min-w-0 d-none d-sm-block">
              <Breadcrumbs compact />
            </div>
          </div>

          <Nav className="align-items-center flex-nowrap">
            <Nav.Item className="me-2 d-none d-md-flex align-items-center">
              <span
                className="small text-gray-600 d-inline-flex align-items-center"
                title={
                  aiHealthy === null
                    ? "Checking AI…"
                    : aiHealthy
                      ? "AI service healthy"
                      : "AI service unavailable"
                }
              >
                <span
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    backgroundColor:
                      aiHealthy === null
                        ? "#adb5bd"
                        : aiHealthy
                          ? "#198754"
                          : "#dc3545",
                    display: "inline-block",
                    marginRight: 6,
                  }}
                />
                AI
              </span>
            </Nav.Item>

            <Dropdown as={Nav.Item} className="me-2">
              <Dropdown.Toggle
                as={Nav.Link}
                className="text-dark px-2 pt-1"
                aria-label="Notifications"
              >
                <span className="icon icon-sm position-relative">
                  <FontAwesomeIcon icon={faBell} aria-hidden="true" />
                  {unread > 0 ? (
                    <Badge
                      bg="danger"
                      className="position-absolute top-0 start-100 translate-middle badge-sm"
                      style={{ fontSize: "0.65rem" }}
                    >
                      {unread}
                    </Badge>
                  ) : null}
                </span>
              </Dropdown.Toggle>
              <Dropdown.Menu className="dropdown-menu-right mt-2 py-2" style={{ minWidth: 240 }}>
                <Dropdown.Header>Notifications</Dropdown.Header>
                {unread === 0 ? (
                  <Dropdown.ItemText className="text-muted small">
                    No notifications
                  </Dropdown.ItemText>
                ) : (
                  notifications.slice(0, 5).map((n) => (
                    <Dropdown.ItemText key={n.id} className="small">
                      <strong>{n.title || n.type}</strong>
                      {n.message ? ` — ${n.message}` : ""}
                    </Dropdown.ItemText>
                  ))
                )}
                {unread > 0 ? (
                  <>
                    <Dropdown.Divider />
                    <Dropdown.Item className="fw-bold text-center" onClick={clearAll}>
                      Clear all
                    </Dropdown.Item>
                  </>
                ) : null}
              </Dropdown.Menu>
            </Dropdown>

            <Dropdown as={Nav.Item}>
              <Dropdown.Toggle
                as={Nav.Link}
                className="pt-1 px-0"
                aria-label={`User menu for ${user?.username || "user"}`}
              >
                <div className="media d-flex align-items-center">
                  <span className="icon icon-sm text-gray-600">
                    <FontAwesomeIcon icon={faUserCircle} size="2x" aria-hidden="true" />
                  </span>
                  <div className="media-body ms-2 text-dark align-items-center d-none d-lg-block">
                    <span className="mb-0 font-small fw-bold">
                      {user?.username || "User"}
                    </span>
                  </div>
                </div>
              </Dropdown.Toggle>
              <Dropdown.Menu className="user-dropdown dropdown-menu-right mt-2">
                <div className="px-3 py-2 border-bottom">
                  <div className="fw-bold">{user?.username || "User"}</div>
                  <Badge bg="primary" className="me-1 text-uppercase">
                    {roleLabel}
                  </Badge>
                  <div className="small text-muted mt-1">
                    Last login: {formatLastLogin(user?.last_login)}
                  </div>
                </div>
                <Dropdown.Item
                  as={Link}
                  to={Routes.Profile.path}
                  className="fw-bold"
                >
                  <FontAwesomeIcon icon={faUser} className="me-2" /> Profile
                </Dropdown.Item>
                <Dropdown.Item
                  as={Link}
                  to={Routes.Profile.path}
                  className="fw-bold"
                >
                  <FontAwesomeIcon icon={faKey} className="me-2" /> Change password
                </Dropdown.Item>
                <Dropdown.Item as={Link} to={Routes.Settings.path} className="fw-bold">
                  <FontAwesomeIcon icon={faCog} className="me-2" /> Settings
                </Dropdown.Item>
                <Dropdown.Divider />
                <Dropdown.Item className="fw-bold" onClick={handleLogout}>
                  <FontAwesomeIcon icon={faSignOutAlt} className="text-danger me-2" />{" "}
                  Logout
                </Dropdown.Item>
              </Dropdown.Menu>
            </Dropdown>
          </Nav>
        </div>
      </Container>
    </Navbar>
  );
}
