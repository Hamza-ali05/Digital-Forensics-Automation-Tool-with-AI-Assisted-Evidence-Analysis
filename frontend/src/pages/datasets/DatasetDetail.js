import React, { useCallback, useEffect, useState } from "react";
import { Link, useHistory, useParams } from "react-router-dom";
import {
  Badge,
  Button,
  Card,
  Col,
  Container,
  ListGroup,
  Row,
} from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faArrowLeft,
  faHistory,
  faSync,
  faTrash,
} from "@fortawesome/free-solid-svg-icons";

import PageHeader from "components/common/PageHeader";
import ApiErrorDisplay from "components/common/ApiErrorDisplay";
import ConfirmDialog from "components/common/ConfirmDialog";
import SkeletonLoader from "components/common/SkeletonLoader";
import StatusBadge from "components/common/StatusBadge";
import { formatBytes, formatDate, formatHash } from "utils/formatters";
import useAuth from "hooks/useAuth";
import useNotification from "hooks/useNotification";
import datasetsService from "services/datasets.service";
import { Routes } from "routes";

function labelize(value) {
  if (!value) return "—";
  return String(value)
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Single dataset detail with metadata, history, and admin actions.
 */
export default function DatasetDetail() {
  const { id: datasetId } = useParams();
  const history = useHistory();
  const { role } = useAuth();
  const { success, error: notifyError } = useNotification();
  const isAdmin = role === "admin";

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [dataset, setDataset] = useState(null);
  const [busy, setBusy] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const detail = await datasetsService.getById(datasetId);
      setDataset(detail);
    } catch (err) {
      setError(err);
      setDataset(null);
    } finally {
      setLoading(false);
    }
  }, [datasetId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleReindex = async () => {
    setBusy("reindex");
    try {
      const result = await datasetsService.reindex(datasetId);
      success("Re-index started", result.message || "Dataset re-indexed.");
      await load();
    } catch (err) {
      notifyError("Re-index failed", err?.message || "Unable to re-index dataset.");
    } finally {
      setBusy(null);
    }
  };

  const handleRefresh = async () => {
    setBusy("refresh");
    try {
      const updated = await datasetsService.refresh(datasetId);
      setDataset(updated);
      success("Dataset refreshed", "Validation and preprocessing completed.");
    } catch (err) {
      notifyError("Refresh failed", err?.message || "Unable to refresh dataset.");
    } finally {
      setBusy(null);
    }
  };

  const handleDelete = async () => {
    setBusy("delete");
    try {
      await datasetsService.remove(datasetId);
      success("Dataset removed", "Dataset removed from registry.");
      history.push(Routes.Datasets.path);
    } catch (err) {
      notifyError("Delete failed", err?.message || "Unable to remove dataset.");
    } finally {
      setBusy(null);
      setConfirmDelete(false);
    }
  };

  if (loading) {
    return (
      <Container fluid className="px-0">
        <SkeletonLoader type="detail" />
      </Container>
    );
  }

  if (error && !dataset) {
    return (
      <Container fluid className="px-0">
        <ApiErrorDisplay error={error} onRetry={load} />
        <Button
          as={Link}
          to={Routes.Datasets.path}
          variant="outline-secondary"
          className="mt-3"
        >
          <FontAwesomeIcon icon={faArrowLeft} className="me-2" />
          Back to datasets
        </Button>
      </Container>
    );
  }

  const objectives = dataset.associated_research_objectives || [];
  const modules = dataset.supported_forensic_modules || [];
  const historySteps = dataset.preprocessing_history || [];

  return (
    <Container fluid className="px-0">
      <PageHeader
        title={dataset.name}
        subtitle={`Dataset ${dataset.dataset_id}`}
        breadcrumbs={[
          { label: "Home", to: Routes.Dashboard.path },
          { label: "Datasets", to: Routes.Datasets.path },
          { label: dataset.name },
        ]}
        actions={
          <>
            {isAdmin ? (
              <>
                <Button
                  size="sm"
                  variant="outline-primary"
                  onClick={handleReindex}
                  disabled={busy === "reindex"}
                >
                  Re-index
                </Button>
                <Button
                  size="sm"
                  variant="outline-success"
                  onClick={handleRefresh}
                  disabled={busy === "refresh"}
                  className="ms-2"
                >
                  <FontAwesomeIcon icon={faSync} className="me-1" />
                  Refresh
                </Button>
                <Button
                  size="sm"
                  variant="outline-danger"
                  onClick={() => setConfirmDelete(true)}
                  disabled={busy === "delete"}
                  className="ms-2"
                >
                  <FontAwesomeIcon icon={faTrash} className="me-1" />
                  Remove
                </Button>
              </>
            ) : null}
          </>
        }
      />

      <Row className="g-3">
        <Col xs={12} lg={6}>
          <Card border="light" className="shadow-sm h-100">
            <Card.Header>Metadata</Card.Header>
            <Card.Body>
              <ListGroup variant="flush">
                <ListGroup.Item className="d-flex justify-content-between">
                  <span className="text-muted">Category</span>
                  <Badge bg="light" text="dark">{labelize(dataset.category)}</Badge>
                </ListGroup.Item>
                <ListGroup.Item className="d-flex justify-content-between">
                  <span className="text-muted">Format</span>
                  <span>{labelize(dataset.format)}</span>
                </ListGroup.Item>
                <ListGroup.Item className="d-flex justify-content-between">
                  <span className="text-muted">Status</span>
                  <StatusBadge status={dataset.status} type="dataset" />
                </ListGroup.Item>
                <ListGroup.Item className="d-flex justify-content-between">
                  <span className="text-muted">Indexing</span>
                  <StatusBadge status={dataset.indexing_status} type="indexing" />
                </ListGroup.Item>
                <ListGroup.Item className="d-flex justify-content-between">
                  <span className="text-muted">Size</span>
                  <span>{formatBytes(dataset.file_size_bytes)}</span>
                </ListGroup.Item>
                <ListGroup.Item className="d-flex justify-content-between">
                  <span className="text-muted">SHA-256</span>
                  <code className="small">{formatHash(dataset.hash_sha256, 16)}</code>
                </ListGroup.Item>
                <ListGroup.Item className="d-flex justify-content-between">
                  <span className="text-muted">Discovered</span>
                  <span>{formatDate(dataset.discovered_at)}</span>
                </ListGroup.Item>
                <ListGroup.Item className="d-flex justify-content-between">
                  <span className="text-muted">Validated</span>
                  <span>{dataset.validated_at ? formatDate(dataset.validated_at) : "—"}</span>
                </ListGroup.Item>
                <ListGroup.Item className="d-flex justify-content-between">
                  <span className="text-muted">Indexed</span>
                  <span>{dataset.indexed_at ? formatDate(dataset.indexed_at) : "—"}</span>
                </ListGroup.Item>
                <ListGroup.Item>
                  <span className="text-muted d-block mb-1">Path</span>
                  <code className="small">{dataset.file_path}</code>
                </ListGroup.Item>
                {dataset.tags?.length ? (
                  <ListGroup.Item>
                    <span className="text-muted d-block mb-1">Tags</span>
                    {dataset.tags.map((tag) => (
                      <Badge key={tag} bg="secondary" className="me-1">
                        {tag}
                      </Badge>
                    ))}
                  </ListGroup.Item>
                ) : null}
              </ListGroup>
            </Card.Body>
          </Card>
        </Col>

        <Col xs={12} lg={6}>
          <Card border="light" className="shadow-sm mb-3">
            <Card.Header>
              <FontAwesomeIcon icon={faHistory} className="me-2" />
              Preprocessing History
            </Card.Header>
            <Card.Body>
              {historySteps.length ? (
                <ListGroup variant="flush">
                  {historySteps.map((step, index) => (
                    <ListGroup.Item key={`${index}-${step.step || step.action || "step"}`}>
                      <div className="fw-bold">{labelize(step.step || step.action || "Step")}</div>
                      {step.timestamp ? (
                        <div className="small text-muted">{formatDate(step.timestamp)}</div>
                      ) : null}
                      {step.notes ? <div className="small">{step.notes}</div> : null}
                    </ListGroup.Item>
                  ))}
                </ListGroup>
              ) : (
                <p className="text-muted mb-0 small">No preprocessing history recorded.</p>
              )}
            </Card.Body>
          </Card>

          <Card border="light" className="shadow-sm mb-3">
            <Card.Header>Research Objectives</Card.Header>
            <Card.Body>
              {objectives.length ? (
                objectives.map((item) => (
                  <Badge key={item} bg="info" className="me-1 mb-1">
                    {item}
                  </Badge>
                ))
              ) : (
                <p className="text-muted mb-0 small">No mapped research objectives.</p>
              )}
            </Card.Body>
          </Card>

          <Card border="light" className="shadow-sm">
            <Card.Header>Supported Modules</Card.Header>
            <Card.Body>
              {modules.length ? (
                modules.map((item) => (
                  <Badge key={item} bg="primary" className="me-1 mb-1">
                    {item}
                  </Badge>
                ))
              ) : (
                <p className="text-muted mb-0 small">No supported modules inferred.</p>
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      <ConfirmDialog
        show={confirmDelete}
        title="Remove dataset"
        message="Remove this dataset from the registry? The source file will not be deleted."
        confirmLabel="Remove"
        variant="danger"
        onConfirm={handleDelete}
        onCancel={() => setConfirmDelete(false)}
        loading={busy === "delete"}
      />
    </Container>
  );
}
