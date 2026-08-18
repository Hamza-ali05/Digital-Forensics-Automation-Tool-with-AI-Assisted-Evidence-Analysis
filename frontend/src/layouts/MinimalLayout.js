import React, { useEffect, useState } from "react";
import { Container } from "@themesberg/react-bootstrap";
import { Link } from "react-router-dom";

import LoadingSpinner from "components/common/LoadingSpinner";
import SkipToContent from "components/common/SkipToContent";
import config from "config";
import { Routes } from "routes";

/**
 * Clean public layout (e.g. usability questionnaire) — header only, no nav.
 */
export default function MinimalLayout({ children }) {
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setLoaded(true), 400);
    return () => clearTimeout(timer);
  }, []);

  return (
    <>
      <SkipToContent />
      <LoadingSpinner show={!loaded} />
      <div className="dfat-minimal-layout min-vh-100 bg-soft">
        <header className="border-bottom bg-white py-3">
          <Container>
            <Link
              to={Routes.Questionnaire.path}
              className="text-decoration-none text-dark fw-bold fs-5"
            >
              {config.appName}
            </Link>
            <span className="text-muted ms-2 small">
              Digital Forensics Automation Tool
            </span>
          </Container>
        </header>
        <Container as="main" id="main-content" className="py-4" tabIndex={-1}>
          {children}
        </Container>
      </div>
    </>
  );
}
