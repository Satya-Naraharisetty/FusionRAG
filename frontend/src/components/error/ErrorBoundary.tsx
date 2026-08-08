import { Component, ErrorInfo, ReactNode } from "react";
import { AlertTriangle } from "lucide-react";
import { Button } from "../ui/Button";

interface Props {
  children?: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error("Uncaught boundary error:", error, errorInfo);
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null });
    window.location.reload();
  };

  public render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="flex-1 flex flex-col items-center justify-center p-6 text-center bg-[var(--bg-primary)] text-[var(--text-primary)] min-h-[300px]">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-red-500/10 text-red-400 mb-4 border border-red-500/20">
            <AlertTriangle size={20} />
          </div>
          <h3 className="text-base font-semibold text-[var(--text-primary)] mb-1">
            Something went wrong
          </h3>
          <p className="text-xs text-[var(--text-secondary)] max-w-sm mb-4 leading-relaxed">
            An unexpected error occurred rendering this component. Let's try reloading the interface.
          </p>
          {import.meta.env.DEV && this.state.error && (
            <pre className="p-3 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-[11px] font-mono text-red-400 rounded-[var(--radius-md)] max-w-lg overflow-x-auto text-left mb-4 w-full">
              {this.state.error.toString()}
            </pre>
          )}
          <Button
            variant="secondary"
            size="sm"
            onClick={this.handleReset}
          >
            Reload Interface
          </Button>
        </div>
      );
    }

    return this.props.children;
  }
}
export default ErrorBoundary;
