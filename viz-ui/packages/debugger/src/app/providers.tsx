import { type ReactNode } from 'react';

interface ProvidersProps {
  children: ReactNode;
}

/**
 * Application providers wrapper.
 *
 * Currently minimal since Zustand doesn't require a provider.
 * This is a placeholder for future providers (e.g., React Query, i18n).
 */
export function Providers({ children }: ProvidersProps) {
  return <>{children}</>;
}

export default Providers;
