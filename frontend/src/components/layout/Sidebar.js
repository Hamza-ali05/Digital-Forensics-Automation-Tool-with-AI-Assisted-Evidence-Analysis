import React, { useEffect, useState } from "react";
import SimpleBar from "simplebar-react";
import { Link, useLocation } from "react-router-dom";
import { CSSTransition } from "react-transition-group";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faHome,
  faFolderOpen,
  faDatabase,
  faPlayCircle,
  faMicrochip,
  faFileAlt,
  faChartBar,
  faChartLine,
  faHistory,
  faTachometerAlt,
  faCog,
  faUsers,
  faUserCircle,
  faClipboardList,
  faQuestionCircle,
  faTimes,
  faSignOutAlt,
  faUserPlus,
  faShieldAlt,
  faClock,
  faBug,
  faAlignLeft,
  faCode,
} from "@fortawesome/free-solid-svg-icons";
import { Badge, Button, Nav, Navbar } from "@themesberg/react-bootstrap";

import config from "config";
import { API_ENDPOINTS } from "config/api.config";
import useAuth from "hooks/useAuth";
import usePermission from "hooks/usePermission";
import { apiGet } from "services/api";
import { Routes } from "routes";

function isNavActive(pathname, link) {
  if (link === Routes.Dashboard.path) {
    return pathname === link;
  }
  if (link === Routes.Evidence.path) {
    if (pathname === link) return true;
    if (
      pathname.startsWith("/evidence/register") ||
      pathname.startsWith("/evidence/integrity")
    ) {
      return false;
    }
    return pathname.startsWith(`${link}/`);
  }
  if (link === Routes.Pipeline.path) {
    if (pathname === link) return true;
    if (pathname.startsWith("/pipeline/run")) {
      return false;
    }
    return pathname.startsWith(`${link}/`);
  }
  if (link === Routes.ArtefactsTimeline.path || link === Routes.ArtefactsIOCs.path) {
    return pathname === link;
  }
  if (link === Routes.AISummary.path || link === Routes.JSONViewer.path) {
    return pathname === link;
  }
  if (link === Routes.AIAnalysis.path) {
    return (
      pathname === link ||
      pathname.startsWith("/artefacts/timeline") ||
      pathname.startsWith("/artefacts/iocs") ||
      pathname.startsWith("/ai/summary")
    );
  }
  if (link === Routes.Reports.path) {
    if (pathname === link) return true;
    if (pathname.startsWith("/reports/json")) return true;
    return pathname.startsWith(`${link}/`);
  }
  return pathname === link || pathname.startsWith(`${link}/`);
}

/**
 * DFAT forensic navigation sidebar with role-gated admin links and health.
 */
