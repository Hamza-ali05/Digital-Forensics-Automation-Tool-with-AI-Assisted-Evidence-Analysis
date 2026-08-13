import React from "react";
import { BrowserRouter } from "react-router-dom";

import { ThemeProvider } from "./contexts/ThemeContext";
import { AuthProvider } from "./contexts/AuthContext";
import { NotificationProvider } from "./contexts/NotificationContext";
import ScrollToTop from "./components/common/ScrollToTop";
import ErrorBoundary from "./components/common/ErrorBoundary";
import ToastContainer from "./components/common/ToastContainer";
import { AppRoutes } from "./routes";

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
              <AppRoutes />
            </ErrorBoundary>
          </BrowserRouter>
        </NotificationProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}
