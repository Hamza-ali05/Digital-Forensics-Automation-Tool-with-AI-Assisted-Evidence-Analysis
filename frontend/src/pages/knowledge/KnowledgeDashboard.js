import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Badge,
  Button,
  Card,
  Col,
  Container,
  Form,
  ListGroup,
  Row,
} from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faBook,
  faProjectDiagram,
  faSearch,
  faShieldAlt,
} from "@fortawesome/free-solid-svg-icons";
import {
  Chart as ChartJS,
  ArcElement,
  BarElement,
  CategoryScale,
  Legend,
  LinearScale,
  Tooltip,
} from "chart.js";
import { Bar, Doughnut } from "react-chartjs-2";

import PageHeader from "components/common/PageHeader";
import ApiErrorDisplay from "components/common/ApiErrorDisplay";
import EmptyState from "components/common/EmptyState";
import SkeletonLoader from "components/common/SkeletonLoader";
import StatCard from "components/forensic/StatCard";
import knowledgeService from "services/knowledge.service";

ChartJS.register(
  ArcElement,
  BarElement,
  CategoryScale,
  LinearScale,
  Legend,
  Tooltip
);

function chartFromCounts(counts = {}) {
  const labels = Object.keys(counts).map((key) =>
    key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
  );
  return {
    labels,
    datasets: [
      {
        data: Object.values(counts),
        backgroundColor: ["#0d6efd", "#198754", "#ffc107", "#dc3545", "#6f42c1", "#fd7e14"],
      },
    ],
  };
}

function sumCollectionCounts(collections = {}) {
  let total = 0;
  Object.values(collections).forEach((item) => {
    total += Number(item?.count ?? item?.document_count ?? item?.documents ?? 0);
  });
  return total;
}

/**
 * Knowledge base dashboard with vector, graph, and IOC statistics plus search.
 */
