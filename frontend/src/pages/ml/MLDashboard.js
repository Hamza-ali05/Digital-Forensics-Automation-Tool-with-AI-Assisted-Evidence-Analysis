import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useHistory } from "react-router-dom";
import {
  Button,
  Card,
  Col,
  Container,
  Form,
  Modal,
  ProgressBar,
  Row,
} from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faBrain,
  faEye,
  faPlay,
  faSync,
} from "@fortawesome/free-solid-svg-icons";

import PageHeader from "components/common/PageHeader";
import DataTable from "components/common/DataTable";
import ApiErrorDisplay from "components/common/ApiErrorDisplay";
import EmptyState from "components/common/EmptyState";
import SkeletonLoader from "components/common/SkeletonLoader";
import StatusBadge from "components/common/StatusBadge";
import StatCard from "components/forensic/StatCard";
import { scoreToPercent } from "components/forensic/MetricGauge";
import { ML_EXPERIMENT_STATUS, ML_MODEL_NAMES } from "utils/constants";
import { formatDate } from "utils/formatters";
import useAuth from "hooks/useAuth";
import useNotification from "hooks/useNotification";
import usePolling from "hooks/usePolling";
import config from "config";
import datasetsService from "services/datasets.service";
import mlService from "services/ml.service";
import { Routes } from "routes";

const MODEL_OPTIONS = Object.values(ML_MODEL_NAMES).map((name) => ({
  value: name,
  label: name.replace(/([A-Z])/g, " $1").trim(),
}));

function metricValue(metrics, key) {
  const value = metrics?.[key];
  if (value == null) return "—";
  if (key.includes("accuracy") || key.includes("f1") || key.includes("precision") || key.includes("recall")) {
    return `${scoreToPercent(value)}%`;
  }
  return String(value);
}

/**
 * ML models hub with training form, progress polling, and experiment history.
 */
