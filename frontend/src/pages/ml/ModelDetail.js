import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  Badge,
  Card,
  Col,
  Container,
  ListGroup,
  Row,
  Table,
} from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faArrowLeft,
  faBrain,
} from "@fortawesome/free-solid-svg-icons";
import {
  Chart as ChartJS,
  BarElement,
  CategoryScale,
  LinearScale,
  Legend,
  Tooltip,
} from "chart.js";
import { Bar } from "react-chartjs-2";

import PageHeader from "components/common/PageHeader";
import ApiErrorDisplay from "components/common/ApiErrorDisplay";
import EmptyState from "components/common/EmptyState";
import MetricGauge, { scoreToPercent } from "components/forensic/MetricGauge";
import SkeletonLoader from "components/common/SkeletonLoader";
import { formatDate } from "utils/formatters";
import mlService from "services/ml.service";
import { Routes } from "routes";

ChartJS.register(BarElement, CategoryScale, LinearScale, Legend, Tooltip);

function pickMetric(metrics, keys) {
  for (const key of keys) {
    if (metrics?.[key] != null) return metrics[key];
  }
  return null;
}

function formatMetric(metrics, keys) {
  const value = pickMetric(metrics, keys);
  if (value == null) return "—";
  return `${scoreToPercent(value)}%`;
}

/**
 * Trained model detail with metrics, feature importance, and version comparison.
 */
