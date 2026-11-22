import { useState } from 'react';
import { useDebuggerStore } from '@/store';

/**
 * Supported event schema version.
 * The debugger fully supports this version with all visualization features.
 */
const SUPPORTED_SCHEMA_VERSION = 'LogEvent/v1';

/**
 * Schema compatibility warning banner.
 *
 * Displays a dismissible warning when the current run uses an unsupported
 * event schema version. This allows graceful degradation for forward
 * compatibility.
 */
export function SchemaBanner() {
  const [dismissed, setDismissed] = useState(false);
  const currentRunSummary = useDebuggerStore((s) => s.currentRunSummary);

  // Get schema version from run summary
  const schemaVersion = currentRunSummary?.summary?.events_schema_version as
    | string
    | undefined;

  // Don't show if no run selected, no schema version, or supported
  if (!currentRunSummary || !schemaVersion || schemaVersion === SUPPORTED_SCHEMA_VERSION) {
    return null;
  }

  // Don't show if dismissed
  if (dismissed) {
    return null;
  }

  return (
    <div className="flex items-center justify-between px-4 py-2 bg-[var(--color-warning-bg,#fef3c7)] text-[var(--color-warning-text,#92400e)] border-b border-[var(--color-warning-border,#fcd34d)]">
      <div className="flex items-center gap-2">
        <svg
          className="w-5 h-5 flex-shrink-0"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
          />
        </svg>
        <span className="text-sm">
          Unsupported event schema ({schemaVersion}); showing summary only.
        </span>
      </div>
      <button
        onClick={() => setDismissed(true)}
        className="p-1 hover:bg-[var(--color-warning-hover,#fcd34d)] rounded transition-colors"
        title="Dismiss"
      >
        <svg
          className="w-4 h-4"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M6 18L18 6M6 6l12 12"
          />
        </svg>
      </button>
    </div>
  );
}