export default function MLDashboard() {
  const history = useHistory();
  const { role } = useAuth();
  const { success, error: notifyError } = useNotification();
  const isAdmin = role === "admin";

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [models, setModels] = useState([]);
  const [experiments, setExperiments] = useState([]);
  const [datasets, setDatasets] = useState([]);
  const [showTrainModal, setShowTrainModal] = useState(false);
  const [trainModel, setTrainModel] = useState(ML_MODEL_NAMES.MALWARE_CLASSIFIER);
  const [trainDatasets, setTrainDatasets] = useState([]);
  const [training, setTraining] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [modelRows, experimentRows, datasetRows] = await Promise.all([
        mlService.listModels(),
        mlService.listExperiments(),
        datasetsService.list().catch(() => []),
      ]);
      setModels(modelRows);
      setExperiments(experimentRows);
      setDatasets(Array.isArray(datasetRows) ? datasetRows : []);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const hasRunningExperiment = useMemo(
    () =>
      experiments.some(
        (item) =>
          String(item.status || "").toLowerCase() === ML_EXPERIMENT_STATUS.RUNNING
      ),
    [experiments]
  );

  const { data: polledExperiments } = usePolling(
    () => mlService.listExperiments(),
    config.pollingInterval || 5000,
    hasRunningExperiment || training
  );

  useEffect(() => {
    if (Array.isArray(polledExperiments)) {
      setExperiments(polledExperiments);
      if (
        training &&
        !polledExperiments.some(
          (item) =>
            String(item.status || "").toLowerCase() === ML_EXPERIMENT_STATUS.RUNNING
        )
      ) {
        setTraining(false);
        mlService.listModels().then(setModels).catch(() => {});
      }
    }
  }, [polledExperiments, training]);

  const handleTrain = async () => {
    setTraining(true);
    try {
      const result = await mlService.train({
        model_name: trainModel,
        source_datasets: trainDatasets.length ? trainDatasets : undefined,
      });
      success(
        "Training started",
        `${result.model_name} v${result.version} — check experiment history for progress.`
      );
      setShowTrainModal(false);
      await load();
    } catch (err) {
      setTraining(false);
      notifyError("Training failed", err?.message || "Unable to start training.");
    }
  };

  const modelColumns = useMemo(
    () => [
      {
        key: "model_name",
        header: "Model",
        render: (row) => (
          <Link
            to={Routes.ModelDetail.path.replace(":name", encodeURIComponent(row.model_name))}
          >
            {row.model_name}
          </Link>
        ),
      },
      { key: "version", header: "Version" },
      {
        key: "accuracy",
        header: "Accuracy",
        render: (row) =>
          metricValue(row.metrics, "accuracy") !== "—"
            ? metricValue(row.metrics, "accuracy")
            : metricValue(row.metrics, "test_accuracy"),
      },
      {
        key: "f1",
        header: "F1",
        render: (row) =>
          metricValue(row.metrics, "f1_score") !== "—"
            ? metricValue(row.metrics, "f1_score")
            : metricValue(row.metrics, "f1"),
      },
      {
        key: "trained_at",
        header: "Trained",
        render: (row) => formatDate(row.trained_at),
      },
      {
        key: "actions",
        header: "",
        render: (row) => (
          <Button
            size="sm"
            variant="outline-primary"
            onClick={() =>
              history.push(
                Routes.ModelDetail.path.replace(
                  ":name",
                  encodeURIComponent(row.model_name)
                )
              )
            }
          >
            <FontAwesomeIcon icon={faEye} className="me-1" />
            Details
          </Button>
        ),
      },
    ],
    [history]
  );

  const experimentColumns = useMemo(
    () => [
      { key: "experiment_id", header: "Experiment", render: (row) => String(row.experiment_id).slice(0, 8) },
      { key: "model_name", header: "Model" },
      { key: "dataset_name", header: "Dataset" },
      {
        key: "status",
        header: "Status",
        render: (row) => <StatusBadge status={row.status} type="ml_experiment" />,
      },
      {
        key: "metrics",
        header: "F1",
        render: (row) => metricValue(row.metrics, "f1_score"),
      },
      {
        key: "started_at",
        header: "Started",
        render: (row) => formatDate(row.started_at),
      },
      {
        key: "duration_seconds",
        header: "Duration",
        render: (row) =>
          row.duration_seconds != null ? `${Math.round(row.duration_seconds)}s` : "—",
      },
    ],
    []
  );

  if (loading && !models.length) {
    return (
      <Container fluid className="px-0">
        <SkeletonLoader type="dashboard" />
      </Container>
    );
  }

  return (
    <Container fluid className="px-0">
      <PageHeader
        title="Machine Learning"
        subtitle="Model registry, training, and experiment tracking"
        actions={
          <>
            <Button variant="outline-secondary" onClick={load}>
              <FontAwesomeIcon icon={faSync} className="me-2" />
              Refresh
            </Button>
            {isAdmin ? (
              <Button
                variant="primary"
                className="ms-2"
                onClick={() => setShowTrainModal(true)}
              >
                <FontAwesomeIcon icon={faPlay} className="me-2" />
                Train Model
              </Button>
            ) : null}
          </>
        }
      />

      {error ? <ApiErrorDisplay error={error} onRetry={load} className="mb-3" /> : null}

      {(training || hasRunningExperiment) ? (
        <Card border="light" className="shadow-sm mb-3">
          <Card.Body>
            <div className="d-flex justify-content-between align-items-center mb-2">
              <span className="fw-bold">Training in progress</span>
              <StatusBadge status={ML_EXPERIMENT_STATUS.RUNNING} type="ml_experiment" />
            </div>
            <ProgressBar animated now={100} variant="primary" />
            <div className="small text-muted mt-2">
              Polling experiment status every {Math.round((config.pollingInterval || 5000) / 1000)}s…
            </div>
          </Card.Body>
        </Card>
      ) : null}

      <Row className="g-3 mb-3">
        <Col xs={12} md={4}>
          <StatCard title="Trained Models" value={models.length} icon={faBrain} colour="primary" />
        </Col>
        <Col xs={12} md={4}>
          <StatCard
            title="Experiments"
            value={experiments.length}
            icon={faBrain}
            colour="info"
          />
        </Col>
        <Col xs={12} md={4}>
          <StatCard
            title="Running"
            value={
              experiments.filter(
                (item) =>
                  String(item.status || "").toLowerCase() === ML_EXPERIMENT_STATUS.RUNNING
              ).length
            }
            icon={faPlay}
            colour="warning"
          />
        </Col>
      </Row>

      <Card border="light" className="shadow-sm mb-3">
        <Card.Header>Trained Models</Card.Header>
        <Card.Body className="p-0">
          {models.length ? (
            <DataTable columns={modelColumns} data={models} keyField="model_id" />
          ) : (
            <EmptyState message="No trained models yet. Start training to register a model." />
          )}
        </Card.Body>
      </Card>

      <Card border="light" className="shadow-sm">
        <Card.Header>Experiment History</Card.Header>
        <Card.Body className="p-0">
          {experiments.length ? (
            <DataTable
              columns={experimentColumns}
              data={experiments}
              keyField="experiment_id"
            />
          ) : (
            <EmptyState message="No experiments recorded yet." />
          )}
        </Card.Body>
      </Card>

      <Modal show={showTrainModal} onHide={() => setShowTrainModal(false)} centered>
        <Modal.Header closeButton>
          <Modal.Title>Train Model</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Form.Group className="mb-3">
            <Form.Label>Model</Form.Label>
            <Form.Select
              value={trainModel}
              onChange={(e) => setTrainModel(e.target.value)}
            >
              {MODEL_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </Form.Select>
          </Form.Group>
          <Form.Group>
            <Form.Label>Source datasets (optional)</Form.Label>
            <Form.Select
              multiple
              htmlSize={Math.min(6, Math.max(3, datasets.length))}
              value={trainDatasets}
              onChange={(e) =>
                setTrainDatasets(
                  Array.from(e.target.selectedOptions, (option) => option.value)
                )
              }
            >
              {datasets.map((item) => (
                <option key={item.dataset_id} value={item.dataset_id}>
                  {item.name}
                </option>
              ))}
            </Form.Select>
            <Form.Text className="text-muted">
              Leave empty to use default training dataset selection.
            </Form.Text>
          </Form.Group>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="outline-secondary" onClick={() => setShowTrainModal(false)}>
            Cancel
          </Button>
          <Button variant="primary" onClick={handleTrain} disabled={training}>
            {training ? "Starting…" : "Start Training"}
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
}
