import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Container,
  Form,
  ProgressBar,
  Row,
  Spinner,
  Table,
} from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faCheckCircle,
  faSearch,
  faShieldAlt,
  faTimesCircle,
} from "@fortawesome/free-solid-svg-icons";

import PageHeader from "components/common/PageHeader";
import DataTable from "components/common/DataTable";
import ApiErrorDisplay from "components/common/ApiErrorDisplay";
import EmptyState from "components/common/EmptyState";
import { formatDate, formatHash } from "utils/formatters";
import useNotification from "hooks/useNotification";
import evidenceService from "services/evidence.service";
import casesService from "services/cases.service";
import { Routes } from "routes";

const ALGORITHMS = [
  { key: "md5", label: "MD5" },
  { key: "sha1", label: "SHA-1" },
  { key: "sha256", label: "SHA-256" },
];

function shortId(id) {
  if (!id) return "—";
  return String(id).slice(0, 8);
}

function pickHash(hashSet, algo) {
  if (!hashSet) return "";
  return (
    hashSet[algo] ||
    hashSet[algo.toUpperCase()] ||
    hashSet[`hash_${algo}`] ||
    ""
  );
}

function mismatchAlgos(discrepancies = {}) {
  return Object.keys(discrepancies || {})
    .map((k) => k.toLowerCase())
    .filter((k) => ["md5", "sha1", "sha256"].includes(k));
}

function buildComparison(original, verifyResult) {
  const discrepancies = verifyResult?.discrepancies || {};
  const currentSet = verifyResult?.hash_set || {};
  const passed = Boolean(verifyResult?.integrity_verified);

  return ALGORITHMS.map(({ key, label }) => {
    const disc = discrepancies[key] || discrepancies[key.toUpperCase()];
    const expected = disc?.expected || pickHash(original, key) || "";
    const actual =
      disc?.actual ||
      pickHash(currentSet, key) ||
      (passed ? expected : "");
    const match =
      passed ||
      (expected &&
        actual &&
        String(expected).toLowerCase() === String(actual).toLowerCase());
    return { key, label, expected, actual, match: Boolean(match && expected) };
  });
}

/**
 * Dedicated evidence integrity verification — single and batch.
 */
