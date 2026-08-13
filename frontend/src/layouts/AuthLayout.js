import React, { useEffect, useState } from "react";
import { Container } from "@themesberg/react-bootstrap";

import LoadingSpinner from "components/common/LoadingSpinner";
import config from "config";

/**
 * Centred auth shell for login / register (no sidebar).
 * Branding sits above page content; pages supply their own card forms.
 */
export default function AuthLayout({ children }) {
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setLoaded(true), 400);
    return () => clearTimeout(timer);
  }, []);

  return (
    <>
      <LoadingSpinner show={!loaded} />
      <main className="dfat-auth-layout">
        <Container className="pt-4 pt-lg-5 text-center">
          <div className="dfat-auth-brand">
            <span className="fw-bold fs-2 text-primary d-block">{config.appName}</span>
            <span className="text-gray">Digital Forensics Automation Tool</span>
          </div>
        </Container>
        {children}
      </main>
    </>
  );
}
