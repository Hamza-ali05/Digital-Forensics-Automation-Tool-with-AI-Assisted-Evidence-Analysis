import React, { useEffect, useRef, useState } from "react";
import {
  Badge,
  Button,
  Form,
  InputGroup,
  Spinner,
} from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faCheckCircle,
  faExclamationTriangle,
  faPaperPlane,
} from "@fortawesome/free-solid-svg-icons";

import ConfidenceMeter from "components/forensic/ConfidenceMeter";
import { formatArtefactId } from "utils/formatters";

function hallucinationPassed(check) {
  if (!check) return true;
  const risk = String(check.risk_level || "low").toLowerCase();
  const ids = check.hallucinated_ids || [];
  const terms = check.fabricated_terms || [];
  return risk === "low" && ids.length === 0 && terms.length === 0;
}

function MessageBubble({ message, onArtefactClick }) {
  const isUser = message.role === "user";
  const text = message.content || message.text || message.answer || "";
  const ids = message.referenced_artefact_ids || [];
  const check = message.hallucination_check;
  const passed = hallucinationPassed(check);

  return (
    <div
      className={`d-flex mb-3 ${isUser ? "justify-content-end" : "justify-content-start"}`}
    >
      <div
        className={`p-3 rounded shadow-sm ${
          isUser ? "bg-primary text-white" : "bg-white border"
        }`}
        style={{ maxWidth: "85%" }}
      >
        <div className="small fw-bold mb-1 opacity-75">
          {isUser ? "Investigator" : "AI Assistant"}
        </div>
        <div style={{ whiteSpace: "pre-wrap" }}>{text}</div>

        {!isUser ? (
          <div className="mt-3">
            {message.confidence != null ? (
              <ConfidenceMeter score={message.confidence} className="mb-2" />
            ) : null}

            {ids.length ? (
              <div className="mb-2">
                <div className="small text-muted mb-1">Referenced artefacts</div>
                <div className="d-flex flex-wrap gap-1">
                  {ids.map((id) => (
                    <Button
                      key={id}
                      size="sm"
                      variant="outline-secondary"
                      onClick={() => onArtefactClick && onArtefactClick(id)}
                    >
                      {formatArtefactId(id)}
                    </Button>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="small d-flex align-items-center">
              {passed ? (
                <>
                  <FontAwesomeIcon
                    icon={faCheckCircle}
                    className="text-success me-2"
                  />
                  <span className="text-success">Hallucination check passed</span>
                </>
              ) : (
                <>
                  <FontAwesomeIcon
                    icon={faExclamationTriangle}
                    className="text-warning me-2"
                  />
                  <span className="text-warning">
                    Hallucination warning
                    {check?.risk_level
                      ? ` (${String(check.risk_level).toLowerCase()} risk)`
                      : ""}
                  </span>
                </>
              )}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

/**
 * Reusable investigator / AI chat surface.
 *
 * @param {{
 *   messages?: object[],
 *   onSend?: (text: string) => void,
 *   loading?: boolean,
 *   suggestions?: string[],
 *   placeholder?: string,
 *   disabled?: boolean,
 *   onArtefactClick?: (artefactId: string) => void,
 * }} props
 */
export default function ChatInterface({
  messages = [],
  onSend,
  loading = false,
  suggestions = [],
  placeholder = "Ask a question about the evidence...",
  disabled = false,
  onArtefactClick,
}) {
  const [draft, setDraft] = useState("");
  const endRef = useRef(null);

  useEffect(() => {
    if (endRef.current) {
      endRef.current.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [messages, loading]);

  const submit = (text) => {
    const value = String(text || "").trim();
    if (!value || loading || disabled || typeof onSend !== "function") return;
    onSend(value);
    setDraft("");
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    submit(draft);
  };

  return (
    <div className="dfat-chat-interface">
      <div
        className="bg-light rounded p-3 mb-3"
        style={{ minHeight: 220, maxHeight: 420, overflowY: "auto" }}
      >
        {messages.length === 0 && !loading ? (
          <p className="text-muted small mb-0 text-center py-4">
            Ask a question to start an investigation conversation.
          </p>
        ) : (
          messages.map((message, index) => (
            <MessageBubble
              key={message.id || `${message.role}-${index}`}
              message={message}
              onArtefactClick={onArtefactClick}
            />
          ))
        )}
        {loading ? (
          <div className="d-flex align-items-center text-muted small">
            <Spinner animation="border" size="sm" className="me-2" />
            Generating answer…
          </div>
        ) : null}
        <div ref={endRef} />
      </div>

      {suggestions.length ? (
        <div className="mb-3">
          <div className="small text-muted text-uppercase fw-bold mb-2">
            Suggested questions
          </div>
          <div className="d-flex flex-wrap gap-2">
            {suggestions.map((question) => (
              <Badge
                key={question}
                as="button"
                bg="light"
                text="dark"
                className="border text-start"
                style={{ cursor: disabled || loading ? "not-allowed" : "pointer" }}
                onClick={() => submit(question)}
              >
                {question}
              </Badge>
            ))}
          </div>
        </div>
      ) : null}

      <Form onSubmit={handleSubmit}>
        <InputGroup>
          <Form.Control
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder={placeholder}
            disabled={disabled || loading}
            aria-label="Ask a question about the evidence"
          />
          <Button
            type="submit"
            variant="primary"
            disabled={disabled || loading || !draft.trim()}
          >
            {loading ? (
              <Spinner animation="border" size="sm" />
            ) : (
              <FontAwesomeIcon icon={faPaperPlane} />
            )}
            <span className="ms-2">Send</span>
          </Button>
        </InputGroup>
      </Form>
    </div>
  );
}
