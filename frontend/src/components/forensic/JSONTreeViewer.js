import React, { useEffect, useMemo, useState } from "react";
import { Button, Form, InputGroup } from "@themesberg/react-bootstrap";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faCaretDown,
  faCaretRight,
  faCopy,
  faSearch,
} from "@fortawesome/free-solid-svg-icons";
import { CopyToClipboard } from "react-copy-to-clipboard";

const TYPE_COLOURS = {
  key: "#0d6efd",
  string: "#198754",
  number: "#fd7e14",
  boolean: "#6f42c1",
  null: "#6c757d",
};

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function stringifyNode(value) {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function valueMatches(value, query) {
  if (!query) return false;
  const q = query.toLowerCase();
  if (typeof value === "string") return value.toLowerCase().includes(q);
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value).toLowerCase().includes(q);
  }
  if (value == null) return q === "null";
  return false;
}

function subtreeMatches(value, query) {
  if (!query) return true;
  if (valueMatches(value, query)) return true;
  if (Array.isArray(value)) {
    return value.some((item) => subtreeMatches(item, query));
  }
  if (isPlainObject(value)) {
    return Object.entries(value).some(
      ([key, child]) =>
        String(key).toLowerCase().includes(query.toLowerCase()) ||
        subtreeMatches(child, query)
    );
  }
  return false;
}

function Highlight({ text, query }) {
  const value = String(text);
  if (!query) return value;
  const lower = value.toLowerCase();
  const needle = query.toLowerCase();
  const index = lower.indexOf(needle);
  if (index < 0) return value;
  return (
    <>
      {value.slice(0, index)}
      <mark className="px-0">{value.slice(index, index + needle.length)}</mark>
      {value.slice(index + needle.length)}
    </>
  );
}

function Primitive({ value, query }) {
  if (value === null || value === undefined) {
    return <span style={{ color: TYPE_COLOURS.null }}>null</span>;
  }
  if (typeof value === "boolean") {
    return (
      <span style={{ color: TYPE_COLOURS.boolean }}>
        <Highlight text={String(value)} query={query} />
      </span>
    );
  }
  if (typeof value === "number") {
    return (
      <span style={{ color: TYPE_COLOURS.number }}>
        <Highlight text={String(value)} query={query} />
      </span>
    );
  }
  return (
    <span style={{ color: TYPE_COLOURS.string }}>
      &quot;
      <Highlight text={String(value)} query={query} />
      &quot;
    </span>
  );
}

function CopyButton({ value, onCopied }) {
  const text = stringifyNode(value);
  return (
    <CopyToClipboard text={text} onCopy={onCopied}>
      <Button
        variant="link"
        size="sm"
        className="p-0 ms-1 text-muted"
        title="Copy this node"
        aria-label="Copy this node"
      >
        <FontAwesomeIcon icon={faCopy} />
      </Button>
    </CopyToClipboard>
  );
}

function JSONNode({
  name,
  value,
  depth,
  maxDepth,
  query,
  onCopied,
}) {
  const expandable = isPlainObject(value) || Array.isArray(value);
  const queryActive = Boolean(query);
  const matches = queryActive ? subtreeMatches(value, query) : true;
  const keyMatches =
    queryActive && String(name).toLowerCase().includes(query.toLowerCase());
  const [open, setOpen] = useState(
    () => depth < maxDepth || (queryActive && matches)
  );

  useEffect(() => {
    if (queryActive && matches) setOpen(true);
    if (!queryActive) setOpen(depth < maxDepth);
  }, [queryActive, matches, depth, maxDepth]);

  if (queryActive && !matches && !keyMatches && depth > 0) {
    return null;
  }

  const entries = expandable
    ? Array.isArray(value)
      ? value.map((item, index) => [index, item])
      : Object.entries(value)
    : [];
  const preview = Array.isArray(value)
    ? `Array(${value.length})`
    : expandable
      ? `{${Object.keys(value).length}}`
      : null;

  return (
    <div className="font-monospace small" style={{ marginLeft: depth ? 16 : 0 }}>
      <div className="d-flex align-items-start">
        {expandable ? (
          <button
            type="button"
            className="btn btn-link p-0 me-1 text-muted"
            onClick={() => setOpen((prev) => !prev)}
            aria-label={open ? "Collapse" : "Expand"}
          >
            <FontAwesomeIcon icon={open ? faCaretDown : faCaretRight} />
          </button>
        ) : (
          <span className="me-3" />
        )}
        {name !== undefined && name !== null && name !== "" ? (
          <span style={{ color: TYPE_COLOURS.key }}>
            <Highlight text={String(name)} query={query} />
            <span className="text-muted">: </span>
          </span>
        ) : null}
        {expandable ? (
          <span className="text-muted">{preview}</span>
        ) : (
          <Primitive value={value} query={query} />
        )}
        <CopyButton value={value} onCopied={onCopied} />
      </div>
      {expandable && open
        ? entries.map(([key, child]) => (
            <JSONNode
              key={String(key)}
              name={key}
              value={child}
              depth={depth + 1}
              maxDepth={maxDepth}
              query={query}
              onCopied={onCopied}
            />
          ))
        : null}
    </div>
  );
}

/**
 * Collapsible JSON tree with optional search and per-node copy.
 *
 * @param {{
 *   data: object|array,
 *   searchable?: boolean,
 *   maxDepth?: number,
 *   onCopied?: () => void,
 * }} props
 */
export default function JSONTreeViewer({
  data,
  searchable = true,
  maxDepth = 2,
  onCopied,
}) {
  const [query, setQuery] = useState("");
  const trimmed = query.trim();

  const empty = data == null || (isPlainObject(data) && !Object.keys(data).length);

  const tree = useMemo(
    () => (
      <JSONNode
        name=""
        value={data}
        depth={0}
        maxDepth={maxDepth}
        query={trimmed}
        onCopied={onCopied}
      />
    ),
    [data, maxDepth, trimmed, onCopied]
  );

  if (empty) {
    return <p className="text-muted small mb-0">No JSON data to display.</p>;
  }

  return (
    <div className="dfat-json-tree">
      {searchable ? (
        <InputGroup className="mb-3" size="sm" style={{ maxWidth: 360 }}>
          <InputGroup.Text>
            <FontAwesomeIcon icon={faSearch} />
          </InputGroup.Text>
          <Form.Control
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search within JSON…"
            aria-label="Search within JSON"
          />
        </InputGroup>
      ) : null}
      <div
        className="bg-light rounded p-3"
        style={{ maxHeight: 640, overflow: "auto" }}
      >
        {tree}
      </div>
    </div>
  );
}
