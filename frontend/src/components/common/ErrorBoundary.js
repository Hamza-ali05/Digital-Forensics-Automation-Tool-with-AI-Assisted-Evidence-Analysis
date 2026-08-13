import React from "react";
import { Alert, Button, Card } from "@themesberg/react-bootstrap";

import config from "config";

/**
 * Class error boundary with friendly recovery UI.
 */
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    if (config.debug || process.env.NODE_ENV !== "production") {
      // eslint-disable-next-line no-console
      console.error("[DFAT ErrorBoundary]", error, errorInfo);
    }

    const { onError } = this.props;
    if (typeof onError === "function") {
      onError(error, errorInfo);
    }
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      const message =
        this.state.error?.message ||
        "Something went wrong while rendering this view.";

      return (
        <Card border="light" className="shadow-sm m-3">
          <Card.Body>
            <h4 className="mb-3">Unexpected error</h4>
            <Alert variant="danger">
              <p className="mb-2">
                A problem prevented this page from displaying correctly.
              </p>
              <p className="mb-0 small text-break">{message}</p>
            </Alert>
            <Button variant="primary" onClick={this.handleRetry}>
              Try Again
            </Button>
          </Card.Body>
        </Card>
      );
    }

    return this.props.children;
  }
}