export default function ModelDetail() {
  const { name: modelName } = useParams();
  const decodedName = decodeURIComponent(modelName);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [model, setModel] = useState(null);
  const [allVersions, setAllVersions] = useState([]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [latest, versions] = await Promise.all([
        mlService.getLatestModel(decodedName),
        mlService.listModels(),
      ]);
      setModel(latest);
      setAllVersions(
        versions.filter((item) => item.model_name === decodedName)
      );
    } catch (err) {
      setError(err);
      setModel(null);
    } finally {
      setLoading(false);
    }
  }, [decodedName]);

  useEffect(() => {
    load();
  }, [load]);

  const featureChart = useMemo(() => {
    const importance = model?.feature_importance || {};
    const entries = Object.entries(importance).slice(0, 12);
    if (!entries.length && model?.feature_names?.length) {
      return {
        labels: model.feature_names.slice(0, 12),
        datasets: [
          {
            label: "Features",
            data: model.feature_names.slice(0, 12).map(() => 1),
            backgroundColor: "#0d6efd",
          },
        ],
      };
    }
    return {
      labels: entries.map(([name]) => name),
      datasets: [
        {
          label: "Importance",
          data: entries.map(([, value]) => Number(value) || 0),
          backgroundColor: "#198754",
        },
      ],
    };
  }, [model]);

  if (loading) {
    return (
      <Container fluid className="px-0">
        <SkeletonLoader type="detail" />
      </Container>
    );
  }

  if (error && !model) {
    return (
      <Container fluid className="px-0">
        <ApiErrorDisplay error={error} onRetry={load} />
        <Link to={Routes.MLModels.path} className="btn btn-outline-secondary mt-3">
          <FontAwesomeIcon icon={faArrowLeft} className="me-2" />
          Back to ML
        </Link>
      </Container>
    );
  }

  const metrics = model.metrics || {};
  const precision = pickMetric(metrics, ["precision", "test_precision"]);
  const recall = pickMetric(metrics, ["recall", "test_recall"]);
  const f1 = pickMetric(metrics, ["f1_score", "f1", "test_f1"]);

  return (
    <Container fluid className="px-0">
      <PageHeader
        title={decodedName}
        subtitle={`Version ${model.version}`}
      />

      <Row className="g-3 mb-3">
        <Col xs={12} md={4}>
          <Card border="light" className="shadow-sm h-100 text-center">
            <Card.Body>
              <MetricGauge
                value={scoreToPercent(precision)}
                label="Precision"
                display={formatMetric(metrics, ["precision", "test_precision"])}
              />
            </Card.Body>
          </Card>
        </Col>
        <Col xs={12} md={4}>
          <Card border="light" className="shadow-sm h-100 text-center">
            <Card.Body>
              <MetricGauge
                value={scoreToPercent(recall)}
                label="Recall"
                display={formatMetric(metrics, ["recall", "test_recall"])}
              />
            </Card.Body>
          </Card>
        </Col>
        <Col xs={12} md={4}>
          <Card border="light" className="shadow-sm h-100 text-center">
            <Card.Body>
              <MetricGauge
                value={scoreToPercent(f1)}
                label="F1 Score"
                display={formatMetric(metrics, ["f1_score", "f1", "test_f1"])}
              />
            </Card.Body>
          </Card>
        </Col>
      </Row>

      <Row className="g-3">
        <Col xs={12} lg={5}>
          <Card border="light" className="shadow-sm mb-3">
            <Card.Header>
              <FontAwesomeIcon icon={faBrain} className="me-2" />
              Model Metadata
            </Card.Header>
            <Card.Body>
              <ListGroup variant="flush">
                <ListGroup.Item className="d-flex justify-content-between">
                  <span className="text-muted">Model ID</span>
                  <code className="small">{model.model_id}</code>
                </ListGroup.Item>
                <ListGroup.Item className="d-flex justify-content-between">
                  <span className="text-muted">Version</span>
                  <Badge bg="primary">{model.version}</Badge>
                </ListGroup.Item>
                <ListGroup.Item className="d-flex justify-content-between">
                  <span className="text-muted">Trained</span>
                  <span>{formatDate(model.trained_at)}</span>
                </ListGroup.Item>
                <ListGroup.Item className="d-flex justify-content-between">
                  <span className="text-muted">Training dataset</span>
                  <span>{model.training_dataset || "—"}</span>
                </ListGroup.Item>
                <ListGroup.Item>
                  <span className="text-muted d-block mb-1">Model path</span>
                  <code className="small">{model.model_path}</code>
                </ListGroup.Item>
              </ListGroup>
            </Card.Body>
          </Card>

          <Card border="light" className="shadow-sm">
            <Card.Header>Hyperparameters</Card.Header>
            <Card.Body>
              {Object.keys(model.hyperparameters || {}).length ? (
                <Table size="sm" responsive className="mb-0">
                  <tbody>
                    {Object.entries(model.hyperparameters).map(([key, value]) => (
                      <tr key={key}>
                        <td className="text-muted">{key}</td>
                        <td>{String(value)}</td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              ) : (
                <p className="text-muted mb-0 small">No hyperparameters recorded.</p>
              )}
            </Card.Body>
          </Card>
        </Col>

        <Col xs={12} lg={7}>
          <Card border="light" className="shadow-sm mb-3">
            <Card.Header>Feature Importance</Card.Header>
            <Card.Body>
              {featureChart.labels.length ? (
                <Bar
                  data={featureChart}
                  options={{
                    indexAxis: "y",
                    plugins: { legend: { display: false } },
                    scales: { x: { beginAtZero: true } },
                  }}
                />
              ) : (
                <EmptyState message="Feature importance not available for this model." />
              )}
            </Card.Body>
          </Card>

          <Card border="light" className="shadow-sm">
            <Card.Header>Version Comparison</Card.Header>
            <Card.Body className="p-0">
              {allVersions.length ? (
                <Table responsive hover className="mb-0">
                  <thead>
                    <tr>
                      <th>Version</th>
                      <th>Accuracy</th>
                      <th>F1</th>
                      <th>Trained</th>
                    </tr>
                  </thead>
                  <tbody>
                    {allVersions.map((row) => (
                      <tr key={row.model_id}>
                        <td>
                          <Badge bg={row.model_id === model.model_id ? "primary" : "light"} text={row.model_id === model.model_id ? undefined : "dark"}>
                            {row.version}
                          </Badge>
                        </td>
                        <td>{formatMetric(row.metrics, ["accuracy", "test_accuracy"])}</td>
                        <td>{formatMetric(row.metrics, ["f1_score", "f1"])}</td>
                        <td>{formatDate(row.trained_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              ) : (
                <EmptyState message="No version history available." />
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>
    </Container>
  );
}
