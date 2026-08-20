import React, { useCallback, useEffect, useState } from "react";
import {
  Badge,
  Card,
  Col,
  Container,
  ListGroup,
  Row,
} from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faBook,
  faBrain,
  faChartBar,
  faMicrochip,
  faShieldVirus,
  faWrench,
} from "@fortawesome/free-solid-svg-icons";

import PageHeader from "components/common/PageHeader";
import ApiErrorDisplay from "components/common/ApiErrorDisplay";
import SkeletonLoader from "components/common/SkeletonLoader";
import systemService from "services/system.service";
import knowledgeService from "services/knowledge.service";
import threatIntelService from "services/threat-intel.service";

const INSTALL_HINTS = {
  llm: "Install Ollama locally and pull the configured model (e.g. ollama pull llama3). Ensure DFAT AI settings point to your Ollama API URL.",
  rag: "Enable RAG in config, ensure Ollama is healthy, and index documents into the knowledge vector store from the Knowledge dashboard.",
  ml: "Place labelled datasets under data/datasets and train a model from the ML dashboard or wait for auto-retrain.",
  yara: "Install yara-python and add .yar rule files under data/threat_intel/yara/, then restart DFAT.",
  sigma: "Install pySigma and add Sigma rules under data/threat_intel/sigma/, then restart DFAT.",
  mitre: "MITRE mappings are embedded; if unavailable, verify threat intelligence bootstrap completed without errors.",
  vector_store: "Ensure ChromaDB dependencies are installed and the knowledge base directory is writable.",
  graph: "Initialize the forensic knowledge graph during bootstrap; check logs for graph build errors.",
  ioc_db: "Import or generate IOC entries under the knowledge IOC database path.",
  dfrws: "Place DFRWS ground-truth JSON files under data/ground_truth/dfrws/.",
  cfreds: "Place CFReDS ground-truth JSON files under data/ground_truth/cfreds/.",
};

function AvailabilityBadge({ available }) {
  return (
    <Badge bg={available ? "success" : "danger"}>
      {available ? "Available" : "Unavailable"}
    </Badge>
  );
}

function CapabilitySection({ title, icon, children }) {
  return (
    <Col xs={12} lg={6} className="mb-4">
      <Card className="border-0 shadow-sm h-100">
        <Card.Body>
          <Card.Title className="h5 mb-3">
            <FontAwesomeIcon icon={icon} className="me-2 text-primary" aria-hidden="true" />
            {title}
          </Card.Title>
          {children}
        </Card.Body>
      </Card>
    </Col>
  );
}

function UnavailableHint({ featureKey }) {
  const hint = INSTALL_HINTS[featureKey];
  if (!hint) return null;
  return (
    <div className="small text-muted mt-2">
      <FontAwesomeIcon icon={faWrench} className="me-1" aria-hidden="true" />
      {hint}
    </div>
  );
}

/**
 * Admin capability overview across parsers, AI, threat intel, knowledge, and benchmarks.
 */
