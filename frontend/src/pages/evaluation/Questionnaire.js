import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Collapse,
  Form,
  Spinner,
} from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faCaretDown,
  faCaretRight,
  faCheckCircle,
  faUniversity,
} from "@fortawesome/free-solid-svg-icons";

import ApiErrorDisplay from "components/common/ApiErrorDisplay";
import SkeletonLoader from "components/common/SkeletonLoader";
import evaluationService from "services/evaluation.service";
import usePageTitle from "hooks/usePageTitle";

const MAX_FREE_TEXT = 1000;

const LIKERT_POINTS = [
  { value: 1, caption: "Strongly Disagree" },
  { value: 2, caption: "2" },
  { value: 3, caption: "Neutral" },
  { value: 4, caption: "4" },
  { value: 5, caption: "Strongly Agree" },
];

/** Ethics-locked fallback matching ``QuestionnaireInstrument.QUESTIONS``. */
const FALLBACK_QUESTIONS = [
  {
    id: "Q1",
    text: "How useful was the tool's output for identifying key evidence?",
    type: "likert",
  },
  {
    id: "Q2",
    text:
      "How accurate were the identified artefacts compared to your manual analysis?",
    type: "likert",
  },
  {
    id: "Q3",
    text: "How clear and readable was the investigative summary?",
    type: "likert",
  },
  {
    id: "Q4",
    text: "Would you use this tool in a real forensic investigation?",
    type: "likert",
  },
  {
    id: "Q5",
    text: "How does the tool's output compare to manual triage methods?",
    type: "likert",
  },
  {
    id: "Q6",
    text:
      "Please provide any additional feedback on the tool's strengths or weaknesses.",
    type: "open",
    scale: "free_text",
  },
];

function isLikert(question) {
  const type = String(question?.type || "").toLowerCase();
  const scale = String(question?.scale || "").toLowerCase();
  if (type === "open" || scale === "free_text") return false;
  return type === "likert" || scale === "1-5" || /^q[1-5]$/i.test(question?.id);
}

function isOpen(question) {
  return !isLikert(question);
}

function LikertScale({ questionId, labelledBy, value, invalid, onChange }) {
  return (
    <fieldset className="border-0 p-0 m-0" aria-labelledby={labelledBy}>
      <legend className="visually-hidden">
        5-point agreement scale for {questionId}
      </legend>
      <div className="d-flex justify-content-between small text-muted mb-2 px-1">
        {LIKERT_POINTS.map((point) => (
          <span
            key={point.value}
            className="text-center"
            style={{ width: "20%" }}
          >
            {point.value === 1
              ? "1 (Strongly Disagree)"
              : point.value === 3
                ? "3 (Neutral)"
                : point.value === 5
                  ? "5 (Strongly Agree)"
                  : String(point.value)}
          </span>
        ))}
      </div>
      <div
        className={`d-flex justify-content-between px-1 ${
          invalid ? "is-invalid" : ""
        }`}
      >
        {LIKERT_POINTS.map((point) => (
          <div
            key={point.value}
            className="text-center"
            style={{ width: "20%" }}
          >
            <Form.Check
              type="radio"
              id={`${questionId}-${point.value}`}
              name={questionId}
              value={point.value}
              checked={Number(value) === point.value}
              onChange={() => onChange(point.value)}
              aria-label={`${questionId}: ${point.value} ${
                point.caption
              }`}
              className="d-flex justify-content-center"
            />
          </div>
        ))}
      </div>
      {invalid ? (
        <div className="invalid-feedback d-block">
          Please select a rating from 1 to 5.
        </div>
      ) : null}
    </fieldset>
  );
}

/**
 * Public ethics-approved usability questionnaire — no authentication.
 */
