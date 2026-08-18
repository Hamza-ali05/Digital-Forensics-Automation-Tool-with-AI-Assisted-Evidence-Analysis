import React, { useCallback, useEffect, useState } from "react";
import { Container } from "@themesberg/react-bootstrap";

import Sidebar from "components/layout/Sidebar";
import Topbar from "components/layout/Topbar";
import Footer from "components/layout/Footer";
import LoadingSpinner from "components/common/LoadingSpinner";
import SkipToContent from "components/common/SkipToContent";

/**
 * Main authenticated shell: Sidebar + Topbar + content + Footer.
 * Sidebar collapse state is shared so the Topbar hamburger works on mobile.
 */
export default function DashboardLayout({ children }) {
  const [loaded, setLoaded] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setLoaded(true), 400);
    return () => clearTimeout(timer);
  }, []);

  const toggleSidebar = useCallback(() => {
    setSidebarOpen((open) => !open);
  }, []);

  const closeSidebar = useCallback(() => {
    setSidebarOpen(false);
  }, []);

  return (
    <>
      <SkipToContent />
      <LoadingSpinner show={!loaded} />
      <Sidebar show={sidebarOpen} onClose={closeSidebar} onToggle={toggleSidebar} />
      <main id="main-content" className="content" tabIndex={-1}>
        <Topbar onToggleSidebar={toggleSidebar} />
        <Container fluid className="px-0">
          {children}
        </Container>
        <Footer />
      </main>
    </>
  );
}