export default function KnowledgeDashboard() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [stats, setStats] = useState(null);
  const [graphStats, setGraphStats] = useState(null);
  const [query, setQuery] = useState("");
  const [queryBusy, setQueryBusy] = useState(false);
  const [queryError, setQueryError] = useState(null);
  const [queryResult, setQueryResult] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [statsResult, graphResult] = await Promise.all([
        knowledgeService.getStats(),
        knowledgeService.getGraphStats(),
      ]);
      setStats(statsResult);
      setGraphStats(graphResult);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleQuery = async (event) => {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;
    setQueryBusy(true);
    setQueryError(null);
    try {
      const result = await knowledgeService.query({
        query: trimmed,
        max_results: 10,
      });
      setQueryResult(result);
    } catch (err) {
      setQueryError(err);
      setQueryResult(null);
    } finally {
      setQueryBusy(false);
    }
  };

  const vectorCollections = stats?.vector_collections || {};
  const iocStats = stats?.ioc_statistics || {};
  const graph = graphStats || stats?.graph_statistics || {};

  const collectionChart = useMemo(() => {
    const counts = {};
    Object.entries(vectorCollections).forEach(([name, info]) => {
      counts[name] = Number(info?.count ?? info?.document_count ?? info?.documents ?? 0);
    });
    return chartFromCounts(counts);
  }, [vectorCollections]);

  const iocTypeChart = useMemo(
    () => chartFromCounts(iocStats.by_type || iocStats.type_counts || {}),
    [iocStats]
  );

  const graphNodeChart = useMemo(
    () => chartFromCounts(graph.nodes_by_type || graph.node_types || {}),
    [graph]
  );

  if (loading && !stats) {
    return (
      <Container fluid className="px-0">
        <SkeletonLoader type="dashboard" />
      </Container>
    );
  }

  return (
    <Container fluid className="px-0">
      <PageHeader
        title="Knowledge Base"
        subtitle="Vector store, knowledge graph, and IOC intelligence"
      />

      {error ? <ApiErrorDisplay error={error} onRetry={load} className="mb-3" /> : null}

      <Row className="g-3 mb-3">
        <Col xs={12} md={4}>
          <StatCard
            title="Vector Documents"
            value={sumCollectionCounts(vectorCollections)}
            icon={faBook}
            colour="primary"
          />
        </Col>
        <Col xs={12} md={4}>
          <StatCard
            title="Graph Nodes"
            value={graph.total_nodes ?? graph.nodes ?? 0}
            icon={faProjectDiagram}
            colour="success"
          />
        </Col>
        <Col xs={12} md={4}>
          <StatCard
            title="IOC Entries"
            value={iocStats.total_iocs ?? iocStats.total ?? 0}
            icon={faShieldAlt}
            colour="warning"
          />
        </Col>
      </Row>

      <Row className="g-3 mb-3">
        <Col xs={12} lg={4}>
          <Card border="light" className="shadow-sm h-100">
            <Card.Header>Documents per Collection</Card.Header>
            <Card.Body>
              {collectionChart.labels.length ? (
                <Doughnut data={collectionChart} />
              ) : (
                <EmptyState message="No vector collections indexed yet." />
              )}
            </Card.Body>
          </Card>
        </Col>
        <Col xs={12} lg={4}>
          <Card border="light" className="shadow-sm h-100">
            <Card.Header>Graph Nodes by Type</Card.Header>
            <Card.Body>
              {graphNodeChart.labels.length ? (
                <Bar data={graphNodeChart} options={{ plugins: { legend: { display: false } } }} />
              ) : (
                <EmptyState message="Knowledge graph statistics unavailable." />
              )}
              <div className="small text-muted mt-2">
                Edges: {graph.total_edges ?? graph.edges ?? 0}
              </div>
            </Card.Body>
          </Card>
        </Col>
        <Col xs={12} lg={4}>
          <Card border="light" className="shadow-sm h-100">
            <Card.Header>IOCs by Type</Card.Header>
            <Card.Body>
              {iocTypeChart.labels.length ? (
                <Doughnut data={iocTypeChart} />
              ) : (
                <EmptyState message="No IOC statistics available." />
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      <Card border="light" className="shadow-sm">
        <Card.Header>Query Knowledge Base</Card.Header>
        <Card.Body>
          <Form onSubmit={handleQuery} className="mb-3">
            <Row className="g-2">
              <Col xs={12} md={9}>
                <Form.Control
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search forensic knowledge, IOCs, and graph connections…"
                />
              </Col>
              <Col xs={12} md={3}>
                <Button type="submit" variant="primary" className="w-100" disabled={queryBusy}>
                  <FontAwesomeIcon icon={faSearch} className="me-2" />
                  {queryBusy ? "Searching…" : "Search"}
                </Button>
              </Col>
            </Row>
          </Form>

          {queryError ? (
            <ApiErrorDisplay error={queryError} className="mb-3" />
          ) : null}

          {queryResult ? (
            <>
              <div className="small text-muted mb-2">
                {queryResult.total_results ?? 0} results in{" "}
                {queryResult.retrieval_time_ms ?? 0} ms
              </div>
              <Row className="g-3">
                <Col xs={12} lg={4}>
                  <h6>Vector Results</h6>
                  <ListGroup variant="flush">
                    {(queryResult.vector_results || []).slice(0, 5).map((item, index) => (
                      <ListGroup.Item key={`vec-${index}`}>
                        <div className="small fw-bold">{item.collection || item.source || "vector"}</div>
                        <div className="small text-muted">{item.content || item.text || JSON.stringify(item).slice(0, 120)}</div>
                      </ListGroup.Item>
                    ))}
                  </ListGroup>
                </Col>
                <Col xs={12} lg={4}>
                  <h6>IOC Matches</h6>
                  <ListGroup variant="flush">
                    {(queryResult.ioc_matches || []).slice(0, 5).map((item, index) => (
                      <ListGroup.Item key={`ioc-${index}`}>
                        <Badge bg="danger" className="me-1">{item.ioc_type || item.type}</Badge>
                        <span className="small">{item.value || item.ioc_value}</span>
                      </ListGroup.Item>
                    ))}
                  </ListGroup>
                </Col>
                <Col xs={12} lg={4}>
                  <h6>Graph Connections</h6>
                  <ListGroup variant="flush">
                    {(queryResult.graph_connections || []).slice(0, 5).map((item, index) => (
                      <ListGroup.Item key={`graph-${index}`}>
                        <div className="small">{item.label || item.relation || item.type}</div>
                        <div className="small text-muted">{item.node || item.target || item.id}</div>
                      </ListGroup.Item>
                    ))}
                  </ListGroup>
                </Col>
              </Row>
            </>
          ) : (
            <EmptyState message="Enter a query to search the unified knowledge base." />
          )}
        </Card.Body>
      </Card>
    </Container>
  );
}
