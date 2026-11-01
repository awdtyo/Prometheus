import type { ErrorInfo, ReactNode } from "react";
import { Component } from "react";

interface Props {
  children: ReactNode;
  fallback?: (props: { error: Error; reset: () => void }) => ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(_error: Error, errorInfo: ErrorInfo): void {
    // eslint-disable-next-line no-console
    console.error("ErrorBoundary caught an error:", errorInfo.componentStack);
  }

  reset = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    if (this.state.error) {
      const { fallback } = this.props;
      const error = this.state.error;
      if (fallback) {
        return fallback({ error, reset: this.reset });
      }
      return (
        <div role="alert" style={errorStyles.container}>
          <h2 style={errorStyles.title}>Something went wrong</h2>
          <pre style={errorStyles.message}>{error.message}</pre>
          {error.stack && (
            <details style={errorStyles.details}>
              <summary>Stack trace</summary>
              <pre style={errorStyles.stack}>{error.stack}</pre>
            </details>
          )}
          <button style={errorStyles.button} onClick={this.reset}>
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

const errorStyles: Record<string, React.CSSProperties> = {
  container: {
    padding: 32,
    border: "1px solid var(--border-strong)",
    background: "var(--surface)",
    color: "var(--text)",
    maxWidth: 700,
    margin: "0 auto",
  },
  title: { margin: "0 0 12px", fontSize: 1.25, color: "var(--red)" },
  message: {
    margin: "0 0 12px",
    whiteSpace: "pre-wrap",
    fontFamily: "var(--mono)",
    fontSize: 0.85,
    color: "var(--muted)",
  },
  details: { margin: "12px 0 0", fontSize: 0.85 },
  stack: {
    margin: "6px 0 0",
    whiteSpace: "pre-wrap",
    fontFamily: "var(--mono)",
    fontSize: 0.75,
    color: "var(--faint)",
  },
  button: {
    marginTop: 16,
    padding: "8px 16px",
    background: "var(--amber)",
    color: "#161006",
    border: "none",
    borderRadius: 6,
    fontWeight: 650,
    cursor: "pointer",
  },
};