export default function IntegrityCheck() {
  const { success, error: notifyError, warning } = useNotification();

  const [inventory, setInventory] = useState([]);
  const [cases, setCases] = useState([]);
  const [loadError, setLoadError] = useState(null);
  const [loadingList, setLoadingList] = useState(true);

  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [singleBusy, setSingleBusy] = useState(false);
  const [singleResult, setSingleResult] = useState(null);
  const [singleOriginal, setSingleOriginal] = useState({});
  const [singleMeta, setSingleMeta] = useState(null);

  const [batchCaseId, setBatchCaseId] = useState("");
  const [batchBusy, setBatchBusy] = useState(false);
  const [batchProgress, setBatchProgress] = useState({ done: 0, total: 0 });
  const [batchResults, setBatchResults] = useState([]);
  const [expandedFail, setExpandedFail] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoadingList(true);
      setLoadError(null);
      try {
        const [inv, caseList] = await Promise.all([
          evidenceService.getInventory(),
          casesService.list().catch(() => ({ cases: [] })),
        ]);
        if (cancelled) return;
        setInventory(Array.isArray(inv?.items) ? inv.items : []);
        setCases(Array.isArray(caseList?.cases) ? caseList.cases : []);
      } catch (err) {
        if (!cancelled) setLoadError(err);
      } finally {
        if (!cancelled) setLoadingList(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const filteredOptions = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return inventory;
    return inventory.filter((item) => {
      const hay = [
        item.evidence_id,
        item.file_name,
        item.case_name,
        pickHash(item.hash_set, "sha256"),
      ]
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }, [inventory, search]);

  const selectedItem = useMemo(
    () => inventory.find((item) => item.evidence_id === selectedId) || null,
    [inventory, selectedId]
  );

  const comparison = useMemo(() => {
    if (!singleResult) return [];
    return buildComparison(singleOriginal, singleResult);
  }, [singleOriginal, singleResult]);

  const handleSingleVerify = async () => {
    if (!selectedId) {
      notifyError("Select evidence", "Choose an evidence item to verify.");
      return;
    }
    setSingleBusy(true);
    setSingleResult(null);
    try {
      let original = selectedItem?.hash_set || {};
      try {
        const detail = await evidenceService.getDetail(selectedId);
        original = detail?.metadata?.hash_set || original;
        if (!original?.sha256 && detail?.original_hash) {
          original = { ...original, sha256: detail.original_hash };
        }
        setSingleMeta({
          fileName: selectedItem?.file_name || detail?.file_path,
          caseName: detail?.case_name || selectedItem?.case_name,
        });
      } catch {
        setSingleMeta({
          fileName: selectedItem?.file_name,
          caseName: selectedItem?.case_name,
        });
      }
      setSingleOriginal(original || {});

      const result = await evidenceService.verifyIntegrity(selectedId);
      setSingleResult(result);
      if (result?.integrity_verified) {
        success("Integrity passed", "All registered hashes match the file.");
      } else {
        warning(
          "Integrity failed",
          `Mismatch on: ${mismatchAlgos(result?.discrepancies).join(", ") || "hash"}`
        );
      }
    } catch (err) {
      notifyError("Verification failed", err?.message || "Could not verify.");
    } finally {
      setSingleBusy(false);
    }
  };

  const handleBatchVerify = async () => {
    const targets = batchCaseId
      ? inventory.filter((item) => item.case_id === batchCaseId)
      : inventory;

    if (!targets.length) {
      notifyError("Nothing to verify", "No evidence matches the current filter.");
      return;
    }

    setBatchBusy(true);
    setBatchResults([]);
    setExpandedFail(null);
    setBatchProgress({ done: 0, total: targets.length });

    const rows = [];
    for (let i = 0; i < targets.length; i += 1) {
      const item = targets[i];
      let original = item.hash_set || {};
      try {
        const detail = await evidenceService.getDetail(item.evidence_id);
        original = detail?.metadata?.hash_set || original;
        if (!original?.sha256 && detail?.original_hash) {
          original = { ...original, sha256: detail.original_hash };
        }
      } catch {
        // use inventory hash_set
      }

      try {
        const result = await evidenceService.verifyIntegrity(item.evidence_id);
        const mismatched = mismatchAlgos(result.discrepancies);
        rows.push({
          id: item.evidence_id,
          evidence_id: item.evidence_id,
          file_name: item.file_name,
          passed: Boolean(result.integrity_verified),
          mismatched: mismatched.join(", ") || (result.integrity_verified ? "—" : "unknown"),
          timestamp: result.timestamp,
          original,
          result,
          error: null,
        });
      } catch (err) {
        rows.push({
          id: item.evidence_id,
          evidence_id: item.evidence_id,
          file_name: item.file_name,
          passed: false,
          mismatched: "error",
          timestamp: new Date().toISOString(),
          original,
          result: null,
          error: err?.message || "Verification request failed",
        });
      }
      setBatchProgress({ done: i + 1, total: targets.length });
      setBatchResults([...rows]);
    }

    const passed = rows.filter((r) => r.passed).length;
    if (passed === rows.length) {
      success("Batch complete", `All ${rows.length} items passed integrity checks.`);
    } else {
      warning(
        "Batch complete",
        `${passed}/${rows.length} passed. Review failed items below.`
      );
    }
    setBatchBusy(false);
  };

  const batchPassed = batchResults.filter((r) => r.passed).length;

  const batchColumns = useMemo(
    () => [
      {
        key: "evidence_id",
        header: "Evidence ID",
        render: (row) => (
          <Link to={Routes.EvidenceDetail.path.replace(":id", row.evidence_id)}>
            {shortId(row.evidence_id)}
          </Link>
        ),
      },
      {
        key: "file_name",
        header: "File",
        accessor: "file_name",
      },
      {
        key: "status",
        header: "Status",
        render: (row) =>
          row.passed ? (
            <Badge bg="success">Pass</Badge>
          ) : (
            <Badge bg="danger">Fail</Badge>
          ),
      },
      {
        key: "mismatched",
        header: "Mismatched Algorithm",
        accessor: "mismatched",
      },
      {
        key: "timestamp",
        header: "Timestamp",
        render: (row) => formatDate(row.timestamp),
      },
    ],
    []
  );

  return (
    <Container fluid className="px-0">
      <PageHeader
        title="Evidence Integrity Verification"
        subtitle="Compare registered digests against current file hashes (MD5, SHA-1, SHA-256)"
        breadcrumbs={[
          { label: "Home", to: Routes.Dashboard.path },
          { label: "Evidence", to: Routes.Evidence.path },
          { label: "Integrity Check" },
        ]}
      />

      {loadError ? (
        <ApiErrorDisplay error={loadError} className="mb-3" />
      ) : null}

      {/* Section 1 — Single */}
      <Card border="light" className="shadow-sm mb-4">
        <Card.Header className="border-bottom border-light">
          <h5 className="mb-0">
            <FontAwesomeIcon icon={faShieldAlt} className="me-2 text-primary" />
            Single Evidence Verification
          </h5>
        </Card.Header>
        <Card.Body>
          <Row className="g-3 align-items-end mb-3">
            <Col xs={12} md={4}>
              <Form.Group className="mb-0">
                <Form.Label className="small text-muted mb-1">
                  Search by ID or filename
                </Form.Label>
                <Form.Control
                  type="search"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Filter evidence…"
                  disabled={loadingList || batchBusy}
                />
              </Form.Group>
            </Col>
            <Col xs={12} md={5}>
              <Form.Group className="mb-0">
                <Form.Label className="small text-muted mb-1">
                  Evidence
                </Form.Label>
                <Form.Select
                  value={selectedId}
                  onChange={(e) => {
                    setSelectedId(e.target.value);
                    setSingleResult(null);
                  }}
                  disabled={loadingList || singleBusy || batchBusy}
                >
                  <option value="">
                    {loadingList
                      ? "Loading…"
                      : filteredOptions.length
                        ? "Select evidence…"
                        : "No matching evidence"}
                  </option>
                  {filteredOptions.map((item) => (
                    <option key={item.evidence_id} value={item.evidence_id}>
                      {item.file_name} ({shortId(item.evidence_id)})
                    </option>
                  ))}
                </Form.Select>
              </Form.Group>
            </Col>
            <Col xs={12} md={3}>
              <Button
                variant="primary"
                className="w-100"
                disabled={!selectedId || singleBusy || batchBusy}
                onClick={handleSingleVerify}
              >
                {singleBusy ? (
                  <>
                    <Spinner animation="border" size="sm" className="me-2" />
                    Verifying…
                  </>
                ) : (
                  <>
                    <FontAwesomeIcon icon={faSearch} className="me-2" />
                    Verify
                  </>
                )}
              </Button>
            </Col>
          </Row>

          {singleResult ? (
            <Card border={singleResult.integrity_verified ? "success" : "danger"}>
              <Card.Header
                className={`d-flex justify-content-between align-items-center ${
                  singleResult.integrity_verified
                    ? "bg-success text-white"
                    : "bg-danger text-white"
                }`}
              >
                <span className="fw-bold">
                  {singleResult.integrity_verified ? (
                    <>
                      <FontAwesomeIcon icon={faCheckCircle} className="me-2" />
                      Integrity passed
                    </>
                  ) : (
                    <>
                      <FontAwesomeIcon icon={faTimesCircle} className="me-2" />
                      Integrity failed
                    </>
                  )}
                </span>
                <span className="small">
                  {formatDate(singleResult.timestamp)}
                </span>
              </Card.Header>
              <Card.Body>
                {singleMeta ? (
                  <p className="small text-muted mb-3">
                    {singleMeta.fileName}
                    {singleMeta.caseName
                      ? ` · Case: ${singleMeta.caseName}`
                      : ""}
                  </p>
                ) : null}
                <Table responsive bordered className="align-middle mb-0">
                  <thead className="thead-light">
                    <tr>
                      <th>Algorithm</th>
                      <th>Original (registered)</th>
                      <th>Current (file)</th>
                      <th className="text-center">Result</th>
                    </tr>
                  </thead>
                  <tbody>
                    {comparison.map((row) => (
                      <tr key={row.key}>
                        <td className="fw-bold">{row.label}</td>
                        <td>
                          <code className="small text-break">
                            {row.expected || "—"}
                          </code>
                        </td>
                        <td>
                          <code className="small text-break">
                            {row.actual || "—"}
                          </code>
                        </td>
                        <td className="text-center">
                          {row.match ? (
                            <FontAwesomeIcon
                              icon={faCheckCircle}
                              className="text-success"
                              size="lg"
                            />
                          ) : (
                            <FontAwesomeIcon
                              icon={faTimesCircle}
                              className="text-danger"
                              size="lg"
                            />
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
                {!singleResult.integrity_verified &&
                Object.keys(singleResult.discrepancies || {}).length ? (
                  <Alert variant="warning" className="mt-3 mb-0">
                    <div className="fw-bold mb-2">Mismatch details</div>
                    {ALGORITHMS.filter(
                      ({ key }) => singleResult.discrepancies[key]
                    ).map(({ key, label }) => {
                      const disc = singleResult.discrepancies[key];
                      return (
                        <div key={key} className="small mb-2">
                          <strong>{label}</strong>
                          <div>
                            Expected:{" "}
                            <code>{formatHash(disc.expected, 16)}</code>
                          </div>
                          <div>
                            Actual: <code>{formatHash(disc.actual, 16)}</code>
                          </div>
                        </div>
                      );
                    })}
                  </Alert>
                ) : null}
                <div className="mt-3">
                  <Button
                    as={Link}
                    to={Routes.EvidenceDetail.path.replace(":id", selectedId)}
                    variant="outline-primary"
                    size="sm"
                  >
                    Open evidence detail
                  </Button>
                </div>
              </Card.Body>
            </Card>
          ) : (
            <EmptyState
              title="No verification yet"
              description="Select an evidence item and click Verify. Results are also written to the forensic audit trail."
            />
          )}
        </Card.Body>
      </Card>

      {/* Section 2 — Batch */}
      <Card border="light" className="shadow-sm">
        <Card.Header className="border-bottom border-light">
          <h5 className="mb-0">Batch Verification</h5>
        </Card.Header>
        <Card.Body>
          <Row className="g-3 align-items-end mb-3">
            <Col xs={12} md={6}>
              <Form.Group className="mb-0">
                <Form.Label className="small text-muted mb-1">
                  Case filter (optional)
                </Form.Label>
                <Form.Select
                  value={batchCaseId}
                  onChange={(e) => setBatchCaseId(e.target.value)}
                  disabled={batchBusy || loadingList}
                >
                  <option value="">All evidence</option>
                  {cases.map((c) => (
                    <option key={c.case_id} value={c.case_id}>
                      {c.case_name}
                    </option>
                  ))}
                </Form.Select>
              </Form.Group>
            </Col>
            <Col xs={12} md={6}>
              <Button
                variant="warning"
                className="w-100"
                disabled={batchBusy || loadingList || !inventory.length}
                onClick={handleBatchVerify}
              >
                {batchBusy ? (
                  <>
                    <Spinner animation="border" size="sm" className="me-2" />
                    Verifying {batchProgress.done}/{batchProgress.total}…
                  </>
                ) : (
                  <>
                    <FontAwesomeIcon icon={faShieldAlt} className="me-2" />
                    Verify All Evidence
                    {batchCaseId ? " in Case" : ""}
                  </>
                )}
              </Button>
            </Col>
          </Row>

          {batchBusy || batchProgress.total > 0 ? (
            <div className="mb-3">
              <div className="d-flex justify-content-between small text-muted mb-1">
                <span>Progress</span>
                <span>
                  {batchProgress.done}/{batchProgress.total}
                </span>
              </div>
              <ProgressBar
                now={
                  batchProgress.total
                    ? Math.round(
                        (batchProgress.done / batchProgress.total) * 100
                      )
                    : 0
                }
                animated={batchBusy}
                variant={batchBusy ? "info" : "success"}
              />
            </div>
          ) : null}

          {batchResults.length ? (
            <>
              <Alert
                variant={
                  batchPassed === batchResults.length ? "success" : "warning"
                }
                className="mb-3"
              >
                <strong>
                  {batchPassed}/{batchResults.length}
                </strong>{" "}
                passed integrity check
                {batchPassed < batchResults.length
                  ? ` · ${batchResults.length - batchPassed} failed`
                  : ""}
              </Alert>

              <DataTable
                columns={batchColumns}
                data={batchResults}
                emptyMessage="No batch results"
                actions={(row) =>
                  !row.passed ? (
                    <Button
                      size="sm"
                      variant="outline-danger"
                      onClick={() =>
                        setExpandedFail(
                          expandedFail === row.evidence_id
                            ? null
                            : row.evidence_id
                        )
                      }
                    >
                      {expandedFail === row.evidence_id
                        ? "Hide details"
                        : "Details"}
                    </Button>
                  ) : null
                }
              />

              {batchResults
                .filter(
                  (row) => !row.passed && expandedFail === row.evidence_id
                )
                .map((row) => (
                  <Alert key={row.evidence_id} variant="danger" className="mt-3">
                    <div className="fw-bold mb-2">
                      Failed: {row.file_name} ({shortId(row.evidence_id)})
                    </div>
                    {row.error ? (
                      <div className="small">{row.error}</div>
                    ) : (
                      <Table size="sm" bordered className="mb-0 bg-white">
                        <thead>
                          <tr>
                            <th>Algorithm</th>
                            <th>Expected</th>
                            <th>Actual</th>
                          </tr>
                        </thead>
                        <tbody>
                          {buildComparison(row.original, row.result).map(
                            (cmp) => (
                              <tr key={cmp.key}>
                                <td>{cmp.label}</td>
                                <td>
                                  <code className="small">
                                    {cmp.expected || "—"}
                                  </code>
                                </td>
                                <td>
                                  <code className="small">
                                    {cmp.actual || "—"}
                                  </code>
                                </td>
                              </tr>
                            )
                          )}
                        </tbody>
                      </Table>
                    )}
                  </Alert>
                ))}
            </>
          ) : (
            <EmptyState
              title="No batch results yet"
              description="Optionally filter by case, then run Verify All Evidence. Each check is logged to the audit trail."
            />
          )}
        </Card.Body>
      </Card>
    </Container>
  );
}