export default function CapabilityDashboard() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [capabilities, setCapabilities] = useState(null);
  const [knowledgeStats, setKnowledgeStats] = useState(null);
  const [threatSummary, setThreatSummary] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [caps, stats, summary] = await Promise.all([
        systemService.getCapabilities(),
        knowledgeService.getStats().catch(() => null),
        threatIntelService.getSummary().catch(() => null),
      ]);
      setCapabilities(caps);
      setKnowledgeStats(stats);
      setThreatSummary(summary);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const parserEntries = Object.entries(capabilities?.parsers || {});
  const ai = capabilities?.ai || {};
  const ti = capabilities?.threat_intel || {};
  const knowledge = capabilities?.knowledge || {};
  const benchmarks = capabilities?.benchmarks || {};

  const vectorDocs = knowledgeStats?.collections
    ? Object.values(knowledgeStats.collections).reduce(
        (sum, item) =>
          sum + Number(item?.count ?? item?.document_count ?? item?.documents ?? 0),
        0
      )
    : knowledgeStats?.document_count;

  return (
    <Container fluid className="px-4 py-4">
      <PageHeader
        title="System Capabilities"
        subtitle="Feature availability and subsystem readiness"
      />

      {error ? <ApiErrorDisplay error={error} className="mb-3" /> : null}

      {loading ? (
        <SkeletonLoader lines={8} />
      ) : (
        <Row>
          <CapabilitySection title="Forensic Parsers" icon={faWrench}>
            <ListGroup variant="flush">
              {parserEntries.length ? (
                parserEntries.map(([name, available]) => (
                  <ListGroup.Item key={name} className="px-0 d-flex justify-content-between">
                    <span>{name}</span>
                    <AvailabilityBadge available={available} />
                  </ListGroup.Item>
                ))
              ) : (
                <ListGroup.Item className="px-0 text-muted">
                  No parsers registered.
                </ListGroup.Item>
              )}
            </ListGroup>
          </CapabilitySection>

          <CapabilitySection title="AI Engine" icon={faMicrochip}>
            <ListGroup variant="flush">
              {[
                ["llm", "LLM (Ollama)"],
                ["rag", "RAG Pipeline"],
                ["ml", "ML Models"],
              ].map(([key, label]) => (
                <ListGroup.Item key={key} className="px-0">
                  <div className="d-flex justify-content-between align-items-center">
                    <span>{label}</span>
                    <AvailabilityBadge available={ai[key]} />
                  </div>
                  {!ai[key] ? <UnavailableHint featureKey={key} /> : null}
                </ListGroup.Item>
              ))}
            </ListGroup>
          </CapabilitySection>

          <CapabilitySection title="Threat Intelligence" icon={faShieldVirus}>
            <ListGroup variant="flush">
              <ListGroup.Item className="px-0 d-flex justify-content-between">
                <span>
                  YARA rules
                  {threatSummary?.yara_rules != null
                    ? ` (${threatSummary.yara_rules})`
                    : ""}
                </span>
                <AvailabilityBadge available={ti.yara} />
              </ListGroup.Item>
              {!ti.yara ? <UnavailableHint featureKey="yara" /> : null}
              <ListGroup.Item className="px-0 d-flex justify-content-between">
                <span>
                  Sigma rules
                  {threatSummary?.sigma_rules != null
                    ? ` (${threatSummary.sigma_rules})`
                    : ""}
                </span>
                <AvailabilityBadge available={ti.sigma} />
              </ListGroup.Item>
              {!ti.sigma ? <UnavailableHint featureKey="sigma" /> : null}
              <ListGroup.Item className="px-0 d-flex justify-content-between">
                <span>MITRE ATT&CK</span>
                <AvailabilityBadge available={ti.mitre} />
              </ListGroup.Item>
              {!ti.mitre ? <UnavailableHint featureKey="mitre" /> : null}
            </ListGroup>
          </CapabilitySection>

          <CapabilitySection title="Knowledge Base" icon={faBook}>
            <ListGroup variant="flush">
              <ListGroup.Item className="px-0 d-flex justify-content-between">
                <span>
                  Vector store
                  {vectorDocs != null ? ` (${vectorDocs} docs)` : ""}
                </span>
                <AvailabilityBadge available={knowledge.vector_store} />
              </ListGroup.Item>
              {!knowledge.vector_store ? <UnavailableHint featureKey="vector_store" /> : null}
              <ListGroup.Item className="px-0 d-flex justify-content-between">
                <span>
                  Knowledge graph
                  {knowledgeStats?.graph?.node_count != null
                    ? ` (${knowledgeStats.graph.node_count} nodes)`
                    : ""}
                </span>
                <AvailabilityBadge available={knowledge.graph} />
              </ListGroup.Item>
              {!knowledge.graph ? <UnavailableHint featureKey="graph" /> : null}
              <ListGroup.Item className="px-0 d-flex justify-content-between">
                <span>
                  IOC database
                  {knowledgeStats?.ioc_count != null
                    ? ` (${knowledgeStats.ioc_count} IOCs)`
                    : ""}
                </span>
                <AvailabilityBadge available={knowledge.ioc_db} />
              </ListGroup.Item>
              {!knowledge.ioc_db ? <UnavailableHint featureKey="ioc_db" /> : null}
            </ListGroup>
          </CapabilitySection>

          <CapabilitySection title="Benchmarks" icon={faChartBar}>
            <ListGroup variant="flush">
              <ListGroup.Item className="px-0">
                <div className="d-flex justify-content-between align-items-center">
                  <span>DFRWS datasets</span>
                  <AvailabilityBadge available={benchmarks.dfrws} />
                </div>
                {!benchmarks.dfrws ? <UnavailableHint featureKey="dfrws" /> : null}
              </ListGroup.Item>
              <ListGroup.Item className="px-0">
                <div className="d-flex justify-content-between align-items-center">
                  <span>CFReDS datasets</span>
                  <AvailabilityBadge available={benchmarks.cfreds} />
                </div>
                {!benchmarks.cfreds ? <UnavailableHint featureKey="cfreds" /> : null}
              </ListGroup.Item>
            </ListGroup>
          </CapabilitySection>

          <CapabilitySection title="ML Readiness" icon={faBrain}>
            <p className="text-muted small mb-0">
              ML capability flag:{" "}
              <AvailabilityBadge available={ai.ml} />
              {!ai.ml ? <UnavailableHint featureKey="ml" /> : null}
            </p>
          </CapabilitySection>
        </Row>
      )}
    </Container>
  );
}
