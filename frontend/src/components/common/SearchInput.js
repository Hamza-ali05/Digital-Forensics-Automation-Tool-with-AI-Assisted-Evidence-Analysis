import React, { useEffect, useRef, useState } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faSearch, faTimes } from "@fortawesome/free-solid-svg-icons";
import { Form, InputGroup, Button } from "@themesberg/react-bootstrap";

import useDebounce from "hooks/useDebounce";

/**
 * Search field with icon, clear button, and debounced onChange.
 *
 * @param {{
 *   placeholder?: string,
 *   value?: string,
 *   onChange?: (value: string) => void,
 *   debounceMs?: number,
 *   className?: string,
 * }} props
 */
export default function SearchInput({
  placeholder = "Search…",
  value = "",
  onChange,
  debounceMs = 300,
  className = "",
}) {
  const [internal, setInternal] = useState(value);
  const debounced = useDebounce(internal, debounceMs);
  const skipEmit = useRef(true);

  useEffect(() => {
    setInternal(value);
  }, [value]);

  useEffect(() => {
    if (skipEmit.current) {
      skipEmit.current = false;
      return;
    }
    if (typeof onChange === "function") {
      onChange(debounced);
    }
  }, [debounced, onChange]);

  const clear = () => {
    setInternal("");
  };

  return (
    <Form className={className} onSubmit={(e) => e.preventDefault()}>
      <Form.Group className="mb-0">
        <InputGroup className="input-group-merge search-bar">
          <InputGroup.Text>
            <FontAwesomeIcon icon={faSearch} />
          </InputGroup.Text>
          <Form.Control
            type="search"
            placeholder={placeholder}
            value={internal}
            onChange={(e) => setInternal(e.target.value)}
            aria-label={placeholder}
          />
          {internal ? (
            <Button
              variant="link"
              className="text-muted px-2"
              onClick={clear}
              aria-label="Clear search"
            >
              <FontAwesomeIcon icon={faTimes} />
            </Button>
          ) : null}
        </InputGroup>
      </Form.Group>
    </Form>
  );
}
