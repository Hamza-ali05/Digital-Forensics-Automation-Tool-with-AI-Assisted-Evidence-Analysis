import React, { useCallback, useEffect, useRef, useState } from "react";
import { BrowserRouter } from "react-router-dom";

import { ThemeProvider } from "./contexts/ThemeContext";
import { AuthProvider } from "./contexts/AuthContext";
import { NotificationProvider } from "./contexts/NotificationContext";
import ScrollToTop from "./components/common/ScrollToTop";
import ErrorBoundary from "./components/common/ErrorBoundary";
import ToastContainer from "./components/common/ToastContainer";
import StartupScreen from "./components/common/StartupScreen";
import systemService from "./services/system.service";
import { AppRoutes } from "./routes";

/**
 * Blocks the UI until the backend reports ready/degraded, or shows boot errors.
 */
function BootstrapGate({ children }) {
  const [view, setView] = useState("checking");
  const [startupReport, setStartupReport] = useState(null);
  const [errorDetail, setErrorDetail] = useState("");
  const viewRef = useRef(view);

  useEffect(() => {
    viewRef.current = view;
  }, [view]);

  const evaluate = useCallback(async () => {
    try {
      const status = await systemService.getStatus();
      const readiness = String(status?.system_readiness || "initializing").toLowerCase();

      if (readiness === "initializing") {
        setView("initializing");
        setErrorDetail("");
        return;
      }

      if (readiness === "unavailable") {
        setView("unavailable");
        try {
          setStartupReport(await systemService.getStartupReport());
        } catch {
          setStartupReport(null);
        }
        return;
      }

      setView("ready");
      setStartupReport(null);
      setErrorDetail("");
    } catch (err) {
      const message =
        err?.message ||
        "Could not connect to the DFAT API. Start the backend server and refresh.";
      setErrorDetail(message);
      setView("offline");
      setStartupReport(null);
    }
  }, []);

  useEffect(() => {
    evaluate();
    const intervalId = window.setInterval(() => {
      const current = viewRef.current;
      if (
        current === "checking" ||
        current === "initializing" ||
        current === "offline"
      ) {
        evaluate();
      }
    }, 3000);

    return () => window.clearInterval(intervalId);
  }, [evaluate]);

  if (view === "checking" || view === "initializing") {
    return <StartupScreen mode="initializing" startupReport={startupReport} />;
  }

  if (view === "unavailable") {
    return (
      <StartupScreen
        mode="unavailable"
        startupReport={startupReport}
        errorDetail={errorDetail}
      />
    );
  }

  if (view === "offline") {
    return <StartupScreen mode="offline" errorDetail={errorDetail} />;
  }

  return children;
}

/**
 * Root application — providers, toasts, error boundary, and routes.
 */
export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <NotificationProvider>
          <ToastContainer />
          <BrowserRouter>
            <ScrollToTop />
            <ErrorBoundary>
              <BootstrapGate>
                <AppRoutes />
              </BootstrapGate>
            </ErrorBoundary>
          </BrowserRouter>
        </NotificationProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}