export default function Questionnaire() {
  usePageTitle("Usability questionnaire");
  const [infoOpen, setInfoOpen] = useState(true);
  const [questions, setQuestions] = useState(FALLBACK_QUESTIONS);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [ratings, setRatings] = useState({});
  const [freeText, setFreeText] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [submitError, setSubmitError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [participantId, setParticipantId] = useState(null);

  const loadInstrument = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const payload = await evaluationService.getQuestionnaire();
      const list = payload?.questions || payload?.instrument?.questions;
      if (Array.isArray(list) && list.length) {
        setQuestions(list);
      } else {
        setQuestions(FALLBACK_QUESTIONS);
      }
    } catch (err) {
      setLoadError(err);
      setQuestions(FALLBACK_QUESTIONS);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadInstrument().catch(() => {});
  }, [loadInstrument]);

  const likertQuestions = useMemo(
    () => questions.filter(isLikert),
    [questions]
  );
  const openQuestion = useMemo(
    () => questions.find(isOpen) || FALLBACK_QUESTIONS[5],
    [questions]
  );

  const setRating = (id, value) => {
    setRatings((prev) => ({ ...prev, [id]: value }));
    setFieldErrors((prev) => {
      if (!prev[id]) return prev;
      const next = { ...prev };
      delete next[id];
      return next;
    });
  };

  const handleFreeText = (event) => {
    const next = event.target.value.slice(0, MAX_FREE_TEXT);
    setFreeText(next);
  };

  const validate = () => {
    const next = {};
    likertQuestions.forEach((question) => {
      const value = Number(ratings[question.id]);
      if (!Number.isInteger(value) || value < 1 || value > 5) {
        next[question.id] = true;
      }
    });
    setFieldErrors(next);
    return Object.keys(next).length === 0;
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSubmitError(null);
    if (!validate()) return;

    const payload = { ratings: {} };
    likertQuestions.forEach((question) => {
      payload.ratings[question.id] = Number(ratings[question.id]);
    });
    const trimmed = freeText.trim();
    if (trimmed) payload.free_text = trimmed;

    setSubmitting(true);
    try {
      const result = await evaluationService.submitQuestionnaire(payload);
      setParticipantId(result?.participant_id || result?.participantId || "");
    } catch (err) {
      setSubmitError(err);
    } finally {
      setSubmitting(false);
    }
  };

  if (typeof participantId === "string") {
    return (
      <Card border="light" className="shadow-sm mx-auto" style={{ maxWidth: 720 }}>
        <Card.Body className="text-center py-5 px-4">
          <FontAwesomeIcon
            icon={faCheckCircle}
            className="text-success mb-3"
            size="3x"
          />
          <h2 className="h4 mb-3">Thank you</h2>
          <p className="mb-3">
            Your anonymous response has been recorded. Participant ID:{" "}
            <code>{participantId || "—"}</code>
          </p>
          <p className="text-muted mb-0">You may close this page.</p>
        </Card.Body>
      </Card>
    );
  }

  return (
    <div className="mx-auto" style={{ maxWidth: 800 }}>
      <header className="text-center mb-4">
        <div className="text-primary mb-2">
          <FontAwesomeIcon icon={faUniversity} size="2x" aria-hidden="true" />
        </div>
        <h1 className="h3 mb-1">DFAT Usability Assessment</h1>
        <p className="text-muted mb-0">Canterbury Christ Church University</p>
      </header>

      <Card border="light" className="shadow-sm mb-4">
        <Card.Header className="p-0">
          <button
            type="button"
            className="btn btn-link text-decoration-none text-dark w-100 d-flex justify-content-between align-items-center px-3 py-2"
            onClick={() => setInfoOpen((prev) => !prev)}
            aria-expanded={infoOpen}
            aria-controls="participant-info"
          >
            <span className="h5 mb-0">Participant information</span>
            <FontAwesomeIcon
              icon={infoOpen ? faCaretDown : faCaretRight}
              aria-hidden="true"
            />
          </button>
        </Card.Header>
        <Collapse in={infoOpen}>
          <div id="participant-info">
            <Card.Body>
              <p>
                You are invited to evaluate the Digital Forensics Automation Tool
                (DFAT). Your responses are anonymous and will be used for academic
                research only. Participation is voluntary and you may withdraw at
                any time. No personally identifiable information is collected.
              </p>
              <p className="mb-0 fw-semibold">
                By submitting this form, you consent to participate in this study.
              </p>
            </Card.Body>
          </div>
        </Collapse>
      </Card>

      {loadError ? (
        <ApiErrorDisplay
          error={loadError}
          onRetry={loadInstrument}
          className="mb-3"
        />
      ) : null}

      {loading ? (
        <SkeletonLoader type="detail" rows={6} />
      ) : (
        <Form onSubmit={handleSubmit} noValidate>
          {submitError ? (
            <Alert variant="danger" className="mb-4">
              <div className="fw-bold mb-1">Submission failed</div>
              <div className="small mb-2">
                {submitError.message ||
                  "Your response could not be recorded. Please try again."}
              </div>
              <Button
                variant="outline-danger"
                size="sm"
                onClick={handleSubmit}
                disabled={submitting}
              >
                Retry
              </Button>
            </Alert>
          ) : null}

          {likertQuestions.map((question) => (
            <Card key={question.id} border="light" className="shadow-sm mb-3">
              <Card.Body>
                <div className="small text-muted text-uppercase fw-bold mb-1">
                  {question.id}
                </div>
                <p id={`${question.id}-text`} className="fs-5 mb-3">
                  {question.text}
                </p>
                <LikertScale
                  questionId={question.id}
                  labelledBy={`${question.id}-text`}
                  value={ratings[question.id]}
                  invalid={Boolean(fieldErrors[question.id])}
                  onChange={(value) => setRating(question.id, value)}
                />
              </Card.Body>
            </Card>
          ))}

          {openQuestion ? (
            <Card border="light" className="shadow-sm mb-4">
              <Card.Body>
                <div className="small text-muted text-uppercase fw-bold mb-1">
                  {openQuestion.id}
                </div>
                <p id={`${openQuestion.id}-text`} className="fs-5 mb-3">
                  {openQuestion.text}
                </p>
                <Form.Group>
                  <Form.Label htmlFor="questionnaire-feedback" className="visually-hidden">
                    Additional feedback
                  </Form.Label>
                  <Form.Control
                    id="questionnaire-feedback"
                    as="textarea"
                    rows={5}
                    maxLength={MAX_FREE_TEXT}
                    value={freeText}
                    onChange={handleFreeText}
                    placeholder="Optional comments"
                    aria-labelledby={`${openQuestion.id}-text`}
                  />
                  <div className="d-flex justify-content-between mt-2">
                    <Form.Text>Your response is anonymous</Form.Text>
                    <Form.Text>
                      {freeText.length} / {MAX_FREE_TEXT}
                    </Form.Text>
                  </div>
                </Form.Group>
              </Card.Body>
            </Card>
          ) : null}

          <div className="d-grid">
            <Button type="submit" variant="primary" size="lg" disabled={submitting}>
              {submitting ? (
                <>
                  <Spinner animation="border" size="sm" className="me-2" />
                  Submitting…
                </>
              ) : (
                "Submit anonymous response"
              )}
            </Button>
          </div>
        </Form>
      )}
    </div>
  );
}
