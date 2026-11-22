import { Component, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback ?? (
        <div className="p-4 bg-red-900/20 border border-red-500 rounded m-4">
          <h2 className="text-red-400 font-bold">Something went wrong</h2>
          <pre className="text-xs text-red-300 mt-2 overflow-auto">
            {this.state.error?.message}
          </pre>
          <button
            onClick={() => this.setState({ hasError: false })}
            className="mt-2 px-3 py-1 bg-red-500 text-white rounded text-sm"
          >
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
