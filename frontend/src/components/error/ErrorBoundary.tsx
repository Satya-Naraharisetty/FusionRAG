import { Component, ErrorInfo, ReactNode } from "react";
import { AlertTriangle } from "lucide-react";
import { Button } from "../ui/button";

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
        <div className="flex-1 flex flex-col items-center justify-center p-6 text-center bg-zinc-950 text-zinc-350 min-h-[300px]">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-red-950/20 text-red-500 mb-4 border border-red-900/10">
            <AlertTriangle size={20} />
          </div>
          <h3 className="text-sm font-bold text-zinc-200 mb-1">
            Something went wrong
          </h3>
          <p className="text-xs text-zinc-500 max-w-sm mb-4 leading-relaxed">
            An unexpected error occurred rendering this component. Let's try reloading the interface.
          </p>
          {import.meta.env.DEV && this.state.error && (
            <pre className="p-3 bg-zinc-900 border border-zinc-800 text-[10px] font-mono text-red-400 rounded-lg max-w-lg overflow-x-auto text-left mb-4 w-full">
              {this.state.error.toString()}
            </pre>
          )}
          <Button
            onClick={this.handleReset}
            className="bg-zinc-900 border border-zinc-800 hover:bg-zinc-850 text-zinc-300 text-xs h-8 px-4"
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
