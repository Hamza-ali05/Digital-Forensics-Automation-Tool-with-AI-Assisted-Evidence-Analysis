import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Badge,
  Button,
  Card,
  Col,
  Container,
  Form,
  Modal,
  Row,
  Table,
} from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faBug,
  faSearch,
  faShieldAlt,
  faSync,
} from "@fortawesome/free-solid-svg-icons";

import PageHeader from "components/common/PageHeader";
import DataTable from "components/common/DataTable";
import ApiErrorDisplay from "components/common/ApiErrorDisplay";
import EmptyState from "components/common/EmptyState";
import SkeletonLoader from "components/common/SkeletonLoader";
import StatCard from "components/forensic/StatCard";
import {
  evidenceOptionId,
  evidenceOptionLabel,
  loadEvidenceOptions,
} from "utils/artefactLoader";
import threatIntelService from "services/threat-intel.service";
import useNotification from "hooks/useNotification";

const TACTIC_ORDER = [
  "Reconnaissance",
  "Resource Development",
  "Initial Access",
  "Execution",
  "Persistence",
  "Privilege Escalation",
  "Defense Evasion",
  "Credential Access",
  "Discovery",
  "Lateral Movement",
  "Collection",
  "Command and Control",
  "Exfiltration",
  "Impact",
];

function heatColour(count) {
  if (!count) return "#f8f9fa";
  if (count >= 3) return "#dc3545";
  if (count >= 2) return "#fd7e14";
  return "#ffc107";
}

/**
 * Threat intelligence dashboard with MITRE heatmap and artefact scanning.
 */
