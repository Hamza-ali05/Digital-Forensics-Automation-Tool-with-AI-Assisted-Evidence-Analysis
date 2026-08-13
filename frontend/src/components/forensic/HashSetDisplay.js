import React from "react";
import { Button, Card, Table } from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faCheckCircle,
  faCopy,
  faTimesCircle,
} from "@fortawesome/free-solid-svg-icons";
import { CopyToClipboard } from "react-copy-to-clipboard";

import { formatDate, formatHash } from "utils/formatters";
import useNotification from "hooks/useNotification";

function HashRow({ label, value, verified }) {
  const { info } = useNotification();
  const digest = value || "";

  return (
    <tr>
      <th className="ps-0 text-muted" style={{ width: "18%" }}>
        {label}
      </th>
      <td>
        <code className="small text-break">{digest || "—"}</code>
      </td>
      <td className="text-end" style={{ width: 100 }}>
        {digest ? (
          <CopyToClipboard
            text={digest}
            onCopy={() => info("Copied", `${label} hash copied to clipboard.`)}
          >
            <Button
              variant="outline-secondary"
              size="sm"
              title={`Copy ${label}`}
              aria-label={`Copy ${label}`}
            >
              <FontAwesomeIcon icon={faCopy} className="me-1" />
              {formatHash(digest, 4)}
            </Button>
          </CopyToClipboard>
        ) : (
          "—"
        )}
      </td>
      <td className="text-center" style={{ width: 48 }}>
        {verified === true ? (
          <FontAwesomeIcon
            icon={faCheckCircle}
            className="text-success"
            title="Verified"
          />
        ) : verified === false ? (
          <FontAwesomeIcon
            icon={faTimesCircle}
            className="text-danger"
            title="Mismatch"
          />
        ) : null}
      </td>
    </tr>
  );
}

/**
 * Display MD5 / SHA-1 / SHA-256 with copy buttons and verification indicators.
 *
 * @param {{
 *   hashSet?: { md5?: string, sha1?: string, sha256?: string, computed_at?: string },
 *   lastVerifiedAt?: string|null,
 *   integrityVerified?: boolean|null,
 *   discrepancies?: object,
 *   className?: string,
 * }} props
 */
export default function HashSetDisplay({
  hashSet = {},
  lastVerifiedAt = null,
  integrityVerified = null,
  discrepancies = {},
  className = "",
}) {
  const md5 = hashSet.md5 || hashSet.MD5 || "";
  const sha1 = hashSet.sha1 || hashSet.SHA1 || "";
  const sha256 = hashSet.sha256 || hashSet.SHA256 || hashSet.primary_hash || "";

  const algoVerified = (algo) => {
    if (integrityVerified == null) return null;
    if (discrepancies && discrepancies[algo]) return false;
    return integrityVerified;
  };

  return (
    <Card border="light" className={`shadow-sm h-100 ${className}`.trim()}>
      <Card.Header className="border-bottom border-light d-flex justify-content-between align-items-center">
        <h5 className="mb-0">Hash Set</h5>
        {integrityVerified === true ? (
          <span className="text-success small fw-bold">
            <FontAwesomeIcon icon={faCheckCircle} className="me-1" />
            Integrity OK
          </span>
        ) : integrityVerified === false ? (
          <span className="text-danger small fw-bold">
            <FontAwesomeIcon icon={faTimesCircle} className="me-1" />
            Integrity failed
          </span>
        ) : (
          <span className="text-muted small">Not verified this session</span>
        )}
      </Card.Header>
      <Card.Body>
        <Table borderless responsive className="mb-2 align-middle">
          <tbody>
            <HashRow label="MD5" value={md5} verified={algoVerified("md5")} />
            <HashRow label="SHA-1" value={sha1} verified={algoVerified("sha1")} />
            <HashRow
              label="SHA-256"
              value={sha256}
              verified={algoVerified("sha256")}
            />
          </tbody>
        </Table>
        <div className="small text-muted">
          Computed: {formatDate(hashSet.computed_at) || "—"}
          <span className="mx-1">·</span>
          Last verified: {formatDate(lastVerifiedAt) || "—"}
        </div>
      </Card.Body>
    </Card>
  );
}
