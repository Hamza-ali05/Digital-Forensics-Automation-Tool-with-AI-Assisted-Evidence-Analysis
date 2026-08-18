import React, { useCallback, useEffect, useState } from "react";
import {
  Badge,
  Button,
  Card,
  Col,
  Container,
  Row,
  Spinner,
  Table,
} from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faBroom,
  faCheckCircle,
  faDatabase,
  faMicrochip,
  faServer,
  faTimesCircle,
} from "@fortawesome/free-solid-svg-icons";

import PageHeader from "components/common/PageHeader";
import ApiErrorDisplay from "components/common/ApiErrorDisplay";
import EmptyState from "components/common/EmptyState";
import SkeletonLoader from "components/common/SkeletonLoader";
import HealthBar from "components/forensic/HealthBar";
import config from "config";
import { formatDate } from "utils/formatters";
import useNotification from "hooks/useNotification";
import healthService from "services/health.service";
import aiService, { isAiHealthy } from "services/ai.service";
import pipelineService from "services/pipeline.service";
import { Routes } from "routes";

function BoolIcon({ ok }) {
  return (
    <FontAwesomeIcon
      icon={ok ? faCheckCircle : faTimesCircle}
      className={ok ? "text-success" : "text-danger"}
    />
  );
}

/**
 * Admin system settings — health, AI, parsers, database diagnostics.
 */
