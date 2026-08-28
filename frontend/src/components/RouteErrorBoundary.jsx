import { Component } from "react";

/**
 * RouteErrorBoundary — a reusable class-based ErrorBoundary you wrap
 * around any route or subtree. When a fatal render or lifecycle error
 * happens (that would otherwise nuke the app to a white screen), it
 * catches, logs, and shows a friendly retry UI instead.
 *
 * Usage:
 *   <RouteErrorBoundary name="Discovery">
 *     <Discovery />
 *   </RouteErrorBoundary>
 *
 * Optional `onRetry` prop is called on "Try again" so callers can
 * re-fetch/reset state before we clear the error and re-render.
 */
export default class RouteErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    // Log to console so devs / a future Sentry integration can capture.
    // Keep the message intentionally simple — a real Sentry hookup can
    // replace this later without touching call sites.
    console.error(
      `[RouteErrorBoundary${this.props.name ? ` · ${this.props.name}` : ""}]`,
      error,
      info?.componentStack,
    );
  }

  handleRetry = () => {
    try { this.props.onRetry?.(); } catch { /* non-fatal */ }
    this.setState({ hasError: false, error: null });
  };

  handleHardReload = () => {
    try {
      // Also clear the SW's runtime caches — the sign-in bug taught us
      // stale caches can outlive a normal reload.
      if ("serviceWorker" in navigator) {
        navigator.serviceWorker.ready.then((reg) => {
          reg.active?.postMessage({ type: "CLEAR_CACHES" });
        }).catch(() => {});
      }
    } catch { /* non-fatal */ }
    window.location.reload();
  };

  render() {
    if (!this.state.hasError) return this.props.children;

    const label = this.props.name || "this page";
    return (
      <div
        className="min-h-[60vh] flex items-center justify-center p-6"
        role="alert"
        data-testid="route-error-boundary"
      >
        <div className="max-w-md w-full bg-white border border-gray-200 rounded-2xl shadow-lg p-8 text-center">
          <div className="text-4xl mb-3" aria-hidden="true">🥏</div>
          <h1 className="font-display text-2xl text-gray-900 mb-2">
            Something snapped mid-flight
          </h1>
          <p className="text-sm text-gray-600 mb-6">
            We hit an unexpected error rendering {label}. Nothing&apos;s lost — try again
            and it usually clears right up.
          </p>
          <div className="flex flex-col sm:flex-row gap-2 sm:justify-center">
            <button
              type="button"
              onClick={this.handleRetry}
              data-testid="route-error-retry-btn"
              className="px-5 py-2.5 rounded-full bg-emerald-800 hover:bg-emerald-700 text-white font-semibold text-sm transition-colors"
            >
              Try again
            </button>
            <button
              type="button"
              onClick={this.handleHardReload}
              data-testid="route-error-reload-btn"
              className="px-5 py-2.5 rounded-full border border-gray-300 text-gray-700 hover:bg-gray-50 font-semibold text-sm transition-colors"
            >
              Reload the page
            </button>
          </div>
          {this.state.error?.message && (
            <details className="mt-5 text-left">
              <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-600 font-mono">
                Error details
              </summary>
              <pre className="mt-2 text-[10px] text-gray-500 bg-gray-50 rounded p-2 overflow-x-auto whitespace-pre-wrap">
                {String(this.state.error.message)}
              </pre>
            </details>
          )}
        </div>
      </div>
    );
  }
}