export default function Sidebar({ show = false, onClose, onToggle }) {
  const location = useLocation();
  const { pathname } = location;
  const { logout, user, role } = useAuth();
  const { canRead: canManageUsers } = usePermission("users");
  const canRegister = role === "admin" || role === "investigator";

  const [healthOk, setHealthOk] = useState(null);
  const [activeCaseCount, setActiveCaseCount] = useState(0);
  const [runningJobCount, setRunningJobCount] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function loadIndicators() {
      try {
        await apiGet(API_ENDPOINTS.HEALTH.CHECK);
        if (!cancelled) setHealthOk(true);
      } catch {
        if (!cancelled) setHealthOk(false);
      }

      try {
        const { data } = await apiGet(API_ENDPOINTS.CASES.MINE);
        const list = Array.isArray(data) ? data : data?.items || data?.cases || [];
        const active = list.filter((c) => {
          const status = (c.status || "").toLowerCase();
          return status === "active" || status === "open" || status === "under_review";
        }).length;
        if (!cancelled) setActiveCaseCount(active || list.length || 0);
      } catch {
        if (!cancelled) setActiveCaseCount(0);
      }

      try {
        const { data } = await apiGet(API_ENDPOINTS.PIPELINE.JOBS);
        const list = Array.isArray(data) ? data : data?.items || data?.jobs || [];
        const running = list.filter((job) => {
          const status = (job.status || "").toLowerCase();
          return status === "running" || status === "in_progress" || status === "queued";
        }).length;
        if (!cancelled) setRunningJobCount(running);
      } catch {
        if (!cancelled) setRunningJobCount(0);
      }
    }

    loadIndicators();
    const interval = window.setInterval(loadIndicators, config.pollingInterval || 15000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  const showClass = show ? "show" : "";

  const NavItem = ({ title, link, icon, badge }) => {
    const active = isNavActive(pathname, link);
    return (
      <Nav.Item className={active ? "active" : ""} onClick={onClose}>
        <Nav.Link as={Link} to={link} className="d-flex align-items-center justify-content-between">
          <span className="d-flex align-items-center">
            {icon ? (
              <span className="sidebar-icon">
                <FontAwesomeIcon icon={icon} aria-hidden="true" />
              </span>
            ) : null}
            <span className="sidebar-text">{title}</span>
          </span>
          {badge > 0 ? (
            <Badge bg="secondary" className="badge-md">
              {badge}
            </Badge>
          ) : null}
        </Nav.Link>
      </Nav.Item>
    );
  };

  const handleSignOut = async () => {
    if (onClose) onClose();
    try {
      await logout();
    } finally {
      window.location.href = Routes.Login.path;
    }
  };

  return (
    <>
      <Navbar
        expand={false}
        collapseOnSelect
        variant="dark"
        className="navbar-theme-primary px-4 d-md-none"
      >
        <Navbar.Brand as={Link} to={Routes.Dashboard.path} className="me-lg-5">
          <span className="text-white fw-bold">{config.appName}</span>
        </Navbar.Brand>
        <Navbar.Toggle
          as={Button}
          aria-controls="sidebar-nav"
          aria-label="Open navigation"
          onClick={onToggle}
        >
          <span className="navbar-toggler-icon" />
        </Navbar.Toggle>
      </Navbar>

      <CSSTransition timeout={300} in={show} classNames="sidebar-transition">
        <SimpleBar
          id="sidebar-nav"
          className={`collapse ${showClass} sidebar d-md-block bg-primary text-white`}
          role="navigation"
          aria-label="Primary"
        >
          <div className="sidebar-inner px-4 pt-3 d-flex flex-column" style={{ minHeight: "100%" }}>
            <div className="user-card d-flex d-md-none align-items-center justify-content-between pb-4">
              <div className="d-block">
                <h6 className="mb-1">{user?.username || config.appName}</h6>
                <Button
                  as={Link}
                  to={Routes.Profile.path}
                  variant="secondary"
                  size="xs"
                  className="text-dark me-2"
                  onClick={onClose}
                >
                  Profile
                </Button>
                <Button
                  variant="secondary"
                  size="xs"
                  className="text-dark"
                  onClick={handleSignOut}
                >
                  <FontAwesomeIcon icon={faSignOutAlt} className="me-2" aria-hidden="true" /> Sign Out
                </Button>
              </div>
              <Button
                variant="link"
                className="collapse-close d-md-none text-white p-0"
                onClick={onClose}
                aria-label="Close navigation"
              >
                <FontAwesomeIcon icon={faTimes} aria-hidden="true" />
              </Button>
            </div>

            <Nav className="flex-column pt-3 pt-md-0 flex-grow-1">
              <Nav.Item className="mb-3">
                <Nav.Link
                  as={Link}
                  to={Routes.Dashboard.path}
                  className="d-flex align-items-center"
                  onClick={onClose}
                >
                  <span className="sidebar-text fw-bold fs-5">{config.appName}</span>
                </Nav.Link>
              </Nav.Item>

              <NavItem title="Dashboard" link={Routes.Dashboard.path} icon={faHome} />
              <NavItem
                title="Cases"
                link={Routes.Cases.path}
                icon={faFolderOpen}
                badge={activeCaseCount}
              />
              <NavItem
                title="Evidence"
                link={Routes.Evidence.path}
                icon={faDatabase}
              />
              <NavItem
                title="Integrity Check"
                link={Routes.EvidenceIntegrity.path}
                icon={faShieldAlt}
              />
              <NavItem
                title="Pipeline"
                link={Routes.Pipeline.path}
                icon={faPlayCircle}
                badge={runningJobCount}
              />
              <NavItem
                title="AI Analysis"
                link={Routes.AIAnalysis.path}
                icon={faMicrochip}
              />
              <Nav.Item className="ms-3">
                <Nav.Link
                  as={Link}
                  to={Routes.ArtefactsTimeline.path}
                  className={`d-flex align-items-center py-1 ${
                    pathname === Routes.ArtefactsTimeline.path ? "active" : ""
                  }`}
                  onClick={onClose}
                >
                  <span className="sidebar-icon">
                    <FontAwesomeIcon icon={faClock} aria-hidden="true" />{" "}
                  </span>
                  <span className="sidebar-text">Timeline</span>
                </Nav.Link>
              </Nav.Item>
              <Nav.Item className="ms-3">
                <Nav.Link
                  as={Link}
                  to={Routes.ArtefactsIOCs.path}
                  className={`d-flex align-items-center py-1 ${
                    pathname === Routes.ArtefactsIOCs.path ? "active" : ""
                  }`}
                  onClick={onClose}
                >
                  <span className="sidebar-icon">
                    <FontAwesomeIcon icon={faBug} aria-hidden="true" />{" "}
                  </span>
                  <span className="sidebar-text">IOCs</span>
                </Nav.Link>
              </Nav.Item>
              <Nav.Item className="ms-3">
                <Nav.Link
                  as={Link}
                  to={Routes.AISummary.path}
                  className={`d-flex align-items-center py-1 ${
                    pathname === Routes.AISummary.path ? "active" : ""
                  }`}
                  onClick={onClose}
                >
                  <span className="sidebar-icon">
                    <FontAwesomeIcon icon={faAlignLeft} aria-hidden="true" />{" "}
                  </span>
                  <span className="sidebar-text">Summary</span>
                </Nav.Link>
              </Nav.Item>
              <NavItem title="Reports" link={Routes.Reports.path} icon={faFileAlt} />
              <Nav.Item className="ms-3">
                <Nav.Link
                  as={Link}
                  to={Routes.JSONViewer.path}
                  className={`d-flex align-items-center py-1 ${
                    pathname === Routes.JSONViewer.path ? "active" : ""
                  }`}
                  onClick={onClose}
                >
                  <span className="sidebar-icon">
                    <FontAwesomeIcon icon={faCode} aria-hidden="true" />{" "}
                  </span>
                  <span className="sidebar-text">JSON Artefacts</span>
                </Nav.Link>
              </Nav.Item>
              <NavItem
                title="Evaluation"
                link={Routes.Evaluation.path}
                icon={faChartBar}
              />
              <Nav.Item className="ms-3">
                <Nav.Link
                  as={Link}
                  to={Routes.EvaluationBenchmark.path}
                  className={`d-flex align-items-center py-1 ${
                    pathname === Routes.EvaluationBenchmark.path ? "active" : ""
                  }`}
                  onClick={onClose}
                >
                  <span className="sidebar-icon">
                    <FontAwesomeIcon icon={faChartLine} aria-hidden="true" />{" "}
                  </span>
                  <span className="sidebar-text">Benchmark</span>
                </Nav.Link>
              </Nav.Item>
              <Nav.Item className="ms-3">
                <Nav.Link
                  as={Link}
                  to={Routes.EvaluationBenchmarkHistory.path}
                  className={`d-flex align-items-center py-1 ${
                    pathname === Routes.EvaluationBenchmarkHistory.path
                      ? "active"
                      : ""
                  }`}
                  onClick={onClose}
                >
                  <span className="sidebar-icon">
                    <FontAwesomeIcon icon={faHistory} aria-hidden="true" />{" "}
                  </span>
                  <span className="sidebar-text">History</span>
                </Nav.Link>
              </Nav.Item>
              <Nav.Item className="ms-3">
                <Nav.Link
                  as={Link}
                  to={Routes.EvaluationPerformance.path}
                  className={`d-flex align-items-center py-1 ${
                    pathname === Routes.EvaluationPerformance.path ? "active" : ""
                  }`}
                  onClick={onClose}
                >
                  <span className="sidebar-icon">
                    <FontAwesomeIcon icon={faTachometerAlt} aria-hidden="true" />{" "}
                  </span>
                  <span className="sidebar-text">Performance</span>
                </Nav.Link>
              </Nav.Item>

              {canManageUsers || canRegister ? (
                <>
                  <Nav.Item className="my-2">
                    <hr className="border-light opacity-25 my-2" />
                  </Nav.Item>
                  <NavItem title="Profile" link={Routes.Profile.path} icon={faUserCircle} />
                  {canRegister ? (
                    <NavItem
                      title="Register user"
                      link={Routes.Register.path}
                      icon={faUserPlus}
                    />
                  ) : null}
                  {canManageUsers ? (
                    <>
                      <NavItem title="Settings" link={Routes.Settings.path} icon={faCog} />
                      <NavItem
                        title="User Management"
                        link={Routes.SettingsUsers.path}
                        icon={faUsers}
                      />
                      <NavItem
                        title="Audit Logs"
                        link={Routes.SettingsAudit.path}
                        icon={faClipboardList}
                      />
                    </>
                  ) : null}
                  <NavItem title="Help" link={Routes.Help.path} icon={faQuestionCircle} />
                </>
              ) : (
                <>
                  <Nav.Item className="my-2">
                    <hr className="border-light opacity-25 my-2" />
                  </Nav.Item>
                  <NavItem title="Profile" link={Routes.Profile.path} icon={faUserCircle} />
                  <NavItem title="Help" link={Routes.Help.path} icon={faQuestionCircle} />
                </>
              )}
            </Nav>

            <div className="sidebar-footer mt-auto pt-3 pb-4 small">
              <div className="d-flex align-items-center justify-content-between text-white-50">
                <span>
                  {config.appName} v{config.appVersion}
                </span>
                <span
                  className="d-inline-flex align-items-center"
                  title={
                    healthOk === null
                      ? "Checking system health…"
                      : healthOk
                        ? "System healthy"
                        : "System unhealthy"
                  }
                >
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: "50%",
                      backgroundColor:
                        healthOk === null
                          ? "#adb5bd"
                          : healthOk
                            ? "#198754"
                            : "#dc3545",
                      display: "inline-block",
                      marginRight: 6,
                    }}
                  />
                  Health
                </span>
              </div>
            </div>
          </div>
        </SimpleBar>
      </CSSTransition>
    </>
  );
}
