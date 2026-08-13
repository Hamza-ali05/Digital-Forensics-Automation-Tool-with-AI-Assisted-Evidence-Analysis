import React, { useMemo, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  Collapse,
  Col,
  Row,
} from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faCaretDown,
  faCaretRight,
  faDownload,
  faExclamationTriangle,
} from "@fortawesome/free-solid-svg-icons";

import ConfidenceMeter from "components/forensic/ConfidenceMeter";
import EmptyState from "components/common/EmptyState";
import { formatArtefactId } from "utils/formatters";
import { extractArtefacts } from "utils/artefactLoader";

const UUID_RE =
  /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi;
const ART_ID_RE = /\b(?:art|artefact)[-_][\w-]+\b/gi;

const SECTION_ALIASES = {
  "executive summary": "Executive Summary",
  "key findings": "Key Findings",
  timeline: "Timeline",
  "timeline of events": "Timeline",
  iocs: "IOCs",
  "indicators of compromise": "IOCs",
  "recommended actions": "Recommended Actions",
};

const DISPLAY_SECTIONS = [
  "Executive Summary",
  "Key Findings",
  "Timeline",
  "IOCs",
  "Recommended Actions",
];

export function parseNarrativeSections(markdown) {
  const text = String(markdown || "").replace(/\r\n/g, "\n");
  const parts = text.split(/^## /m);
  const map = {};
  parts.forEach((chunk) => {
    const trimmed = chunk.trim();
    if (!trimmed) return;
    const nl = trimmed.indexOf("\n");
    const title = (nl === -1 ? trimmed : trimmed.slice(0, nl)).trim();
    const body = nl === -1 ? "" : trimmed.slice(nl + 1).trim();
    const alias = SECTION_ALIASES[title.toLowerCase()];
    if (alias) map[alias] = body;
  });
  return map;
}

export function parseNarrativeMeta(markdown, jsonDoc) {
  const text = String(markdown || "");
  const model =
    (text.match(/\*\*Model:\*\*\s*(.+)/i) || [])[1] ||
    (text.match(/\|\s*LLM model\s*\|\s*([^|]+)\|/i) || [])[1] ||
    "";
  const prompt =
    (text.match(/\|\s*Prompt version\s*\|\s*([^|]+)\|/i) || [])[1] || "";
  const confidenceLine =
    (text.match(/\*\*Confidence:\*\*\s*([0-9.]+)\s*%/i) || [])[1] ||
    (text.match(/\|\s*Confidence\s*\|\s*([0-9.]+)\s*%/i) || [])[1] ||
    "";
  const score = Number(confidenceLine);
  const aiMeta = jsonDoc?.ai_metadata || {};
  return {
    model:
      model.trim() ||
      aiMeta.model_used ||
      aiMeta.model ||
      jsonDoc?.llm_model_used ||
      "—",
    promptVersion: prompt.trim() || aiMeta.prompt_version || "—",
    confidence:
      Number.isFinite(score)
        ? score / 100
        : aiMeta.confidence_score != null
          ? Number(aiMeta.confidence_score)
          : null,
  };
}

function LinkedNarrative({ text, artefactIds, onArtefactClick }) {
  const known = new Set((artefactIds || []).map(String));
  const source = String(text || "");
  if (!source) return <span className="text-muted">—</span>;

  const combined = new RegExp(`${UUID_RE.source}|${ART_ID_RE.source}`, "gi");
  const nodes = [];
  let last = 0;
  let match;
  let key = 0;
  combined.lastIndex = 0;
  while ((match = combined.exec(source)) !== null) {
    const id = match[0];
    if (match.index > last) nodes.push(source.slice(last, match.index));
    const recognised = known.size === 0 || known.has(id);
    if (recognised && typeof onArtefactClick === "function") {
      nodes.push(
        <Button
          key={`art-${key++}`}
          variant="link"
          size="sm"
          className="p-0 align-baseline"
          onClick={() => onArtefactClick(id)}
        >
          {formatArtefactId(id)}
        </Button>
      );
    } else {
      nodes.push(id);
    }
    last = match.index + id.length;
  }
  if (last < source.length) nodes.push(source.slice(last));
  return (
    <div style={{ whiteSpace: "pre-wrap" }} className="small">
      {nodes}
    </div>
  );
}

function SectionCard({ title, body, artefactIds, onArtefactClick, defaultOpen }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Card border="light" className="shadow-sm mb-3">
      <Card.Header
        className="d-flex justify-content-between align-items-center"
        style={{ cursor: "pointer" }}
        onClick={() => setOpen((prev) => !prev)}
      >
        <h6 className="mb-0">{title}</h6>
        <FontAwesomeIcon icon={open ? faCaretDown : faCaretRight} />
      </Card.Header>
      <Collapse in={open}>
        <div>
          <Card.Body>
            <LinkedNarrative
              text={body}
              artefactIds={artefactIds}
              onArtefactClick={onArtefactClick}
            />
          </Card.Body>
        </div>
      </Collapse>
    </Card>
  );
}

/**
 * Collapsible investigative narrative with disclaimer and artefact ID links.
 */
export default function NarrativeSummary({
  narrative,
  jsonDoc,
  onArtefactClick,
  showDownload = false,
  onDownload,
  reportId,
}) {
  const artefacts = useMemo(() => extractArtefacts(jsonDoc), [jsonDoc]);
  const artefactIds = useMemo(
    () => artefacts.map((item) => item.artefact_id).filter(Boolean),
    [artefacts]
  );
  const sections = useMemo(() => parseNarrativeSections(narrative), [narrative]);
  const meta = useMemo(
    () => parseNarrativeMeta(narrative, jsonDoc),
    [narrative, jsonDoc]
  );

  if (!narrative) {
    return (
      <EmptyState
        title="No narrative available"
        description="This report does not include an investigative summary yet."
      />
    );
  }

  return (
    <>
      <Alert variant="danger" className="mb-4">
        <FontAwesomeIcon icon={faExclamationTriangle} className="me-2" />
        LLM Disclaimer: AI-generated analysis uses base LLaMA-3 and should be
        verified against the structured JSON artefact data. This narrative is
        advisory only and is not the evidential record (Scanlon et al., 2023).
      </Alert>

      <Card border="light" className="shadow-sm mb-4">
        <Card.Body>
          <Row className="g-3 align-items-center">
            <Col xs={12} md={4}>
              {meta.confidence != null ? (
                <ConfidenceMeter score={meta.confidence} />
              ) : (
                <span className="text-muted small">Confidence not recorded</span>
              )}
            </Col>
            <Col xs={12} md={4}>
              <div className="small text-muted text-uppercase fw-bold">Model</div>
              <div>{meta.model}</div>
            </Col>
            <Col xs={12} md={4}>
              <div className="small text-muted text-uppercase fw-bold">
                Prompt version
              </div>
              <Badge bg="light" text="dark">
                {meta.promptVersion}
              </Badge>
            </Col>
          </Row>
        </Card.Body>
      </Card>

      {DISPLAY_SECTIONS.map((title, index) => (
        <SectionCard
          key={title}
          title={title}
          body={sections[title] || "_No content in this section._"}
          artefactIds={artefactIds}
          onArtefactClick={onArtefactClick}
          defaultOpen={index === 0}
        />
      ))}

      {showDownload ? (
        <div className="d-flex flex-wrap gap-2 mt-2 mb-2">
          <Button
            variant="outline-primary"
            onClick={() => onDownload && onDownload(narrative, reportId)}
          >
            <FontAwesomeIcon icon={faDownload} className="me-2" />
            Download Summary as Text
          </Button>
        </div>
      ) : null}
    </>
  );
}