export default function Settings() {
  const { success, error: notifyError } = useNotification();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [detailed, setDetailed] = useState(null);
  const [aiHealth, setAiHealth] = useState(null);
  const [aiStats, setAiStats] = useState(null);
  const [cacheStats, setCacheStats] = useState(null);
  const [parsers, setParsers] = useState([]);
  const [clearing, setClearing] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [detail, health, stats, cache, parserList] = await Promise.all([
        healthService.detailed(),
        aiService.getHealth().catch(() => null),
        aiService.getStats().catch(() => null),
        aiService.getCacheStats().catch(() => null),
        pipelineService.listParsers().catch(() => []),
      ]);
      setDetailed(detail);
      setAiHealth(health);
      setAiStats(stats);
      setCacheStats(cache);
      const list = Array.isArray(parserList)
        ? parserList
        : parserList?.parsers || [];
      setParsers(list);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load().catch(() => {});
  }, [load]);

  const handleClearCache = async () => {
    setClearing(true);
    try {
      const result = await aiService.clearCache();
      success(
        "Cache cleared",
        result?.message ||
          `Cleared ${result?.cleared_count ?? result?.cleared ?? "all"} entries.`
      );
      const cache = await aiService.getCacheStats().catch(() => null);
      setCacheStats(cache);
    } catch (err) {
      notifyError("Clear failed", err?.message || "Could not clear AI cache.");
    } finally {
      setClearing(false);
    }
  };

  const checks = detailed?.checks || {};
  const tableCounts = detailed?.database_table_counts || {};
  const packages = detailed?.package_versions || {};

  return (
    <Container fluid className="px-0">
      <PageHeader
        title="System Settings"
        subtitle="Read-only diagnostics for health, AI engine, parsers, and database"
        breadcrumbs={[
          { label: "Home", to: Routes.Dashboard.path },
          { label: "Settings" },
        ]}
      />

      {error ? (
        <ApiErrorDisplay error={error} onRetry={load} className="mb-3" />
      ) : null}

      {loading ? (
        <SkeletonLoader type="detail" rows={8} />
      ) : (
        <>
          <h5 className="mb-3">
            <FontAwesomeIcon icon={faServer} className="me-2 text-primary" />
            System Health
          </h5>
          <div className="mb-4">
            <HealthBar
              checks={checks}
              loading={false}
              error={!detailed}
            />
          </div>
          <Card border="light" className="shadow-sm mb-4">
            <Card.Body>
              <Row className="g-3 small">
                <Col xs={12} md={4}>
                  <div className="text-muted text-uppercase fw-bold">Status</div>
                  <div>{detailed?.status || "—"}</div>
                </Col>
                <Col xs={12} md={4}>
                  <div className="text-muted text-uppercase fw-bold">Version</div>
                  <div>{detailed?.version || config.appVersion}</div>
                </Col>
                <Col xs={12} md={4}>
                  <div className="text-muted text-uppercase fw-bold">Uptime</div>
                  <div>
                    {detailed?.uptime_seconds != null
                      ? `${Math.round(detailed.uptime_seconds)}s`
                      : "—"}
                  </div>
                </Col>
                <Col xs={12} md={4}>
                  <div className="text-muted text-uppercase fw-bold">Python</div>
                  <div>{detailed?.python_version || "—"}</div>
                </Col>
                <Col xs={12} md={4}>
                  <div className="text-muted text-uppercase fw-bold">Platform</div>
                  <div className="text-break">{detailed?.platform || "—"}</div>
                </Col>
                <Col xs={12} md={4}>
                  <div className="text-muted text-uppercase fw-bold">Memory</div>
                  <div>
                    {detailed?.memory_usage_mb != null
                      ? `${detailed.memory_usage_mb} MB`
                      : "—"}
                  </div>
                </Col>
                <Col xs={12}>
                  <div className="text-muted text-uppercase fw-bold mb-1">
                    Package versions
                  </div>
                  <div className="d-flex flex-wrap gap-1">
                    {Object.entries(packages).map(([name, ver]) => (
                      <Badge key={name} bg="light" text="dark" className="border">
                        {name}: {ver}
                      </Badge>
                    ))}
                    {!Object.keys(packages).length ? (
                      <span className="text-muted">Unavailable</span>
                    ) : null}
                  </div>
                </Col>
              </Row>
            </Card.Body>
          </Card>

          <h5 className="mb-3">
            <FontAwesomeIcon icon={faMicrochip} className="me-2 text-primary" />
            AI Engine
          </h5>
          <Card border="light" className="shadow-sm mb-4">
            <Card.Body>
              <Row className="g-3 mb-3">
                <Col xs={12} md={4}>
                  <div className="text-muted small text-uppercase fw-bold">
                    Availability
                  </div>
                  <div>
                    <BoolIcon ok={isAiHealthy(aiHealth)} />{" "}
                    {isAiHealthy(aiHealth) ? "Healthy" : "Unavailable"}
                  </div>
                </Col>
                <Col xs={12} md={4}>
                  <div className="text-muted small text-uppercase fw-bold">
                    Model
                  </div>
                  <div>
                    {aiHealth?.model ||
                      aiStats?.model ||
                      aiStats?.model_name ||
                      "—"}
                  </div>
                </Col>
                <Col xs={12} md={4}>
                  <div className="text-muted small text-uppercase fw-bold">
                    Checked
                  </div>
                  <div>{formatDate(aiHealth?.checked_at) || "—"}</div>
                </Col>
              </Row>
              <div className="d-flex flex-wrap align-items-center gap-3 mb-3">
                <div className="small">
                  Cache hits:{" "}
                  <strong>
                    {cacheStats?.hits ?? cacheStats?.hit_count ?? "—"}
                  </strong>
                </div>
                <div className="small">
                  Misses:{" "}
                  <strong>
                    {cacheStats?.misses ?? cacheStats?.miss_count ?? "—"}
                  </strong>
                </div>
                <div className="small">
                  Entries:{" "}
                  <strong>
                    {cacheStats?.size ??
                      cacheStats?.entry_count ??
                      cacheStats?.entries ??
                      "—"}
                  </strong>
                </div>
              </div>
              <Button
                variant="outline-danger"
                size="sm"
                disabled={clearing}
                onClick={handleClearCache}
              >
                {clearing ? (
                  <Spinner animation="border" size="sm" className="me-2" />
                ) : (
                  <FontAwesomeIcon icon={faBroom} className="me-2" />
                )}
                Clear cache
              </Button>
            </Card.Body>
          </Card>

          <h5 className="mb-3">Pipeline parsers</h5>
          <Card border="light" className="shadow-sm mb-4">
            <Card.Body className="pt-0">
              {!parsers.length ? (
                <EmptyState
                  title="No parsers reported"
                  description="The pipeline parsers endpoint returned an empty list."
                />
              ) : (
                <Table responsive hover className="align-middle mb-0">
                  <thead className="thead-light">
                    <tr>
                      <th>Parser Name</th>
                      <th>Availability</th>
                    </tr>
                  </thead>
                  <tbody>
                    {parsers.map((parser) => {
                      const name =
                        parser.parser_name || parser.name || String(parser);
                      const available =
                        parser.available === true ||
                        String(parser.status || "").toLowerCase() ===
                          "available";
                      return (
                        <tr key={name}>
                          <td>{name}</td>
                          <td>
                            <Badge bg={available ? "success" : "secondary"}>
                              {available ? "Available" : "Unavailable"}
                            </Badge>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </Table>
              )}
            </Card.Body>
          </Card>

          <h5 className="mb-3">
            <FontAwesomeIcon icon={faDatabase} className="me-2 text-primary" />
            Database
          </h5>
          <Card border="light" className="shadow-sm mb-4">
            <Card.Body>
              <p className="small text-muted">
                Table counts from the detailed health probe. Migration version is
                not exposed by the API; use{" "}
                <code>make db-current</code> on the server for Alembic state.
              </p>
              <Table responsive size="sm" className="mb-0">
                <thead className="thead-light">
                  <tr>
                    <th>Table</th>
                    <th>Count</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(tableCounts).length ? (
                    Object.entries(tableCounts).map(([table, count]) => (
                      <tr key={table}>
                        <td>
                          <code>{table}</code>
                        </td>
                        <td>{count < 0 ? "—" : count}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={2} className="text-muted">
                        Table counts unavailable
                      </td>
                    </tr>
                  )}
                </tbody>
              </Table>
            </Card.Body>
          </Card>

          <h5 className="mb-3">Configuration (read-only)</h5>
          <Card border="light" className="shadow-sm mb-4">
            <Card.Body>
              <dl className="row mb-0 small">
                <dt className="col-sm-4 text-muted">App name</dt>
                <dd className="col-sm-8">{config.appName}</dd>
                <dt className="col-sm-4 text-muted">App version</dt>
                <dd className="col-sm-8">{config.appVersion}</dd>
                <dt className="col-sm-4 text-muted">API base URL</dt>
                <dd className="col-sm-8">
                  <code>{config.apiBaseUrl}</code>
                </dd>
                <dt className="col-sm-4 text-muted">Polling interval</dt>
                <dd className="col-sm-8">{config.pollingInterval} ms</dd>
                <dt className="col-sm-4 text-muted">Max upload size</dt>
                <dd className="col-sm-8">{config.maxFileSizeMB} MB</dd>
                <dt className="col-sm-4 text-muted">Debug</dt>
                <dd className="col-sm-8">{config.debug ? "Enabled" : "Disabled"}</dd>
              </dl>
            </Card.Body>
          </Card>
        </>
      )}
    </Container>
  );
}