export default function ThreatIntelDashboard() {
  const { success, error: notifyError } = useNotification();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [summary, setSummary] = useState({});
  const [mitre, setMitre] = useState({ techniques: [], tactics: {} });
  const [recentMatches, setRecentMatches] = useState([]);
  const [evidenceOptions, setEvidenceOptions] = useState([]);
  const [showScanModal, setShowScanModal] = useState(false);
  const [selectedEvidence, setSelectedEvidence] = useState("");
  const [scanning, setScanning] = useState(false);
  const [scanResult, setScanResult] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [summaryResult, mitreResult, evidenceRows] = await Promise.all([
        threatIntelService.getSummary(),
        threatIntelService.getMitreCoverage(),
        loadEvidenceOptions(),
      ]);
      setSummary(summaryResult);
      setMitre(mitreResult);
      setEvidenceOptions(evidenceRows);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleScan = async () => {
    if (!selectedEvidence) return;
    setScanning(true);
    try {
      const result = await threatIntelService.scan({
        evidence_id: selectedEvidence,
      });
      setScanResult(result);
      const findings = [
        ...(result.yara_matches || []).map((item) => ({
          type: "YARA",
          label: item.rule_name || item.rule || "YARA match",
          severity: "high",
        })),
        ...(result.sigma_matches || []).map((item) => ({
          type: "Sigma",
          label: item.title || item.rule_name || "Sigma match",
          severity: "medium",
        })),
        ...(result.ioc_matches || []).map((item) => ({
          type: "IOC",
          label: item.value || item.ioc_value || "IOC match",
          severity: "high",
        })),
      ];
      setRecentMatches((prev) => [
        ...findings.slice(0, 10),
        ...prev,
      ].slice(0, 20));
      success(
        "Scan complete",
        `${result.total_findings ?? findings.length} findings across intelligence sources.`
      );
      setShowScanModal(false);
    } catch (err) {
      notifyError("Scan failed", err?.message || "Unable to scan against threat intel.");
    } finally {
      setScanning(false);
    }
  };

  const heatmapRows = useMemo(() => {
    const tactics = mitre.tactics || {};
    const techniques = mitre.techniques || [];
    const techniqueById = {};
    techniques.forEach((item) => {
      techniqueById[item.technique_id] = item;
    });

    return TACTIC_ORDER.filter((tactic) => tactics[tactic]?.length).map((tactic) => ({
      tactic,
      techniques: (tactics[tactic] || []).map((id) => ({
        id,
        name: techniqueById[id]?.name || id,
        count: 1,
      })),
    }));
  }, [mitre]);

  const matchColumns = useMemo(
    () => [
      {
        key: "type",
        header: "Source",
        render: (row) => <Badge bg="secondary">{row.type}</Badge>,
      },
      { key: "label", header: "Match" },
      {
        key: "severity",
        header: "Severity",
        render: (row) => (
          <Badge bg={row.severity === "high" ? "danger" : "warning"}>
            {row.severity}
          </Badge>
        ),
      },
    ],
    []
  );

  if (loading && !summary) {
    return (
      <Container fluid className="px-0">
        <SkeletonLoader type="dashboard" />
      </Container>
    );
  }

  return (
    <Container fluid className="px-0">
      <PageHeader
        title="Threat Intelligence"
        subtitle="YARA, Sigma, IOC coverage and artefact scanning"
        actions={
          <>
            <Button variant="outline-secondary" onClick={load}>
              <FontAwesomeIcon icon={faSync} className="me-2" />
              Refresh
            </Button>
            <Button
              variant="primary"
              className="ms-2"
              onClick={() => setShowScanModal(true)}
            >
              <FontAwesomeIcon icon={faSearch} className="me-2" />
              Scan Against Intel
            </Button>
          </>
        }
      />

      {error ? <ApiErrorDisplay error={error} onRetry={load} className="mb-3" /> : null}

      <Row className="g-3 mb-3">
        <Col xs={12} md={4}>
          <StatCard
            title="YARA Rules"
            value={summary.yara_rules ?? summary.yara_rule_count ?? 0}
            icon={faShieldAlt}
            colour="danger"
          />
        </Col>
        <Col xs={12} md={4}>
          <StatCard
            title="Sigma Rules"
            value={summary.sigma_rules ?? summary.sigma_rule_count ?? 0}
            icon={faBug}
            colour="warning"
          />
        </Col>
        <Col xs={12} md={4}>
          <StatCard
            title="IOC Entries"
            value={summary.ioc_count ?? summary.total_iocs ?? 0}
            icon={faShieldAlt}
            colour="primary"
          />
        </Col>
      </Row>

      <Card border="light" className="shadow-sm mb-3">
        <Card.Header>MITRE ATT&CK Coverage</Card.Header>
        <Card.Body className="table-responsive">
          {heatmapRows.length ? (
            <Table size="sm" bordered className="mb-0 align-middle">
              <thead>
                <tr>
                  <th>Tactic</th>
                  <th>Techniques</th>
                </tr>
              </thead>
              <tbody>
                {heatmapRows.map((row) => (
                  <tr key={row.tactic}>
                    <td className="fw-bold text-nowrap">{row.tactic}</td>
                    <td>
                      <div className="d-flex flex-wrap gap-1">
                        {row.techniques.map((technique) => (
                          <span
                            key={technique.id}
                            title={`${technique.id}: ${technique.name}`}
                            className="badge rounded-pill"
                            style={{
                              backgroundColor: heatColour(technique.count),
                              color: "#212529",
                              cursor: "default",
                            }}
                          >
                            {technique.id}
                          </span>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <EmptyState message="MITRE coverage data unavailable." />
          )}
        </Card.Body>
      </Card>

      {scanResult ? (
        <Card border="light" className="shadow-sm mb-3">
          <Card.Header>Latest Scan Results</Card.Header>
          <Card.Body>
            <Row className="g-3">
              <Col xs={12} md={3}>
                <div className="text-muted small">Total findings</div>
                <div className="h4 mb-0">{scanResult.total_findings ?? 0}</div>
              </Col>
              <Col xs={12} md={3}>
                <div className="text-muted small">YARA</div>
                <div className="h5 mb-0">{scanResult.yara_matches?.length ?? 0}</div>
              </Col>
              <Col xs={12} md={3}>
                <div className="text-muted small">Sigma</div>
                <div className="h5 mb-0">{scanResult.sigma_matches?.length ?? 0}</div>
              </Col>
              <Col xs={12} md={3}>
                <div className="text-muted small">IOCs</div>
                <div className="h5 mb-0">{scanResult.ioc_matches?.length ?? 0}</div>
              </Col>
            </Row>
          </Card.Body>
        </Card>
      ) : null}

      <Card border="light" className="shadow-sm">
        <Card.Header>Recent Threat Intel Matches</Card.Header>
        <Card.Body className="p-0">
          {recentMatches.length ? (
            <DataTable
              columns={matchColumns}
              data={recentMatches}
              keyField="label"
              emptyMessage="No matches yet."
            />
          ) : (
            <EmptyState message="Run a scan to populate recent threat intelligence matches." />
          )}
        </Card.Body>
      </Card>

      <Modal show={showScanModal} onHide={() => setShowScanModal(false)} centered>
        <Modal.Header closeButton>
          <Modal.Title>Scan Against Intel</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Form.Group>
            <Form.Label>Evidence</Form.Label>
            <Form.Select
              value={selectedEvidence}
              onChange={(e) => setSelectedEvidence(e.target.value)}
            >
              <option value="">Select evidence…</option>
              {evidenceOptions.map((item) => (
                <option key={evidenceOptionId(item)} value={evidenceOptionId(item)}>
                  {evidenceOptionLabel(item)}
                </option>
              ))}
            </Form.Select>
          </Form.Group>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="outline-secondary" onClick={() => setShowScanModal(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleScan}
            disabled={!selectedEvidence || scanning}
          >
            {scanning ? "Scanning…" : "Run Scan"}
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
}
